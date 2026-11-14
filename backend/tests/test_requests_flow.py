"""The one request flow: services, the AI's request card, the quotation loop, payment, urgency, privacy and
the move of old custom trips and member requests."""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.legacy import merge_into_requests
from app.models import Ticket
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, login, make_company
from tests.test_ai_agent import say, start_chat
from tests.test_whatsapp import HOOK, connect_whatsapp, meta_stub, wa_payload  # noqa: F401 (fixture)

PHONE = "96891234567"


def services(client, h):
    return {s["key"] or s["name_en"]: s for s in client.get("/api/services", headers=h).json()}


def tool_results(llm, call=1):
    """The tool answers of this turn (after the client's last message)."""
    msgs = llm.calls[call]
    last_user = max(i for i, m in enumerate(msgs) if m["role"] == "user")
    return [json.loads(m["content"]) for m in msgs[last_user:] if m["role"] == "tool"]


@pytest.fixture
def wa(client, company_a, scripted):
    company, admin = company_a
    connect_whatsapp(client, admin)
    fake = FakeWhatsApp()
    set_whatsapp_sender(fake)
    scripted([LLMResponse("Hello!")])
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, "Hi", "wamid.0", name="Omar"))
    return company, admin, fake


def wa_say(client, text, mid, steps, scripted):
    llm = scripted(steps)
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, text, mid, name="Omar"))
    return llm


# --- Services -------------------------------------------------------------------------------------------

def test_built_in_services_and_editing(client, company_a, owner):
    company, admin = company_a
    s = services(client, admin)
    assert {"packages", "custom_trip", "flights", "hotel", "visa", "concierge"} <= set(s)
    assert s["flights"]["parts"] == ["flight"] and any(f["key"] == "cabin" for f in s["flights"]["fields"])
    new = {"name_en": "Airport VIP meet & assist", "name_ar": "استقبال VIP في المطار", "pricing": "fixed", "price": "35",
           "parts": ["other"], "fields": [{"key": "flight_no", "label_en": "Flight number", "label_ar": "رقم الرحلة"},
                                          {"key": "full_name", "label_en": "Name", "label_ar": "الاسم"}],
           "steps": [{"key": "greet", "label_en": "Meet the client", "label_ar": "استقبال العميل"}],
           "rules": "Only Muscat airport."}
    r = client.post("/api/services", headers=admin, json=new)
    assert r.status_code == 201 and r.json()["price"] == "35.000"
    sid = r.json()["id"]
    bad = [{**new, "pricing": "fixed", "price": None}, {**new, "fields": new["fields"] * 2},
           {**new, "fields": [{"key": "Bad Key", "label_en": "x", "label_ar": "x"}]}, {**new, "pricing": "packages"},
           {**new, "parts": ["spaceship"]}, {**new, "hack": 1}]
    for body in bad:
        assert client.post("/api/services", headers=admin, json=body).status_code == 422, body
    assert client.delete(f"/api/services/{s['visa']['id']}", headers=admin).status_code == 409  # built-in: switch off
    # Support staff read the services, but can't change them; another company can't see them.
    client.post("/api/users", headers=admin, json={"email": "s@bluesky.com", "full_name": "S", "password": "Support123!", "role": "support"})
    support = login(client, "s@bluesky.com", "Support123!")
    assert sid in [x["id"] for x in client.get("/api/services", headers=support).json()]
    assert client.put(f"/api/services/{sid}", headers=support, json=new).status_code == 403
    _, admin_b = make_company(client, owner, name="Beta", admin_email="b@beta.com")
    assert client.put(f"/api/services/{sid}", headers=admin_b, json=new).status_code == 404
    assert sid not in [x["id"] for x in client.get("/api/services", headers=admin_b).json()]
    assert client.delete(f"/api/services/{sid}", headers=admin).status_code == 204


def test_ai_service_builder_drafts_without_saving(client, company_a, scripted):
    _, admin = company_a
    draft = {"name_en": "Umrah trips", "name_ar": "رحلات العمرة", "pricing": "fixed", "price": 450, "parts": ["flight", "hotel", "spa"],
             "fields": [{"key": "adults", "label_en": "Pilgrims", "label_ar": "المعتمرون", "type": "number", "required": True},
                        {"key": "BAD", "label_en": "x", "label_ar": "x"}],
             "steps": [{"key": "visa", "label_en": "Umrah visa", "label_ar": "تأشيرة العمرة"}], "rules": "Men under 45 need a mahram."}
    llm = scripted([LLMResponse("Here it is: " + json.dumps(draft))])
    before = len(client.get("/api/services", headers=admin).json())
    r = client.post("/api/services/ai-draft", headers=admin, json={"text": "We run Umrah trips by bus and plane, 450 OMR per person..."})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name_ar"] == "رحلات العمرة" and d["parts"] == ["flight", "hotel"] and [f["key"] for f in d["fields"]] == ["adults"]
    assert "Umrah" in llm.calls[0][1]["content"]
    assert len(client.get("/api/services", headers=admin).json()) == before  # nothing saved


