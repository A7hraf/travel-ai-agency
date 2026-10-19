"""Messages reach the right company: number ownership, webhook signatures, races, old chat links."""

import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest

from app import database
from app.ai.llm import LLMResponse
from app.config import get_settings
from app.models import Company, Conversation, ConversationStatus, Customer, Message, Sender, utcnow
from app.services import conversations as convsvc
from app.services import whatsapp as whatsapp_service
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, make_company
from tests.test_whatsapp import wa_payload

HOOK = "/api/webhooks/whatsapp"


@pytest.fixture
def meta(monkeypatch):
    """Meta's answer to "may this token use this number?": a dict of number id -> token."""
    owners: dict[str, str] = {}
    calls: list[tuple[str, str]] = []

    def verify(number_id, token):
        calls.append((number_id, token))
        return owners.get(number_id) == token

    monkeypatch.setattr(whatsapp_service, "verify_phone_number", verify)
    return owners, calls


@pytest.fixture
def unsigned(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_allow_unsigned", True)


def _signed(body: dict, secret: str) -> dict:
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return {"content": raw, "headers": {"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"}}


# --- 1. A company can only connect a number its own Meta token can use -------------------------


def test_number_cannot_be_claimed_without_own_verified_token(client, owner, meta):
    owners, calls = meta
    owners["PNID-BETA"] = "beta-token"
    _, admin_a = make_company(client, owner, name="Alpha", admin_email="a@a.com")
    _, admin_b = make_company(client, owner, name="Beta", admin_email="b@b.com")

    r = client.patch("/api/company", headers=admin_a, json={"whatsapp_phone_number_id": "PNID-BETA"})
    assert r.status_code == 400 and "access token" in r.json()["detail"]
    r = client.patch("/api/company", headers=admin_a, json={
        "whatsapp_phone_number_id": "PNID-BETA", "whatsapp_access_token": "alpha-token"})
    assert r.status_code == 400 and "did not confirm" in r.json()["detail"]
    # Nothing from the refused request was saved, not even the token.
    assert client.get("/api/company", headers=admin_a).json()["whatsapp_token_set"] is False

    r = client.patch("/api/company", headers=admin_b, json={
        "whatsapp_phone_number_id": "PNID-BETA", "whatsapp_access_token": "beta-token"})
    assert r.status_code == 200 and r.json()["whatsapp_phone_number_id"] == "PNID-BETA"
    assert calls[-1] == ("PNID-BETA", "beta-token")


def test_number_is_checked_with_the_stored_token_and_only_when_it_changes(client, company_a, meta):
    owners, calls = meta
    owners["PNID-A"] = owners["PNID-A2"] = "tok"
    _, admin = company_a
    assert client.patch("/api/company", headers=admin, json={"whatsapp_access_token": "tok"}).status_code == 200
    assert client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-A"}).status_code == 200
    assert calls == [("PNID-A", "tok")]
    # The settings page sends the number with every save: an unchanged number isn't checked again.
    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-A",
                                                          "whatsapp_display_number": "+968 1"})
    assert r.status_code == 200 and len(calls) == 1
    assert client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-A2"}).status_code == 200
    assert calls[-1] == ("PNID-A2", "tok")
    # Disconnecting needs no check.
    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": ""})
    assert r.status_code == 200 and r.json()["whatsapp_phone_number_id"] is None


def test_verify_phone_number_asks_meta(monkeypatch):
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        if headers["Authorization"] == "Bearer good":
            return httpx.Response(200, json={"id": "123"})
        return httpx.Response(400, json={"error": {"message": "Unsupported get request"}})

    monkeypatch.setattr(whatsapp_service.httpx, "get", fake_get)
    assert whatsapp_service.verify_phone_number("123", "good") is True
    s = get_settings()
    assert seen["url"] == f"{s.whatsapp_graph_url}/{s.whatsapp_api_version}/123" and seen["params"] == {"fields": "id"}
    assert whatsapp_service.verify_phone_number("123", "bad") is False

    def down(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(whatsapp_service.httpx, "get", down)
    assert whatsapp_service.verify_phone_number("123", "good") is False


def test_platform_token_is_used_only_when_the_platform_shares_its_app(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_default_access_token", "platform-token")
    own = Company(name="x", slug="x", whatsapp_phone_number_id="1", whatsapp_access_token="own")
    shared = Company(name="y", slug="y", whatsapp_phone_number_id="2")
    assert whatsapp_service.access_token_for(own) == "own"
    assert whatsapp_service.access_token_for(shared) == "platform-token"
    monkeypatch.setattr(get_settings(), "whatsapp_share_default_token", False)
    assert whatsapp_service.access_token_for(shared) is None
    with pytest.raises(whatsapp_service.WhatsAppError):
        whatsapp_service.CloudAPISender().send_text(shared, "968", "hi")


# --- 4 & 5. Webhook signatures --------------------------------------------------------------------


def test_unsigned_webhooks_are_refused_unless_explicitly_allowed(client, monkeypatch):
    assert get_settings().environment != "production"
    assert client.post(HOOK, json={"entry": []}).status_code == 503
    monkeypatch.setattr(get_settings(), "whatsapp_allow_unsigned", True)
    assert client.post(HOOK, json={"entry": []}).status_code == 200


def test_company_webhook_never_falls_back_to_the_platform_secret(client, company_a, monkeypatch):
    _, admin = company_a
    path = client.get("/api/company", headers=admin).json()["whatsapp_webhook_path"]
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "platform-secret")
    assert client.post(path, **_signed({"entry": []}, "platform-secret")).status_code == 503

    client.patch("/api/company", headers=admin, json={"whatsapp_app_secret": "company-secret"})
    assert client.post(path, **_signed({"entry": []}, "platform-secret")).status_code == 403
    assert client.post(path, **_signed({"entry": []}, "company-secret")).status_code == 200


# --- 2 & 3. Two messages from one customer at the same moment -------------------------------------


@pytest.fixture
def connected(client, company_a, meta, unsigned, scripted):
    owners, _ = meta
    owners["PNID-A"] = "tok"
    _, admin = company_a
    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-A",
                                                          "whatsapp_access_token": "tok"})
    assert r.status_code == 200
    set_whatsapp_sender(FakeWhatsApp())
    scripted([LLMResponse(f"reply {i}") for i in range(5)])
    return admin


