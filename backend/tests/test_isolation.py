"""Customer conversations and company data must never reach another company.

Two companies are filled with packages, a web chat with a booking, a WhatsApp chat, an
employee and an AI training answer. Then every endpoint is tried with the other company's ids.
"""

import hashlib
import hmac
import json

import pytest

from app.ai.llm import LLMResponse, ToolCall
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, future, login, make_company, make_package
from tests.test_whatsapp import meta_stub, wa_payload  # noqa: F401  (meta_stub: autouse fixture)


def _fill(client, admin, slug, scripted, number_id):
    pkg = make_package(client, admin, title=f"{slug} trip")
    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": number_id,
                                                          "whatsapp_access_token": f"EAAG-{slug}"})
    assert r.status_code == 200, r.text
    scripted([
        LLMResponse(None, [ToolCall("q", "quote_booking", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 1}),
            ToolCall("b", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 1,
            "lead_traveler_name": f"Customer of {slug}", "contact_phone": "+968 9999 0000"})]),
        LLMResponse("Booked."),
    ])
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": f"secret plan of {slug}"})
    user = client.post("/api/users", headers=admin, json={
        "email": f"agent@{slug}.com", "full_name": f"Agent {slug}", "password": "Password123", "role": "ticket_agent"
    }).json()
    training = client.post("/api/training", headers=admin, json={"question": "Q?", "answer": f"answer of {slug}"}).json()
    return {
        "package": pkg["id"],
        "token": token,
        "conversation": client.get("/api/conversations", headers=admin).json()[0]["id"],
        "ticket": client.get("/api/tickets", headers=admin).json()[0]["id"],
        "user": user["id"],
        "training": training["id"],
    }


@pytest.fixture
def two_companies(client, owner, scripted):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="admin@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    data_a = _fill(client, admin_a, a["slug"], scripted, "PNID-ALPHA")
    data_b = _fill(client, admin_b, b["slug"], scripted, "PNID-BETA")
    return {"a": (a, admin_a, data_a), "b": (b, admin_b, data_b)}


def test_staff_cannot_reach_other_company_records(client, two_companies):
    _, admin_a, a = two_companies["a"]
    attempts = [
        ("GET", f"/api/packages/{a['package']}", None),
        ("PUT", f"/api/packages/{a['package']}", {"title": "Hacked", "destination": "x", "country": "x",
                                                  "duration_days": 1, "price_per_person": 1}),
        ("DELETE", f"/api/packages/{a['package']}", None),
        ("GET", f"/api/conversations/{a['conversation']}", None),
        ("POST", f"/api/conversations/{a['conversation']}/messages", {"content": "hi"}),
        ("POST", f"/api/conversations/{a['conversation']}/takeover", None),
        ("POST", f"/api/conversations/{a['conversation']}/release", None),
        ("POST", f"/api/conversations/{a['conversation']}/close", None),
        ("GET", f"/api/tickets/{a['ticket']}", None),
        ("PATCH", f"/api/tickets/{a['ticket']}", {"status": "cancelled"}),
        ("PATCH", f"/api/users/{a['user']}", {"full_name": "hacked"}),
        ("DELETE", f"/api/users/{a['user']}", None),
        ("PUT", f"/api/training/{a['training']}", {"question": "x?", "answer": "x"}),
        ("DELETE", f"/api/training/{a['training']}", None),
    ]
    # Company B's admin has every permission inside company B, and none over company A.
    _, admin_b, _ = two_companies["b"]
    for method, path, body in attempts:
        r = client.request(method, path, headers=admin_b, json=body)
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"

    # Nothing of company A changed.
    assert client.get(f"/api/packages/{a['package']}", headers=admin_a).status_code == 200
    detail = client.get(f"/api/conversations/{a['conversation']}", headers=admin_a).json()
    assert detail["status"] == "human" and all(m["sender"] != "agent" for m in detail["messages"])
    assert client.get(f"/api/tickets/{a['ticket']}", headers=admin_a).json()["status"] == "pending_payment"


def test_lists_only_show_own_company(client, two_companies):
    a_company, admin_a, a = two_companies["a"]
    _, admin_b, b = two_companies["b"]
    for path in ("/api/packages", "/api/conversations", "/api/tickets", "/api/training", "/api/team"):
        body = json.dumps(client.get(path, headers=admin_b).json())
        assert "alpha" not in body.lower(), path
    users = client.get("/api/users", headers=admin_b).json()["users"]
    assert all("alpha" not in u["email"] for u in users)
    # Searching for the other company's customer finds nothing.
    assert client.get("/api/conversations", headers=admin_b, params={"q": "alpha"}).json() == []
    assert client.get("/api/tickets", headers=admin_b, params={"q": "alpha"}).json() == []
    # Dashboards count only their own company.
    assert client.get("/api/dashboard", headers=admin_b).json()["tickets_by_status"] == {"pending_payment": 1}


