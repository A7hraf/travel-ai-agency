"""AI training page (answers, import, knowledge, "Try your AI") and the WhatsApp connection steps."""

import pytest
from sqlalchemy import func, select

from app.ai.llm import LLMError, LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import Conversation, Customer, Message, Ticket
from app.services import whatsapp as whatsapp_service
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, login, make_company, make_package

TRY = "/api/training/try"


def counts() -> tuple[int, int, int, int]:
    with SessionLocal() as db:
        return tuple(db.scalar(select(func.count(m.id))) or 0 for m in (Conversation, Customer, Ticket, Message))


def staff(client, admin, role, email):
    r = client.post("/api/users", headers=admin, json={"email": email, "full_name": "Staff", "password": "Password123",
                                                       "role": role})
    assert r.status_code == 201, r.text
    return login(client, email, "Password123")


# --- Try your AI --------------------------------------------------------------------------


def test_try_ai_uses_packages_and_answers_and_saves_nothing(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    taught = client.post("/api/training", headers=admin, json={
        "question": "Do you offer installments?", "answer": "Yes, 3 monthly payments."}).json()
    llm = scripted([
        LLMResponse(None, [ToolCall("c1", "search_packages", {"query": "Maldives"})]),
        LLMResponse("We have the Maldives Honeymoon. Yes, 3 monthly payments."),
    ])
    before = counts()
    r = client.post(TRY, headers=admin, json={"message": "Maldives with installments?"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] and "Maldives" in data["reply"]
    assert [a["id"] for a in data["used_answers"]] == [taught["id"]]
    assert [p["id"] for p in data["packages"]] == [pkg["id"]]
    assert data["tools"] == ["search_packages"] and data["simulated"] == []
    assert "3 monthly payments" in llm.calls[0][0]["content"]  # the taught answer is in the prompt
    assert counts() == before


def test_try_ai_cannot_book_or_hand_over(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    dep = pkg["departure_dates"][0]
    booking = {"package_id": pkg["id"], "departure_date": dep, "adults": 2, "children": 0}
    scripted([
        LLMResponse(None, [ToolCall("q", "quote_booking", booking)]),
        LLMResponse(None, [ToolCall("b", "create_booking_ticket", {
            **booking, "lead_traveler_name": "Test Person", "contact_phone": "+96891234567"})]),
        LLMResponse(None, [ToolCall("h", "request_human_agent", {"reason": "test"})]),
        LLMResponse("Booked! Reference TEST-ONLY."),
    ])
    before = counts()
    data = client.post(TRY, headers=admin, json={"message": "Book it for 2 adults",
                                                 "history": [{"role": "user", "content": "Maldives?"},
                                                             {"role": "assistant", "content": "Yes!"}]}).json()
    assert data["ok"]
    assert data["simulated"] == ["booking", "handover"]
    assert counts() == before  # no conversation, customer, ticket (so no seat hold) or message


def test_try_ai_when_the_ai_is_down(client, company_a, scripted):
    _, admin = company_a
    scripted([LLMError("Provider down")])
    before = counts()
    data = client.post(TRY, headers=admin, json={"message": "hello"}).json()
    assert data["ok"] is False and data["error"] == "Provider down" and data["reply"] is None
    assert counts() == before


def test_try_ai_only_uses_own_company_data(client, owner, company_a, scripted):
    _, admin_a = company_a
    _, admin_b = make_company(client, owner, name="Other Travel", admin_email="admin@other.com")
    make_package(client, admin_b, title="Secret Paris Trip", destination="Paris", country="France", tags=["city"])
    client.post("/api/training", headers=admin_b, json={"question": "Paris discount?", "answer": "SECRET-B"})
    scripted([LLMResponse(None, [ToolCall("c1", "search_packages", {"query": "Paris"})]),
              LLMResponse("Nothing for Paris.")])
    llm_calls = client.post(TRY, headers=admin_a, json={"message": "Paris discount?"}).json()
    assert llm_calls["used_answers"] == [] and all(p["title"] != "Secret Paris Trip" for p in llm_calls["packages"])


def test_try_ai_permissions_and_rate_limit(client, company_a, scripted):
    _, admin = company_a
    for role, email in (("support", "s@bluesky.com"), ("ticket_agent", "t@bluesky.com")):
        headers = staff(client, admin, role, email)
        assert client.post(TRY, headers=headers, json={"message": "hi"}).status_code == 403
        assert client.get("/api/training/knowledge", headers=headers).status_code == 403
        assert client.post("/api/training/import", headers=headers, json={"text": "a b | c"}).status_code == 403
    scripted([LLMResponse("Hi")] * 25)
    codes = [client.post(TRY, headers=admin, json={"message": "hi"}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


# --- Import and knowledge -----------------------------------------------------------------


def test_bulk_import_preview_and_save(client, company_a):
    _, admin = company_a
    client.post("/api/training", headers=admin, json={"question": "Visa for Turkey?", "answer": "e-Visa."})
    text = "question | answer\nDo you take cards? | Yes, all cards.\nvisa for turkey? | dup\nno separator here\n" \
           "x | too short question\n"
    preview = client.post("/api/training/import", headers=admin, json={"text": text, "preview": True}).json()
    assert preview["added"] == 0 and [r["question"] for r in preview["rows"]] == ["Do you take cards?"]
    assert [d["line"] for d in preview["duplicates"]] == [3]
    assert [p["line"] for p in preview["problems"]] == [4, 5]
    assert len(client.get("/api/training", headers=admin).json()) == 1
    saved = client.post("/api/training/import", headers=admin, json={"text": text}).json()
    assert saved["added"] == 1 and len(client.get("/api/training", headers=admin).json()) == 2


def test_bulk_import_csv_and_limits(client, company_a, monkeypatch):
    _, admin = company_a
    csv_text = 'Question,Answer\n"Hotel, or apartment?","Both, as you like"\nKids free?,Under 2 free\n'
    r = client.post("/api/training/import", headers=admin, json={"text": csv_text}).json()
    assert r["added"] == 2 and r["rows"][0]["answer"] == "Both, as you like"
    too_many = "\n".join(f"Question {i} | Answer {i}" for i in range(201))
    r = client.post("/api/training/import", headers=admin, json={"text": too_many})
    assert r.status_code == 400 and "at most 200" in r.json()["detail"]
    assert client.post("/api/training/import", headers=admin, json={"text": "  \n "}).status_code == 400
    from app.ai import training

    monkeypatch.setattr(training, "MAX_EXAMPLES_PER_COMPANY", 3)
    r = client.post("/api/training/import", headers=admin, json={"text": "Q one? | A\nQ two? | B"})
    assert r.status_code == 409


def test_knowledge_edit(client, company_a):
    _, admin = company_a
    r = client.patch("/api/training/knowledge", headers=admin, json={
        "ai_agent_name": "  ", "knowledge_base": "Deposit 20%", "ai_welcome_message_ar": "أهلاً"})
    assert r.status_code == 200
    data = r.json()
    assert data["ai_agent_name"] == "Sara" and data["knowledge_base"] == "Deposit 20%"
    assert client.get("/api/company", headers=admin).json()["ai_welcome_message_ar"] == "أهلاً"


# --- Platform owner -----------------------------------------------------------------------


def test_owner_trains_any_company_and_admins_are_refused(client, owner, company_a, scripted):
    company, admin = company_a
    other, admin_b = make_company(client, owner, name="Other Travel", admin_email="admin@other.com")
    base = f"/api/system/companies/{company['id']}/training"
    added = client.post(base, headers=owner, json={"question": "Office hours?", "answer": "9 to 5"}).json()
    assert [e["question"] for e in client.get("/api/training", headers=admin).json()] == ["Office hours?"]
    assert client.get("/api/training", headers=admin_b).json() == []
    # Example ids are checked against the company in the path.
    assert client.put(f"/api/system/companies/{other['id']}/training/{added['id']}", headers=owner,
                      json={"question": "x?", "answer": "y"}).status_code == 404
    assert client.put(f"{base}/{added['id']}", headers=owner, json={"question": "Hours?", "answer": "9-5"}).status_code == 200
    assert client.post(f"{base}/import", headers=owner, json={"text": "Parking? | Yes"}).json()["added"] == 1
    assert client.patch(f"{base}/knowledge", headers=owner, json={"knowledge_base": "Owner wrote"}).status_code == 200
    assert client.get("/api/training/knowledge", headers=admin).json()["knowledge_base"] == "Owner wrote"
    scripted([LLMResponse("We open 9-5")])
    before = counts()
    assert client.post(f"{base}/try", headers=owner, json={"message": "Hours?"}).json()["reply"] == "We open 9-5"
    assert counts() == before
    assert client.delete(f"{base}/{added['id']}", headers=owner).status_code == 204
    assert client.get("/api/system/companies/9999/training", headers=owner).status_code == 404
    for path in ("training", "training/knowledge", "whatsapp"):
        assert client.get(f"/api/system/companies/{company['id']}/{path}", headers=admin).status_code == 403
    assert client.post(f"{base}/try", headers=admin, json={"message": "hi"}).status_code == 403
    assert client.post(f"/api/system/companies/{company['id']}/whatsapp/test", headers=admin).status_code == 403


# --- WhatsApp -----------------------------------------------------------------------------


@pytest.fixture
def meta(monkeypatch):
    """Meta's answer to the number check, by token."""
    answers = {"good": {"result": "connected", "message": whatsapp_service.CHECK_MESSAGES["connected"],
                        "display_number": "+968 9000 0000", "verified_name": "Blue Sky"}}

    def fake_check(number, token, fields="id"):
        if not number or not token:
            return {"result": "not_configured", "message": whatsapp_service.CHECK_MESSAGES["not_configured"]}
        return answers.get(token) or {"result": token, "message": whatsapp_service.CHECK_MESSAGES[token]}

    monkeypatch.setattr(whatsapp_service, "check_phone_number", fake_check)
    return answers


def test_whatsapp_status_and_test_connection(client, company_a, meta):
    _, admin = company_a
    status = client.get("/api/company/whatsapp", headers=admin).json()
    assert status["status"] == "not_connected" and status["webhook_path"].startswith("/api/webhooks/whatsapp/c/")
    assert status["verify_token"]
    assert client.post("/api/company/whatsapp/test", headers=admin).json()["result"] == "not_configured"

    assert client.patch("/api/company", headers=admin, json={"whatsapp_access_token": "good",
                                                             "whatsapp_phone_number_id": "111"}).status_code == 200
    r = client.post("/api/company/whatsapp/test", headers=admin).json()
    assert r["result"] == "connected" and r["display_number"] == "+968 9000 0000"
    assert r["status"]["status"] == "needs_app_secret"
    client.patch("/api/company", headers=admin, json={"whatsapp_app_secret": "s3cret"})
    assert client.get("/api/company/whatsapp", headers=admin).json()["status"] == "connected"

    for token in ("token_invalid", "number_not_found", "network", "no_access"):
        client.patch("/api/company", headers=admin, json={"whatsapp_access_token": token})
        assert client.post("/api/company/whatsapp/test", headers=admin).json()["result"] == token


def test_number_check_maps_meta_errors(monkeypatch):
    import httpx

    def answer(status, body):
        return lambda *a, **k: httpx.Response(status, json=body)

    cases = [
        (answer(200, {"id": "5", "display_phone_number": "+1 555"}), "connected"),
        (answer(401, {"error": {"code": 190, "message": "expired"}}), "token_invalid"),
        (answer(400, {"error": {"code": 100, "message": "Unsupported get request"}}), "number_not_found"),
        (answer(403, {"error": {"code": 200, "message": "Permission"}}), "no_access"),
    ]
    for fake, expected in cases:
        monkeypatch.setattr(whatsapp_service.httpx, "get", fake)
        assert whatsapp_service.check_phone_number("5", "t")["result"] == expected

    def down(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(whatsapp_service.httpx, "get", down)
    assert whatsapp_service.check_phone_number("5", "t")["result"] == "network"


def test_whatsapp_test_message(client, company_a, meta):
    _, admin = company_a
    path = "/api/company/whatsapp/test-message"
    assert client.post(path, headers=admin, json={"phone": "+968 9123 4567"}).status_code == 400  # not connected
    client.patch("/api/company", headers=admin, json={"whatsapp_access_token": "good", "whatsapp_phone_number_id": "111"})
    assert client.post(path, headers=admin, json={"phone": "hello world"}).status_code == 400
    fake = FakeWhatsApp()
    set_whatsapp_sender(fake)
    r = client.post(path, headers=admin, json={"phone": "+968 9123-4567"})
    assert r.status_code == 200 and r.json()["to"] == "+96891234567"
    assert fake.sent[0][:2] == ("111", "96891234567")
    assert client.post(path, headers=admin, json={"phone": "0096891234567"}).status_code == 200
    assert client.post(path, headers=admin, json={"phone": "+96891234567"}).status_code == 429  # 2 per minute
    assert len(fake.sent) == 2
    set_whatsapp_sender(FakeWhatsApp(fail=True))
    support = staff(client, admin, "support", "s@bluesky.com")
    assert client.post(path, headers=support, json={"phone": "+96891234567"}).status_code == 403


def test_whatsapp_test_message_failure_is_explained(client, company_a, meta):
    _, admin = company_a
    client.patch("/api/company", headers=admin, json={"whatsapp_access_token": "good", "whatsapp_phone_number_id": "111"})
    set_whatsapp_sender(FakeWhatsApp(fail=True))
    r = client.post("/api/company/whatsapp/test-message", headers=admin, json={"phone": "+96891234567"})
    assert r.status_code == 502 and "24 hours" in r.json()["detail"]


def test_owner_whatsapp_tab(client, owner, company_a, meta):
    company, admin = company_a
    base = f"/api/system/companies/{company['id']}"
    assert client.patch(base, headers=owner, json={"whatsapp_phone_number_id": "222"}).status_code == 200
    status = client.get(f"{base}/whatsapp", headers=owner).json()
    assert status["mode"] == "platform" and status["phone_number_id"] == "222"
    assert client.get("/api/company/whatsapp", headers=admin).json()["mode"] == "platform"
    assert client.post(f"{base}/whatsapp/test", headers=owner).status_code == 200
    assert client.get("/api/system/companies/9999/whatsapp", headers=owner).status_code == 404


def test_try_ai_needs_a_message(client, company_a):
    _, admin = company_a
    assert client.post(TRY, headers=admin, json={"message": ""}).status_code == 422