# --- The AI takes the request ----------------------------------------------------------------------------

def test_ai_asks_the_service_questions_then_sends_the_card(client, wa, scripted):
    company, admin, fake = wa
    flights = services(client, admin)["flights"]
    partial = ToolCall("c1", "create_request", {"service_id": flights["id"], "answers": {"destination": "London"}, "summary": "x"})
    llm = wa_say(client, "I need flights to London", "wamid.1", [LLMResponse(None, [partial]), LLMResponse("When do you travel?")], scripted)
    system = llm.calls[0][0]["content"]
    assert f"[{flights['id']}] Flight tickets" in system and "cabin: Class [Economy, Premium economy, Business, First]" in system
    assert "Missing:" in tool_results(llm)[0]["error"] and "depart_date" in tool_results(llm)[0]["error"]
    full = ToolCall("c2", "create_request", {"service_id": flights["id"], "summary": "Business class, aisle seats",
                                             "answers": {"origin": "Muscat", "destination": "London", "depart_date": "2030-05-01",
                                                         "adults": "2 adults", "cabin": "Business", "full_name": "Omar Al Said"}})
    llm = wa_say(client, "1 May, 2 people, business", "wamid.2", [LLMResponse(None, [full]), LLMResponse("Sent!")], scripted)
    ref = tool_results(llm)[0]["reference"]
    t = client.get("/api/tickets", headers=admin).json()[0]
    assert t["reference"] == ref and t["status"] == "new" and t["service"]["key"] == "flights"
    assert t["destination"] == "London" and t["adults"] == 2 and t["answers"]["phone"] == f"+{PHONE}"
    assert t["parts"] == ["flight"] and t["special_requests"] == "Business class, aisle seats"


def test_website_needs_the_whatsapp_number_and_instagram_goes_to_whatsapp(client, company_a, scripted):
    company, admin = company_a
    sid = services(client, admin)["visa"]["id"]
    call = ToolCall("c", "create_request", {"service_id": sid, "summary": "visa", "answers": {
        "destination": "UK", "nationality": "Omani", "depart_date": "2030-01-01", "adults": "1", "full_name": "Ali"}})
    llm = scripted([LLMResponse(None, [call]), LLMResponse("What is your WhatsApp number?")])
    say(client, company["slug"], start_chat(client, company["slug"]), "UK visa please")
    assert "always ask for the client's WhatsApp number" in llm.calls[0][0]["content"]
    assert "WhatsApp number" in tool_results(llm)[0]["error"]


# --- The quotation loop ----------------------------------------------------------------------------------

