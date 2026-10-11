"""WhatsApp Cloud API webhook: verification, routing per company, replies, duplicates."""

import hashlib
import hmac
import json

from app.ai.llm import LLMResponse
from app.config import get_settings
from app.services.whatsapp import set_whatsapp_sender, split_text
from tests.conftest import FakeWhatsApp, make_company, make_package

HOOK = "/api/webhooks/whatsapp"


def wa_payload(phone_number_id, wa_id, text, message_id, name="Omar"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15550001111", "phone_number_id": phone_number_id},
                    "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                    "messages": [{"from": wa_id, "id": message_id, "timestamp": "1700000000",
                                  "type": "text", "text": {"body": text}}],
                },
            }],
        }],
    }


def connect_whatsapp(client, admin, number_id="PNID-A"):
    r = client.patch("/api/company", headers=admin, json={
        "whatsapp_phone_number_id": number_id, "whatsapp_access_token": "EAAG-secret",
        "whatsapp_display_number": "+1 555 000 1111"})
    assert r.status_code == 200
    body = r.json()
    assert body["whatsapp_token_set"] is True
    assert "EAAG-secret" not in json.dumps(body)  # the token is write-only


def test_webhook_verification(client):
    token = get_settings().whatsapp_verify_token
    r = client.get(HOOK, params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"
    r = client.get(HOOK, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert r.status_code == 403


def test_signature_is_checked_when_app_secret_set(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "s3cret")
    body = json.dumps({"entry": []}).encode()
    assert client.post(HOOK, content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    r = client.post(HOOK, content=body, headers={"X-Hub-Signature-256": f"sha256={sig}",
                                                  "Content-Type": "application/json"})
    assert r.status_code == 200


def test_incoming_message_is_answered_by_the_right_company(client, owner, scripted):
    _, admin_a = make_company(client, owner, name="Company A", admin_email="a@a.com")
    _, admin_b = make_company(client, owner, name="Company B", admin_email="b@b.com")
    connect_whatsapp(client, admin_a, "PNID-A")
    connect_whatsapp(client, admin_b, "PNID-B")
    make_package(client, admin_b)
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    llm = scripted([LLMResponse("Hello Omar! Where would you like to go?")])

    assert client.post(HOOK, json=wa_payload("PNID-B", "201001234567", "Hi", "wamid.1")).status_code == 200

    assert wa.sent == [("PNID-B", "201001234567", "Hello Omar! Where would you like to go?")]
    assert wa.read == ["wamid.1"]
    assert "Company B" in llm.calls[0][0]["content"]
    assert "WhatsApp" in llm.calls[0][0]["content"]
    assert "+201001234567" in llm.calls[0][0]["content"]  # phone known from WhatsApp

    assert client.get("/api/conversations", headers=admin_a).json() == []
    conv = client.get("/api/conversations", headers=admin_b).json()[0]
    assert conv["channel"] == "whatsapp"
    assert conv["customer"]["name"] == "Omar"
    assert conv["customer"]["phone"] == "+201001234567"

    # Meta retries the same delivery: it is ignored.
    client.post(HOOK, json=wa_payload("PNID-B", "201001234567", "Hi", "wamid.1"))
    assert len(wa.sent) == 1

    # The next message continues the same conversation.
    scripted([LLMResponse("Great choice!")])
    client.post(HOOK, json=wa_payload("PNID-B", "201001234567", "Maldives", "wamid.2"))
    assert len(client.get("/api/conversations", headers=admin_b).json()) == 1
    assert wa.sent[-1][2] == "Great choice!"


def test_unknown_number_is_ignored(client, company_a, scripted):
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    llm = scripted([LLMResponse("should not be used")])
    client.post(HOOK, json=wa_payload("UNKNOWN", "1", "Hi", "wamid.x"))
    assert wa.sent == [] and llm.calls == []


def test_employee_reply_goes_out_on_whatsapp(client, company_a, scripted):
    _, admin = company_a
    connect_whatsapp(client, admin)
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    scripted([LLMResponse("Hi!")])
    client.post(HOOK, json=wa_payload("PNID-A", "971500000000", "Hi", "wamid.1"))
    conv = client.get("/api/conversations", headers=admin).json()[0]

    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=admin, json={"content": "Payment link: ..."})
    assert r.json()["delivery_status"] == "sent"
    assert wa.sent[-1] == ("PNID-A", "971500000000", "Payment link: ...")

    # Delivery receipts from Meta update the message status.
    sent_id = f"wamid.out.{len(wa.sent)}"
    client.post(HOOK, json={"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "PNID-A"}, "statuses": [{"id": sent_id, "status": "read"}]}}]}]})
    detail = client.get(f"/api/conversations/{conv['id']}", headers=admin).json()
    assert detail["messages"][-1]["delivery_status"] == "read"


def test_failed_send_is_reported(client, company_a, scripted):
    _, admin = company_a
    connect_whatsapp(client, admin)
    set_whatsapp_sender(FakeWhatsApp())
    scripted([LLMResponse("Hi!")])
    client.post(HOOK, json=wa_payload("PNID-A", "971500000000", "Hi", "wamid.1"))
    conv = client.get("/api/conversations", headers=admin).json()[0]
    set_whatsapp_sender(FakeWhatsApp(fail=True))
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=admin, json={"content": "Hello"})
    assert r.json()["delivery_status"] == "failed"


def test_same_number_cannot_be_connected_twice(client, owner):
    _, admin_a = make_company(client, owner, name="Company A", admin_email="a@a.com")
    _, admin_b = make_company(client, owner, name="Company B", admin_email="b@b.com")
    connect_whatsapp(client, admin_a, "PNID-X")
    r = client.patch("/api/company", headers=admin_b, json={"whatsapp_phone_number_id": "PNID-X"})
    assert r.status_code == 409


def test_long_messages_are_split():
    text = ("word " * 2000).strip()
    parts = split_text(text, 4000)
    assert all(len(p) <= 4000 for p in parts)
    assert " ".join(parts) == text