def test_cannot_assign_work_to_other_company_staff(client, two_companies):
    _, admin_a, a = two_companies["a"]
    _, admin_b, b = two_companies["b"]
    r = client.patch(f"/api/tickets/{b['ticket']}", headers=admin_b, json={"assigned_to_id": a["user"]})
    assert r.status_code == 400


def test_web_chat_tokens_only_work_for_their_company(client, two_companies):
    a_company, _, a = two_companies["a"]
    b_company, _, _ = two_companies["b"]
    wrong = f"/api/public/companies/{b_company['slug']}/chats/{a['token']}/messages"
    assert client.get(wrong).status_code == 404
    assert client.post(wrong, json={"content": "hi"}).status_code == 404
    right = f"/api/public/companies/{a_company['slug']}/chats/{a['token']}/messages"
    texts = [m["content"] for m in client.get(right).json()["messages"]]
    assert "secret plan of alpha-travel" in texts
    assert not any("beta" in t.lower() for t in texts)


def test_customers_never_see_internal_messages(client, two_companies):
    a_company, _, a = two_companies["a"]
    messages = client.get(f"/api/public/companies/{a_company['slug']}/chats/{a['token']}/messages").json()["messages"]
    assert {m["sender"] for m in messages} <= {"customer", "ai", "agent"}
    assert not any("Handed over" in m["content"] or "ticket_reference" in m["content"] for m in messages)


def test_platform_owner_cannot_read_customer_chats(client, owner, two_companies):
    _, _, a = two_companies["a"]
    assert client.get("/api/conversations", headers=owner).status_code == 403
    assert client.get(f"/api/conversations/{a['conversation']}", headers=owner).status_code == 403
    assert client.get("/api/tickets", headers=owner).status_code == 403


def test_permissions_limit_what_employees_see(client, two_companies):
    _, admin_a, a = two_companies["a"]
    client.patch(f"/api/users/{a['user']}", headers=admin_a, json={"permissions": ["packages.view"]})
    agent = login(client, "agent@alpha-travel.com", "Password123")
    assert client.get("/api/conversations", headers=agent).status_code == 403
    assert client.get(f"/api/conversations/{a['conversation']}", headers=agent).status_code == 403
    assert client.get("/api/tickets", headers=agent).status_code == 403
    assert client.get("/api/dashboard", headers=agent).status_code == 403
    assert client.get("/api/training", headers=agent).status_code == 403
    assert client.get("/api/packages", headers=agent).status_code == 200


def test_whatsapp_shared_webhook_routes_by_number(client, two_companies, scripted):
    _, admin_a, _ = two_companies["a"]
    _, admin_b, _ = two_companies["b"]
    set_whatsapp_sender(FakeWhatsApp())
    scripted([LLMResponse("Hello Beta customer")])
    client.post("/api/webhooks/whatsapp", json=wa_payload("PNID-BETA", "96890000001", "hi", "wamid.b1"))
    assert [c["channel"] for c in client.get("/api/conversations", headers=admin_b).json()].count("whatsapp") == 1
    assert [c["channel"] for c in client.get("/api/conversations", headers=admin_a).json()].count("whatsapp") == 0


def test_company_webhook_cannot_inject_into_another_company(client, two_companies, scripted):
    """A company that controls its own Meta app secret can only post to its own number."""
    _, admin_a, _ = two_companies["a"]
    _, admin_b, _ = two_companies["b"]
    client.patch("/api/company", headers=admin_a, json={"whatsapp_app_secret": "alpha-secret"})
    path_a = client.get("/api/company", headers=admin_a).json()["whatsapp_webhook_path"]
    set_whatsapp_sender(FakeWhatsApp())
    llm = scripted([LLMResponse("should not answer")])

    body = json.dumps(wa_payload("PNID-BETA", "96890000002", "fake message", "wamid.evil")).encode()
    sig = hmac.new(b"alpha-secret", body, hashlib.sha256).hexdigest()
    r = client.post(path_a, content=body, headers={"X-Hub-Signature-256": f"sha256={sig}",
                                                    "Content-Type": "application/json"})
    assert r.status_code == 200  # accepted by the webhook, but ignored for the other company
    assert llm.calls == []
    assert all(c["channel"] == "web" for c in client.get("/api/conversations", headers=admin_b).json())