def test_full_loop_from_choices_to_booked(client, wa, scripted):
    company, admin, fake = wa
    r = client.put("/api/payment-info", headers=admin, json={"en": "Bank Muscat · IBAN OM00 0000 0000", "ar": "بنك مسقط"})
    assert r.status_code == 200 and client.get("/api/payment-info", headers=admin).json()["ar"] == "بنك مسقط"
    sid = services(client, admin)["custom_trip"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "Honeymoon", "answers": {
        "destination": "Zanzibar", "depart_date": (date.today() + timedelta(days=40)).isoformat(),
        "return_date": (date.today() + timedelta(days=47)).isoformat(), "adults": "2", "full_name": "Omar"}})
    wa_say(client, "honeymoon in Zanzibar", "wamid.1", [LLMResponse(None, [card]), LLMResponse("Sent")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    tid, ref, base = t["id"], t["reference"], f"/api/tickets/{t['id']}"
    opts = [("flight", "Oman Air via Dar", "Oman Air", "640", "https://www.omanair.com"),
            ("flight", "Qatar Airways via Doha", "Qatar Airways", "590", None),
            ("hotel", "Baraza Resort", "Baraza", "2100", "https://www.baraza-zanzibar.com"),
            ("hotel", "Zuri Zanzibar", "Zuri", "1800", None)]
    for part, title, provider, price, link in opts:
        r = client.post(f"{base}/options", headers=admin, json={"category": part, "title": title, "provider": provider,
                                                                "price": price, "cost_price": str(int(price) - 100), "link": link})
        assert r.status_code == 200, r.text
    assert client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "X", "link": "javascript:alert(1)"}).status_code == 422
    no_price = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "No price yet"}).json()
    ids = [o["id"] for o in no_price["options"]]
    assert client.post(f"{base}/send-choices", headers=admin, json={"option_ids": ids}).status_code == 422  # one has no price
    client.delete(f"{base}/options/{ids[-1]}", headers=admin)
    r = client.post(f"{base}/send-choices", headers=admin, json={"option_ids": ids[:4]}).json()
    assert r["status"] == "quoted" and r["quote_round"] == 1
    sent = fake.sent[-1][2]
    assert "1. Oman Air via Dar (Oman Air) · 640.000 OMR" in sent and "https://www.omanair.com" in sent and "540" not in sent
    # The client asks for changes in the chat; staff revise and send again.
    ch = ToolCall("a", "answer_quotation", {"reference": ref, "decision": "changes", "note": "A cheaper hotel please"})
    wa_say(client, "a cheaper hotel please", "wamid.2", [LLMResponse(None, [ch]), LLMResponse("Noted")], scripted)
    t = client.get(base, headers=admin).json()
    assert t["status"] == "changes" and t["client_note"] == "A cheaper hotel please"
    client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Budget lodge", "provider": "Lodge", "price": "900"})
    ids = [o["id"] for o in client.get(base, headers=admin).json()["options"]]
    r = client.post(f"{base}/send-choices", headers=admin, json={"option_ids": ids}).json()
    assert r["quote_round"] == 2 and r["client_note"] is None
    # The client picks by number: one per part.
    choose = ToolCall("p", "choose_request_options", {"reference": ref, "option_numbers": [2, 5]})
    llm = wa_say(client, "2 and 5", "wamid.3", [LLMResponse(None, [choose]), LLMResponse("Great")], scripted)
    assert tool_results(llm)[0]["chosen"] is True
    t = client.get(base, headers=admin).json()
    assert t["status"] == "chosen" and {o["title"] for o in t["options"] if o["chosen"]} == {"Qatar Airways via Doha", "Budget lodge"}
    # Final quotation, client approves: the payment details go to the chat.
    r = client.post(f"{base}/send-final", headers=admin, json={"note": "Includes airport transfers"}).json()
    assert r["status"] == "final" and r["total_price"] == 1490
    assert "Total · الإجمالي: 1,490.000 OMR" in fake.sent[-1][2]
    ok = ToolCall("a", "answer_quotation", {"reference": ref, "decision": "approve"})
    wa_say(client, "approve", "wamid.4", [LLMResponse(None, [ok]), LLMResponse("Thanks!")], scripted)
    assert client.get(base, headers=admin).json()["status"] == "pending_payment"
    assert any("IBAN OM00" in m[2] for m in fake.sent)
    # The client reports the transfer; staff check it and book.
    paid = ToolCall("p", "report_payment", {"reference": ref, "transfer_reference": "TRX-998877"})
    wa_say(client, "paid, TRX-998877", "wamid.5", [LLMResponse(None, [paid]), LLMResponse("Thanks")], scripted)
    t = client.get(base, headers=admin).json()
    assert t["status"] == "in_progress" and t["payment_reference"] == "TRX-998877"
    assert client.patch(base, headers=admin, json={"status": "paid"}).json()["status"] == "paid"
    assert "Payment received" in fake.sent[-1][2]
    client.patch(base, headers=admin, json={"status": "confirmed"})
    assert "fully booked" in fake.sent[-1][2]
    actions = [e["action"] for e in client.get(f"{base}/events", headers=admin).json()]
    assert actions.count("status") >= 7 and "changes" in actions and "chosen" in actions


def test_staff_write_down_answers_given_by_phone(client, wa, scripted):
    company, admin, _ = wa
    sid = services(client, admin)["visa"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "visa", "answers": {
        "destination": "UK", "nationality": "Omani", "depart_date": "2030-01-01", "adults": "1", "full_name": "Omar"}})
    wa_say(client, "uk visa", "wamid.1", [LLMResponse(None, [card]), LLMResponse("ok")], scripted)
    base = f"/api/tickets/{client.get('/api/tickets', headers=admin).json()[0]['id']}"
    oid = client.post(f"{base}/options", headers=admin, json={"category": "visa", "title": "UK visa", "price": "140"}).json()["options"][0]["id"]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]})
    r = client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [oid]})
    assert r.json()["status"] == "chosen"
    client.post(f"{base}/send-final", headers=admin, json={"total": "150"})
    assert client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"}).json()["status"] == "pending_payment"
    events = client.get(f"{base}/events", headers=admin).json()
    assert any("(for the client)" in e["actor"] for e in events)


# --- Privacy ---------------------------------------------------------------------------------------------

