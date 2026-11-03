"""Instagram Direct messages: per-company webhook, signatures, routing, AI replies, staff replies,
connection check, platform owner setup, isolation, dashboard and database upgrade."""

import hashlib
import hmac
import json
import threading
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import create_engine, inspect, text

from app import database
from app.ai.llm import LLMResponse
from app.migrations import upgrade
from app.models import Company, Conversation, ConversationStatus, Customer, Message, Sender, utcnow
from app.services import conversations as convsvc
from app.services import instagram as ig
from tests.conftest import login, make_company, make_package

ACCOUNT_A, ACCOUNT_B = "17841400000000001", "17841400000000002"


class FakeInstagram:
    def __init__(self, fail: bool = False, profiles: dict | None = None):
        self.sent: list[tuple[str, str, str]] = []
        self.profile_calls: list[str] = []
        self.fail = fail
        self.profiles = profiles or {}

    def send_text(self, company, igsid, text):
        if self.fail:
            raise ig.InstagramError("boom")
        out_id = None
        for part in ig.split_message(text):
            self.sent.append((company.instagram_account_id, igsid, part))
            out_id = f"ig.out.{len(self.sent)}"
        return out_id

    def profile(self, company, igsid):
        self.profile_calls.append(igsid)
        return self.profiles.get(igsid)


@pytest.fixture
def fake_ig():
    fake = FakeInstagram(profiles={"IGSID-1": {"name": "Omar Al Balushi", "username": "omar.travels"},
                                   "IGSID-2": {"username": "layla_trips"}})
    ig.set_instagram_sender(fake)
    yield fake
    ig.set_instagram_sender(None)


@pytest.fixture
def tokens(monkeypatch):
    """Instagram's /me answer per token: {token: (user_id, username)}; unknown tokens are invalid."""
    owners: dict[str, tuple[str, str]] = {"tok-a": (ACCOUNT_A, "sunrise.travel"), "tok-b": (ACCOUNT_B, "bluesky.om")}

    def fake_get(url, params=None, headers=None, timeout=None):
        token = (headers or {}).get("Authorization", "").removeprefix("Bearer ")
        assert url.endswith("/me") and params == {"fields": "user_id,username"}
        if token in owners:
            user_id, username = owners[token]
            return httpx.Response(200, json={"user_id": user_id, "username": username, "id": "app-scoped"})
        return httpx.Response(400, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})

    monkeypatch.setattr(ig.httpx, "get", fake_get)
    return owners