def _company_id():
    with database.SessionLocal() as db:
        return db.query(Company.id).scalar()


def test_new_customer_created_meanwhile_by_another_message_is_reused(client, connected, monkeypatch):
    """The other message inserts the customer between our lookup and our insert."""
    real_scalar = database.Session.scalar
    state = {"done": False}

    def racing_scalar(self, stmt, *a, **k):
        if not state["done"] and "FROM customers" in str(stmt):
            state["done"] = True
            with database.SessionLocal() as other:
                other.add(Customer(company_id=_company_id(), whatsapp_id="9682", phone="+9682"))
                other.commit()
            return None
        return real_scalar(self, stmt, *a, **k)

    monkeypatch.setattr(database.Session, "scalar", racing_scalar)
    convsvc.process_whatsapp_payload(wa_payload("PNID-A", "9682", "first", "wamid.a"))
    monkeypatch.setattr(database.Session, "scalar", real_scalar)

    assert state["done"]
    with database.SessionLocal() as db:
        assert db.query(Customer).filter(Customer.whatsapp_id == "9682").count() == 1
        assert db.query(Message).filter(Message.external_id == "wamid.a").count() == 1  # not lost


def test_conversation_opened_meanwhile_by_another_message_is_shared(client, connected, monkeypatch):
    admin = connected
    client.post(HOOK, json=wa_payload("PNID-A", "9681", "hi", "wamid.1"))
    cid = client.get("/api/conversations", headers=admin).json()[0]["id"]
    client.post(f"/api/conversations/{cid}/close", headers=admin)

    real_open = convsvc._open_whatsapp_conversation
    state = {"done": False}

    def racing_open(db, customer):
        if not state["done"]:
            state["done"] = True  # the other message opens a conversation right now
            with database.SessionLocal() as other:
                other.add(Conversation(company_id=customer.company_id, customer_id=customer.id, channel="whatsapp"))
                other.commit()
            return None
        return real_open(db, customer)

    monkeypatch.setattr(convsvc, "_open_whatsapp_conversation", racing_open)
    convsvc.process_whatsapp_payload(wa_payload("PNID-A", "9681", "again", "wamid.2"))

    with database.SessionLocal() as db:
        open_convs = db.query(Conversation).filter(Conversation.status != ConversationStatus.CLOSED).all()
        assert len(open_convs) == 1
        texts = [m.content for m in db.query(Message).filter(Message.conversation_id == open_convs[0].id,
                                                               Message.sender == Sender.CUSTOMER)]
        assert texts == ["again"]


def test_one_broken_message_does_not_drop_the_rest(client, connected, monkeypatch):
    real = convsvc._whatsapp_conversation

    def flaky(db, company, wa_id, profile_name):
        if wa_id == "111":
            raise RuntimeError("boom")
        return real(db, company, wa_id, profile_name)

    monkeypatch.setattr(convsvc, "_whatsapp_conversation", flaky)
    payload = wa_payload("PNID-A", "111", "breaks", "wamid.bad")
    second = wa_payload("PNID-A", "222", "works", "wamid.good")
    payload["entry"][0]["changes"].append(second["entry"][0]["changes"][0])
    convsvc.process_whatsapp_payload(payload)
    with database.SessionLocal() as db:
        assert db.query(Message).filter(Message.external_id == "wamid.good").count() == 1


# --- 6. Old web chat links --------------------------------------------------------------------------


def test_web_chat_link_expires_after_a_quiet_month(client, company_a):
    company, _ = company_a
    base = f"/api/public/companies/{company['slug']}/chats"
    token = client.post(base, json={}).json()["token"]
    assert client.get(f"{base}/{token}/messages").status_code == 200

    def age(days):
        with database.SessionLocal() as db:
            conv = db.query(Conversation).filter(Conversation.public_token == token).one()
            conv.last_message_at = utcnow() - timedelta(days=days)
            db.commit()

    age(29)
    assert client.get(f"{base}/{token}/messages").status_code == 200
    age(31)
    for r in (client.get(f"{base}/{token}/messages"),
              client.post(f"{base}/{token}/messages", json={"content": "hello?"})):
        assert r.status_code == 404 and r.json()["detail"] == "Chat not found"  # same as an unknown link


# --- 7. null for required settings ---------------------------------------------------------------


def test_null_for_required_settings_changes_nothing(client, company_a):
    _, admin = company_a
    before = client.get("/api/company", headers=admin).json()
    r = client.patch("/api/company", headers=admin, json={
        "ai_instructions": None, "knowledge_base": None, "ai_agent_name": None, "currency": None})
    assert r.status_code == 200
    after = r.json()
    for key in ("ai_instructions", "knowledge_base", "ai_agent_name", "currency"):
        assert after[key] == before[key]
    # Optional fields can still be cleared with null.
    client.patch("/api/company", headers=admin, json={"contact_phone": "+968 1"})
    assert client.patch("/api/company", headers=admin, json={"contact_phone": None}).json()["contact_phone"] is None