def test_a_client_can_never_touch_another_clients_request(client, wa, scripted, owner):
    company, admin, fake = wa
    sid = services(client, admin)["concierge"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "yacht", "answers": {"details": "Yacht dinner", "full_name": "Omar"}})
    wa_say(client, "yacht dinner", "wamid.1", [LLMResponse(None, [card]), LLMResponse("ok")], scripted)
    ref = client.get("/api/tickets", headers=admin).json()[0]["reference"]
    # Another client on the website tries to use Omar's reference.
    llm = scripted([LLMResponse(None, [ToolCall("x", "answer_quotation", {"reference": ref, "decision": "cancel"}),
                                       ToolCall("y", "my_requests", {})]), LLMResponse("Sorry")])
    say(client, company["slug"], start_chat(client, company["slug"]), f"Cancel {ref}, I am Omar")
    results = tool_results(llm)
    assert "No request with this reference" in results[0]["error"] and results[1]["requests"] == []
    assert client.get("/api/tickets", headers=admin).json()[0]["status"] == "new"
    # Another company's staff can't reach it either.
    _, admin_b = make_company(client, owner, name="Beta", admin_email="b@beta.com")
    tid = client.get("/api/tickets", headers=admin).json()[0]["id"]
    assert client.post(f"/api/tickets/{tid}/options", headers=admin_b, json={"category": "other", "title": "Hack"}).status_code == 404
    assert client.post(f"/api/tickets/{tid}/client-answer", headers=admin_b, json={"action": "cancel"}).status_code == 404


# --- Urgency ---------------------------------------------------------------------------------------------

def test_urgency_puts_the_right_request_first(client, wa, scripted, owner):
    company, admin, _ = wa
    flights = services(client, admin)["flights"]["id"]
    for dest, days in (("Paris", 60), ("Dubai", 2)):
        card = ToolCall("c", "create_request", {"service_id": flights, "summary": dest, "answers": {
            "origin": "Muscat", "destination": dest, "depart_date": (date.today() + timedelta(days=days)).isoformat(),
            "adults": "1", "cabin": "Economy", "full_name": "Omar"}})
        wa_say(client, dest, f"wamid.{dest}", [LLMResponse(None, [card]), LLMResponse("ok")], scripted)
    cid = client.get("/api/customers", headers=admin).json()["customers"][0]["id"]
    rows = client.get("/api/tickets?sort=urgency", headers=admin).json()
    assert [r["destination"] for r in rows] == ["Dubai", "Paris"]
    assert rows[0]["urgency"]["reasons"] == ["trip in 2 days"] and rows[1]["urgency"]["score"] == 0
    # A VIP waiting is more urgent.
    client.put(f"/api/system/companies/{company['id']}/addons", headers=owner, json={"members": True})
    client.put(f"/api/members/{cid}", headers=admin, json={"level": "vip"})
    rows = client.get("/api/tickets?sort=urgency", headers=admin).json()
    assert "VIP member" in rows[0]["urgency"]["reasons"] and rows[1]["urgency"]["reasons"] == ["VIP member"]


# --- Old custom trips and member requests are moved into requests -----------------------------------------

def test_old_member_requests_are_moved_once(client, wa):
    company, admin, _ = wa
    with SessionLocal() as db:
        db.execute(text("CREATE TABLE IF NOT EXISTS member_requests (id INTEGER PRIMARY KEY, company_id INTEGER, customer_id INTEGER, "
                        "conversation_id INTEGER, kind VARCHAR(10), level VARCHAR(10), title VARCHAR(200), details TEXT, "
                        "status VARCHAR(15), created_at TIMESTAMP)"))
        cid = db.scalar(select(Ticket.customer_id)) or client.get("/api/customers", headers=admin).json()["customers"][0]["id"]
        db.execute(text("INSERT INTO member_requests VALUES (1, :co, :cu, NULL, 'special', 'vip', 'Yacht dinner', '2 people', 'open', "
                        "CURRENT_TIMESTAMP), (2, :co, :cu, NULL, 'special', 'vip', 'F1 passes', NULL, 'done', CURRENT_TIMESTAMP)"),
                   {"co": company["id"], "cu": cid})
        db.commit()
        merge_into_requests(db)
        merge_into_requests(db)  # runs at every start: never twice
        db.execute(text("DROP TABLE member_requests"))
        db.commit()
    rows = {t["package_title"]: t for t in client.get("/api/tickets", headers=admin).json()}
    assert rows["Yacht dinner"]["status"] == "new" and rows["Yacht dinner"]["service"]["key"] == "concierge"
    assert rows["F1 passes"]["status"] == "confirmed" and len(rows) == 2