def connect(client, admin, account_id=ACCOUNT_A, token="tok-a", secret="secret-a"):
    r = client.patch("/api/company", headers=admin, json={
        "instagram_access_token": token, "instagram_app_secret": secret, "instagram_account_id": account_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["instagram_token_set"] and body["instagram_app_secret_set"]
    assert token not in json.dumps(body) and secret not in json.dumps(body)  # write-only
    return client.get("/api/company/instagram", headers=admin).json()


def dm(account_id, igsid, text=None, mid="mid.1", **message):
    msg = {"mid": mid, **message}
    if text is not None:
        msg["text"] = text
    return {"object": "instagram", "entry": [{"id": account_id, "time": 1700000000000, "messaging": [{
        "sender": {"id": igsid}, "recipient": {"id": account_id}, "timestamp": 1700000000000, "message": msg}]}]}


def signed(payload, secret):
    raw = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return {"content": raw, "headers": {"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"}}


@pytest.fixture
def two(client, owner, tokens, fake_ig):
    _, admin_a = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    _, admin_b = make_company(client, owner, name="Blue Sky Travel", admin_email="b@bluesky.com")
    st_a = connect(client, admin_a)
    st_b = connect(client, admin_b, ACCOUNT_B, "tok-b", "secret-b")
    return {"a": admin_a, "b": admin_b, "hook_a": st_a["webhook_path"], "hook_b": st_b["webhook_path"],
            "verify_a": st_a["verify_token"], "verify_b": st_b["verify_token"]}


def post_dm(client, hook, payload, secret="secret-a"):
    r = client.post(hook, **signed(payload, secret))
    assert r.status_code == 200, r.text
    return r


# --- Webhook: verification, signatures, routing ------------------------------------------------------


def test_verify_challenge_uses_each_companys_own_token(client, two):
    def verify(hook, token):
        return client.get(hook, params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "777"})

    r = verify(two["hook_a"], two["verify_a"])
    assert r.status_code == 200 and r.text == "777"
    assert verify(two["hook_a"], two["verify_b"]).status_code == 403  # B's token does not open A's address
    assert verify(two["hook_a"], "").status_code == 403
    assert verify("/api/webhooks/instagram/c/nope", two["verify_a"]).status_code == 404
    assert two["hook_a"] != two["hook_b"] and two["verify_a"] != two["verify_b"]


def test_signature_is_required_with_the_companys_own_secret(client, owner, tokens, fake_ig, scripted):
    _, admin = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    hook = client.get("/api/company/instagram", headers=admin).json()["webhook_path"]
    llm = scripted([LLMResponse("never")])
    payload = dm(ACCOUNT_A, "IGSID-1", "Hi")
    # No app secret saved yet: refused, never accepted unsigned.
    assert client.post(hook, json=payload).status_code == 503
    connect(client, admin)
    assert client.post(hook, json=payload).status_code == 403  # no signature
    assert client.post(hook, **signed(payload, "secret-b")).status_code == 403  # another app's secret
    bad = signed(payload, "secret-a")
    bad["headers"]["X-Hub-Signature-256"] = "sha256=" + "0" * 64
    assert client.post(hook, **bad).status_code == 403
    assert llm.calls == [] and fake_ig.sent == []
    raw = signed(payload, "secret-a")
    raw["content"] = b"not json"
    raw["headers"]["X-Hub-Signature-256"] = "sha256=" + hmac.new(b"secret-a", b"not json", hashlib.sha256).hexdigest()
    assert client.post(hook, **raw).status_code == 400


def test_dm_is_answered_by_the_ai_of_the_owning_company_only(client, two, fake_ig, scripted):
    make_package(client, two["a"])
    llm = scripted([LLMResponse("Hello! Where would you like to travel?")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi, any honeymoon trips?"))

    assert fake_ig.sent == [(ACCOUNT_A, "IGSID-1", "Hello! Where would you like to travel?")]
    system = llm.calls[0][0]["content"]
    assert "Sunrise Travel" in system and "Instagram" in system
    assert "ask for it before booking" in system  # Instagram gives no phone number

    conv = client.get("/api/conversations", headers=two["a"]).json()[0]
    assert conv["channel"] == "instagram"
    assert conv["customer"]["phone"] is None
    assert conv["customer"]["name"] == "Omar Al Balushi"  # read from the profile after the reply
    assert client.get("/api/conversations", headers=two["b"]).json() == []
    detail = client.get(f"/api/conversations/{conv['id']}", headers=two["a"]).json()
    assert detail["messages"][-1]["delivery_status"] == "sent"

    # The same customer writes again: same conversation, and the name is not looked up again.
    scripted([LLMResponse("Great!")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Maldives", mid="mid.2"))
    assert len(client.get("/api/conversations", headers=two["a"]).json()) == 1
    assert fake_ig.profile_calls == ["IGSID-1"]
    # Search by name still works.
    assert len(client.get("/api/conversations?q=Omar", headers=two["a"]).json()) == 1
    assert len(client.get("/api/conversations?channel=instagram", headers=two["a"]).json()) == 1
    assert client.get("/api/conversations?channel=whatsapp", headers=two["a"]).json() == []


def test_company_webhook_cannot_inject_into_another_company(client, two, fake_ig, scripted):
    llm = scripted([LLMResponse("never")])
    # Signed correctly by A, but for B's account: ignored.
    post_dm(client, two["hook_a"], dm(ACCOUNT_B, "IGSID-1", "Hi"))
    # Entry of A, but addressed to B's account: ignored too.
    p = dm(ACCOUNT_A, "IGSID-1", "Hi", mid="mid.x")
    p["entry"][0]["messaging"][0]["recipient"]["id"] = ACCOUNT_B
    post_dm(client, two["hook_a"], p)
    # A's payload on B's address with A's secret: refused.
    assert client.post(two["hook_b"], **signed(dm(ACCOUNT_A, "IGSID-1", "Hi"), "secret-a")).status_code == 403
    assert llm.calls == [] and fake_ig.sent == []
    for admin in (two["a"], two["b"]):
        assert client.get("/api/conversations", headers=admin).json() == []


def test_echoes_reactions_reads_and_own_messages_are_ignored(client, two, fake_ig, scripted):
    llm = scripted([LLMResponse("never")])
    hook = two["hook_a"]
    post_dm(client, hook, dm(ACCOUNT_A, "IGSID-1", "our own reply", is_echo=True))
    post_dm(client, hook, dm(ACCOUNT_A, ACCOUNT_A, "the business itself", mid="mid.self"))
    post_dm(client, hook, dm(ACCOUNT_A, "IGSID-1", "deleted", mid="mid.del", is_deleted=True))
    post_dm(client, hook, dm(ACCOUNT_A, "IGSID-1", mid="mid.story", attachments=[{"type": "story_mention"}]))
    post_dm(client, hook, dm(ACCOUNT_A, "IGSID-1", "no id", mid=""))
    others = {"object": "instagram", "entry": [{"id": ACCOUNT_A, "messaging": [
        {"sender": {"id": "IGSID-1"}, "recipient": {"id": ACCOUNT_A}, "reaction": {"mid": "m", "reaction": "love"}},
        {"sender": {"id": "IGSID-1"}, "recipient": {"id": ACCOUNT_A}, "read": {"mid": "unknown"}},
        {"sender": {"id": "IGSID-1"}, "recipient": {"id": ACCOUNT_A}, "message_edit": {"mid": "m", "text": "x"}},
        "garbage", {"sender": "x"},
    ]}, "garbage"]}
    post_dm(client, hook, others)
    assert llm.calls == [] and fake_ig.sent == []
    assert client.get("/api/conversations", headers=two["a"]).json() == []


def test_photo_is_answered_with_a_request_to_type(client, two, fake_ig, scripted):
    llm = scripted([LLMResponse("Sorry, I can only read text. What trip are you looking for?")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", mid="mid.img",
                                      attachments=[{"type": "image", "payload": {"url": "https://x"}}]))
    assert "Instagram image message that can't be read" in llm.calls[0][-1]["content"]
    assert fake_ig.sent[-1][2].startswith("Sorry, I can only read text")


def test_repeated_delivery_is_handled_once(client, two, fake_ig, scripted):
    scripted([LLMResponse("Hi!"), LLMResponse("second")])
    payload = dm(ACCOUNT_A, "IGSID-1", "Hi", mid="mid.same")
    post_dm(client, two["hook_a"], payload)
    post_dm(client, two["hook_a"], payload)
    assert len(fake_ig.sent) == 1
    with database.SessionLocal() as db:
        assert db.query(Message).filter(Message.external_id == "mid.same").count() == 1


def test_long_ai_reply_is_split_into_1000_character_parts(client, two, fake_ig, scripted):
    long_reply = "\n".join(f"• Package line {i}: " + "x" * 80 for i in range(30))  # about 2,900 characters
    scripted([LLMResponse(long_reply)])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Show me everything"))
    parts = [s[2] for s in fake_ig.sent]
    assert len(parts) == 3 and all(len(p) <= 1000 for p in parts)
    assert all(p.startswith("• Package line") for p in parts)  # cut at line breaks
    assert "\n".join(parts) == long_reply


def test_read_receipt_marks_the_staff_reply_as_read(client, two, fake_ig, scripted):
    scripted([LLMResponse("Hi!")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi"))
    cid = client.get("/api/conversations", headers=two["a"]).json()[0]["id"]
    sent = client.post(f"/api/conversations/{cid}/messages", headers=two["a"], json={"content": "Hello!"}).json()
    assert sent["delivery_status"] == "sent"
    out_id = f"ig.out.{len(fake_ig.sent)}"
    read = {"object": "instagram", "entry": [{"id": ACCOUNT_A, "messaging": [
        {"sender": {"id": "IGSID-1"}, "recipient": {"id": ACCOUNT_A}, "read": {"mid": out_id}}]}]}
    post_dm(client, two["hook_b"], read, "secret-b")  # B's webhook can't touch A's messages
    detail = client.get(f"/api/conversations/{cid}", headers=two["a"]).json()
    assert detail["messages"][-1]["delivery_status"] == "sent"
    post_dm(client, two["hook_a"], read)
    detail = client.get(f"/api/conversations/{cid}", headers=two["a"]).json()
    assert detail["messages"][-1]["delivery_status"] == "read"


# --- Two first messages at the same moment ----------------------------------------------------------


def _company_id(name):
    with database.SessionLocal() as db:
        return db.query(Company.id).filter(Company.name == name).scalar()


def test_new_customer_created_meanwhile_is_reused(client, two, fake_ig, scripted, monkeypatch):
    scripted([LLMResponse("reply")])
    real_scalar = database.Session.scalar
    state = {"done": False}
    company_id = _company_id("Sunrise Travel")

    def racing_scalar(self, stmt, *a, **k):
        if not state["done"] and "FROM customers" in str(stmt):
            state["done"] = True  # the other message creates the customer right now
            with database.SessionLocal() as other:
                other.add(Customer(company_id=company_id, instagram_id="IGSID-9"))
                other.commit()
            return None
        return real_scalar(self, stmt, *a, **k)

    monkeypatch.setattr(database.Session, "scalar", racing_scalar)
    convsvc.process_instagram_payload(dm(ACCOUNT_A, "IGSID-9", "first", mid="mid.a"), company_id)
    monkeypatch.setattr(database.Session, "scalar", real_scalar)

    assert state["done"]
    with database.SessionLocal() as db:
        assert db.query(Customer).filter(Customer.instagram_id == "IGSID-9").count() == 1
        assert db.query(Message).filter(Message.external_id == "mid.a").count() == 1  # not lost


def test_conversation_opened_meanwhile_is_shared(client, two, fake_ig, scripted, monkeypatch):
    scripted([LLMResponse("reply 1"), LLMResponse("reply 2")])
    company_id = _company_id("Sunrise Travel")
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-7", "hi", mid="mid.first"))
    cid = client.get("/api/conversations", headers=two["a"]).json()[0]["id"]
    client.post(f"/api/conversations/{cid}/close", headers=two["a"])
    real_open = convsvc._open_instagram_conversation
    state = {"done": False}

    def racing_open(db, customer):
        if not state["done"]:
            state["done"] = True  # the other message opens a conversation right now
            with database.SessionLocal() as other:
                other.add(Conversation(company_id=customer.company_id, customer_id=customer.id, channel="instagram"))
                other.commit()
            return None
        return real_open(db, customer)

    if database.engine.dialect.name == "postgresql":
        # PostgreSQL: the row lock makes the second message wait, so the other conversation can only
        # appear before the lock is taken.
        real_customer = convsvc._channel_customer

        def racing_customer(db, *a, **k):
            customer = real_customer(db, *a, **k)
            racing_open(db, customer)
            return customer
        monkeypatch.setattr(convsvc, "_channel_customer", racing_customer)
    else:
        monkeypatch.setattr(convsvc, "_open_instagram_conversation", racing_open)
    convsvc.process_instagram_payload(dm(ACCOUNT_A, "IGSID-7", "hello", mid="mid.r"), company_id)
    assert state["done"]
    with database.SessionLocal() as db:
        convs = db.query(Conversation).filter(Conversation.status != ConversationStatus.CLOSED).all()
        assert len(convs) == 1
        texts = [m.content for m in db.query(Message).filter(Message.conversation_id == convs[0].id,
                                                               Message.sender == Sender.CUSTOMER)]
        assert texts == ["hello"]


def test_two_first_messages_in_parallel_make_one_customer_and_one_chat(client, two, fake_ig, scripted):
    scripted([LLMResponse("reply 1"), LLMResponse("reply 2")])
    company_id = _company_id("Sunrise Travel")
    start = threading.Barrier(2)
    errors = []

    def deliver(mid):
        try:
            start.wait(5)
            convsvc.process_instagram_payload(dm(ACCOUNT_A, "IGSID-5", f"hi {mid}", mid=mid), company_id)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=deliver, args=(m,)) for m in ("mid.p1", "mid.p2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors
    with database.SessionLocal() as db:
        assert db.query(Customer).filter(Customer.instagram_id == "IGSID-5").count() == 1
        convs = db.query(Conversation).filter(Conversation.channel == "instagram").all()
        assert len(convs) == 1
        assert db.query(Message).filter(Message.conversation_id == convs[0].id,
                                        Message.sender == Sender.CUSTOMER).count() == 2


# --- Staff replies ----------------------------------------------------------------------------------


def test_staff_reply_goes_out_on_instagram_within_24_hours(client, two, fake_ig, scripted):
    scripted([LLMResponse("Hi!")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi"))
    cid = client.get("/api/conversations", headers=two["a"]).json()[0]["id"]

    r = client.post(f"/api/conversations/{cid}/messages", headers=two["a"], json={"content": "I'll call you now."})
    assert r.status_code == 201 and r.json()["delivery_status"] == "sent"
    assert fake_ig.sent[-1] == (ACCOUNT_A, "IGSID-1", "I'll call you now.")

    ig.set_instagram_sender(FakeInstagram(fail=True))
    r = client.post(f"/api/conversations/{cid}/messages", headers=two["a"], json={"content": "again"})
    assert r.status_code == 201 and r.json()["delivery_status"] == "failed"

    with database.SessionLocal() as db:  # the customer's last message is now 25 hours old
        db.get(Conversation, cid).last_customer_message_at = utcnow() - timedelta(hours=25)
        db.commit()
    ig.set_instagram_sender(fake_ig)
    count = len(fake_ig.sent)
    r = client.post(f"/api/conversations/{cid}/messages", headers=two["a"], json={"content": "late"})
    assert r.status_code == 409 and "Instagram only allows replies within 24 hours" in r.json()["detail"]
    assert len(fake_ig.sent) == count


def test_other_companys_staff_cannot_see_or_answer_instagram_chats(client, two, fake_ig, scripted):
    scripted([LLMResponse("Hi!")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi"))
    cid = client.get("/api/conversations", headers=two["a"]).json()[0]["id"]
    assert client.get(f"/api/conversations/{cid}", headers=two["b"]).status_code == 404
    assert client.post(f"/api/conversations/{cid}/messages", headers=two["b"], json={"content": "x"}).status_code == 404
    assert client.get("/api/conversations?channel=instagram", headers=two["b"]).json() == []
    # B's status shows only B's own account and secrets are never sent.
    st = client.get("/api/company/instagram", headers=two["b"]).json()
    assert st["account_id"] == ACCOUNT_B and "secret-b" not in json.dumps(st)


# --- Connection check and settings ------------------------------------------------------------------


def test_connection_check_requires_the_tokens_own_account(client, owner, tokens, fake_ig):
    _, admin_a = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    _, admin_b = make_company(client, owner, name="Blue Sky Travel", admin_email="b@bluesky.com")
    st = client.get("/api/company/instagram", headers=admin_a).json()
    assert st["status"] == "not_connected" and st["webhook_path"].startswith("/api/webhooks/instagram/c/")
    assert st["verify_token"]
    assert client.post("/api/company/instagram/test", headers=admin_a).json()["result"] == "not_configured"

    # An account ID without a token, or with a token of another account: refused.
    r = client.patch("/api/company", headers=admin_b, json={"instagram_account_id": ACCOUNT_A})
    assert r.status_code == 400 and "access token" in r.json()["detail"]
    r = client.patch("/api/company", headers=admin_b, json={"instagram_access_token": "tok-b",
                                                            "instagram_account_id": ACCOUNT_A})
    assert r.status_code == 400 and "did not confirm" in r.json()["detail"]
    assert client.get("/api/company/instagram", headers=admin_b).json()["status"] == "not_connected"  # nothing saved
    # Only a token: the account it belongs to is connected, no account ID to look up.
    r = client.patch("/api/company", headers=admin_b, json={"instagram_access_token": "tok-b"})
    assert r.status_code == 200 and r.json()["instagram_account_id"] == ACCOUNT_B
    assert r.json()["instagram_username"] == "bluesky.om"

    # The right token: connected, the username comes from Instagram.
    st = connect(client, admin_a)
    assert st["status"] == "connected" and st["username"] == "sunrise.travel"
    test = client.post("/api/company/instagram/test", headers=admin_a).json()
    assert test["result"] == "connected" and test["status"]["status"] == "connected"

    # B can't take A's account even with a token that claims it, explicitly or by detection.
    tokens["tok-evil"] = (ACCOUNT_A, "sunrise.travel")
    r = client.patch("/api/company", headers=admin_b, json={"instagram_access_token": "tok-evil",
                                                            "instagram_account_id": ACCOUNT_A})
    assert r.status_code == 409
    _, admin_c = make_company(client, owner, name="Third Travel", admin_email="c@third.com")
    r = client.patch("/api/company", headers=admin_c, json={"instagram_access_token": "tok-evil"})
    assert r.status_code == 200 and r.json()["instagram_account_id"] is None

    # A swaps to a token of another account: the test names the exact problem.
    client.patch("/api/company", headers=admin_a, json={"instagram_access_token": "tok-b"})
    assert client.post("/api/company/instagram/test", headers=admin_a).json()["result"] == "account_mismatch"
    client.patch("/api/company", headers=admin_a, json={"instagram_access_token": "expired"})
    assert client.post("/api/company/instagram/test", headers=admin_a).json()["result"] == "token_invalid"
    client.patch("/api/company", headers=admin_a, json={"instagram_access_token": ""})
    assert client.get("/api/company/instagram", headers=admin_a).json()["status"] == "needs_token"
    client.patch("/api/company", headers=admin_a, json={"instagram_account_id": ""})
    assert client.get("/api/company/instagram", headers=admin_a).json()["status"] == "not_connected"


def test_check_account_maps_instagram_errors(monkeypatch):
    def answer(status, body):
        return lambda *a, **k: httpx.Response(status, json=body)

    cases = [
        (answer(200, {"user_id": "5", "username": "x"}), "5", "connected"),
        (answer(200, {"user_id": "6", "username": "x"}), "5", "account_mismatch"),
        (answer(200, {"user_id": "6"}), "", "account_missing"),
        (answer(400, {"error": {"code": 190, "message": "expired"}}), "5", "token_invalid"),
        (answer(403, {"error": {"code": 10, "message": "Permission"}}), "5", "no_access"),
        (answer(500, {}), "5", "network"),
    ]
    for fake, account, expected in cases:
        monkeypatch.setattr(ig.httpx, "get", fake)
        assert ig.check_account(account, "t")["result"] == expected

    def down(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(ig.httpx, "get", down)
    assert ig.check_account("5", "t")["result"] == "network"
    assert ig.check_account("5", "")["result"] == "not_configured"


def test_settings_permissions(client, owner, tokens):
    _, admin = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    r = client.post("/api/users", headers=admin, json={"email": "s@sunrise.com", "full_name": "Staff",
                                                       "password": "Password123", "role": "support"})
    assert r.status_code == 201
    support = login(client, "s@sunrise.com", "Password123")
    assert client.get("/api/company/instagram", headers=support).status_code == 403
    assert client.post("/api/company/instagram/test", headers=support).status_code == 403
    body = client.get("/api/company", headers=support).json()
    assert "instagram_verify_token" not in body and body["instagram_token_set"] is False


def test_real_sender_posts_to_the_graph_api_in_parts(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return httpx.Response(200, json={"recipient_id": "IGSID-1", "message_id": f"m{len(calls)}"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(ig.httpx, "post", fake_post)
    company = Company(name="X", slug="x", instagram_account_id=ACCOUNT_A, instagram_access_token="tok")
    assert ig.GraphSender().send_text(company, "IGSID-1", "word " * 500) == "m3"
    url, body, headers = calls[0]
    assert url == f"https://graph.instagram.com/{ig.DEFAULT_API_VERSION}/{ACCOUNT_A}/messages"
    assert headers == {"Authorization": "Bearer tok"} and body["recipient"] == {"id": "IGSID-1"}
    assert all(len(c[1]["message"]["text"]) <= 1000 for c in calls)
    with pytest.raises(ig.InstagramError):
        ig.GraphSender().send_text(Company(name="Y", slug="y"), "IGSID-1", "hi")


# --- Platform owner -------------------------------------------------------------------------------


def test_owner_assigns_an_account_without_the_check(client, owner, tokens, fake_ig, scripted):
    company, admin = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    other, admin_b = make_company(client, owner, name="Blue Sky Travel", admin_email="b@bluesky.com")
    base = f"/api/system/companies/{company['id']}/instagram"
    assert client.get(base, headers=admin).status_code == 403  # company admins can't use the console
    r = client.patch(base, headers=owner, json={"instagram_account_id": "999", "instagram_username": "@sunrise",
                                                "instagram_access_token": "not-checked", "instagram_app_secret": "s"})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["status"] == "connected" and st["account_id"] == "999" and st["username"] == "sunrise"
    assert "not-checked" not in json.dumps(st)
    assert client.get("/api/company/instagram", headers=admin).json()["account_id"] == "999"
    # Never the account of another company.
    r = client.patch(f"/api/system/companies/{other['id']}/instagram", headers=owner,
                     json={"instagram_account_id": "999"})
    assert r.status_code == 409
    # The console's test reports Instagram's answer for this token.
    assert client.post(f"{base}/test", headers=owner).json()["result"] == "token_invalid"
    assert client.get("/api/system/companies/9999/instagram", headers=owner).status_code == 404

    # Messages to the assigned account reach this company.
    scripted([LLMResponse("Hi from Sunrise")])
    post_dm(client, st["webhook_path"], dm("999", "IGSID-3", "Hi"), "s")
    assert fake_ig.sent == [("999", "IGSID-3", "Hi from Sunrise")]
    assert client.get("/api/conversations", headers=admin_b).json() == []

    r = client.patch(base, headers=owner, json={"instagram_account_id": ""})
    assert r.json()["status"] == "not_connected"


def test_suspended_company_gets_no_ai_replies(client, owner, tokens, fake_ig, scripted):
    company, admin = make_company(client, owner, name="Sunrise Travel", admin_email="a@sunrise.com")
    st = connect(client, admin)
    client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"status": "suspended"})
    llm = scripted([LLMResponse("never")])
    post_dm(client, st["webhook_path"], dm(ACCOUNT_A, "IGSID-1", "Hi"))
    assert llm.calls == [] and fake_ig.sent == []


# --- Dashboard ------------------------------------------------------------------------------------


def test_dashboard_counts_instagram_conversations(client, two, fake_ig, scripted):
    scripted([LLMResponse("a"), LLMResponse("b"), LLMResponse("c")])
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi", mid="m1"))
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-2", "Hi", mid="m2"))
    r = client.post("/api/public/companies/sunrise-travel/chats", json={"lang": "en"})
    assert r.status_code == 201, r.text
    a = client.get("/api/dashboard/analytics?days=7", headers=two["a"]).json()
    assert sum(d["instagram"] for d in a["daily"]) == 2
    assert sum(d["web"] for d in a["daily"]) == 1
    assert sum(d["whatsapp"] for d in a["daily"]) == 0
    assert a["funnel"]["conversations"] == 3
    b = client.get("/api/dashboard/analytics?days=7", headers=two["b"]).json()
    assert sum(d["instagram"] for d in b["daily"]) == 0


# --- Database upgrade -----------------------------------------------------------------------------


def test_upgrade_adds_instagram_to_an_existing_database(tmp_path):
    """A database made before Instagram existed gets the columns, indexes and a webhook key per company."""
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name VARCHAR(200), slug VARCHAR(80), status VARCHAR(20), "
            "max_users INTEGER, currency VARCHAR(3), contact_email VARCHAR(200), contact_phone VARCHAR(50), "
            "ai_agent_name VARCHAR(80), ai_welcome_message TEXT, ai_instructions TEXT, knowledge_base TEXT, "
            "whatsapp_phone_number_id VARCHAR(64), whatsapp_access_token TEXT, whatsapp_display_number VARCHAR(50), "
            "created_at TIMESTAMP)"))
        conn.execute(text(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY, company_id INTEGER, name VARCHAR(200), phone VARCHAR(50), "
            "email VARCHAR(200), whatsapp_id VARCHAR(50), created_at TIMESTAMP)"))
        conn.execute(text("INSERT INTO companies (id, name, slug, status, max_users, currency, ai_agent_name, "
                          "ai_instructions, knowledge_base) VALUES (1, 'Old', 'old', 'active', 5, 'OMR', 'Sara', '', ''), "
                          "(2, 'Older', 'older', 'active', 5, 'OMR', 'Sara', '', '')"))
        conn.execute(text("INSERT INTO customers (id, company_id, whatsapp_id) VALUES (1, 1, '968')"))

    upgrade(engine)
    upgrade(engine)  # running it again changes nothing

    insp = inspect(engine)
    columns = {c["name"] for c in insp.get_columns("companies")}
    assert {"instagram_account_id", "instagram_username", "instagram_access_token", "instagram_app_secret",
            "instagram_webhook_key", "instagram_verify_token", "instagram_token_refreshed_at"} <= columns
    assert "instagram_id" in {c["name"] for c in insp.get_columns("customers")}
    indexes = {ix["name"]: ix for t in ("companies", "customers") for ix in insp.get_indexes(t)}
    for name in ("ix_companies_instagram_account_id", "ix_companies_instagram_webhook_key",
                 "uq_customers_company_instagram"):
        assert indexes[name]["unique"]
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT instagram_webhook_key, instagram_verify_token FROM companies")).all()
        assert all(k and v for k, v in rows) and len({k for k, _ in rows}) == 2
        conn.execute(text("INSERT INTO customers (company_id, instagram_id) VALUES (1, 'IG1')"))
        with pytest.raises(Exception):
            conn.execute(text("INSERT INTO customers (company_id, instagram_id) VALUES (1, 'IG1')"))
    engine.dispose()


def test_token_is_renewed_when_it_gets_old(client, two, fake_ig, scripted, monkeypatch):
    scripted([LLMResponse("a"), LLMResponse("b")])
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        return httpx.Response(200, json={"access_token": "tok-a-renewed", "token_type": "bearer",
                                         "expires_in": 5184000})

    monkeypatch.setattr(ig.httpx, "get", fake_get)
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Hi", mid="m1"))
    assert calls == []  # a fresh token is left alone
    with database.SessionLocal() as db:
        company = db.query(Company).filter(Company.name == "Sunrise Travel").one()
        company.instagram_token_refreshed_at = utcnow() - timedelta(days=21)
        db.commit()
    post_dm(client, two["hook_a"], dm(ACCOUNT_A, "IGSID-1", "Again", mid="m2"))
    assert calls == [("https://graph.instagram.com/refresh_access_token",
                      {"grant_type": "ig_refresh_token", "access_token": "tok-a"})]
    with database.SessionLocal() as db:
        company = db.query(Company).filter(Company.name == "Sunrise Travel").one()
        assert company.instagram_access_token == "tok-a-renewed"
        assert utcnow() - company.instagram_token_refreshed_at < timedelta(minutes=1)
