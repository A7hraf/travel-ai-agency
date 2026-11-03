"""Complete business journeys through the HTTP API, as the agencies and their customers live them
(the AI brain is scripted; everything else is the real system)."""

import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.ai.llm import LLMResponse, ToolCall
from app.config import get_settings
from app.database import SessionLocal
from app.models import Conversation, Customer, Message, Ticket, TicketEvent, TrainingExample
from app.services import seats
from app.services import whatsapp as whatsapp_service
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, future, login, make_company, make_package

PUBLIC = "/api/public/companies/{slug}"


# --- helpers ------------------------------------------------------------------------------------


def start_chat(client, slug, **body) -> str:
    r = client.post(f"{PUBLIC.format(slug=slug)}/chats", json=body)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def say(client, slug, token, text) -> dict:
    r = client.post(f"{PUBLIC.format(slug=slug)}/chats/{token}/messages", json={"content": text})
    assert r.status_code == 200, r.text
    return r.json()


def last_tool(messages) -> dict:
    assert messages[-1]["role"] == "tool"
    return json.loads(messages[-1]["content"])


def add_user(client, admin, email, role, permissions=None, password="Password123"):
    body = {"email": email, "full_name": email.split("@")[0].title(), "password": password, "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post("/api/users", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json(), login(client, email, password)


def patch_ticket(client, headers, ticket_id, **body):
    r = client.patch(f"/api/tickets/{ticket_id}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def seats_left(client, admin, pkg_id, date):
    return client.get(f"/api/packages/{pkg_id}", headers=admin).json()["seats_left_by_date"][date]


def quote_call(pkg, date, adults, children=0, cid="q"):
    return ToolCall(cid, "quote_booking", {"package_id": pkg["id"], "departure_date": date,
                                           "adults": adults, "children": children})


def book_call(pkg, date, adults, children=0, name="Salim Al Rawahi", phone="+968 9000 0101", cid="b"):
    return ToolCall(cid, "create_booking_ticket", {
        "package_id": pkg["id"], "departure_date": date, "adults": adults, "children": children,
        "lead_traveler_name": name, "contact_phone": phone})


@pytest.fixture
def agency(client, owner):
    """An Omani agency with an admin, a support employee and a ticket employee."""
    company, admin = make_company(client, owner, name="Muscat Horizons", admin_email="admin@horizons.om",
                                  max_users=6)
    support_user, support = add_user(client, admin, "khalid@horizons.om", "support")
    agent_user, agent = add_user(client, admin, "yousuf@horizons.om", "ticket_agent")
    return {"company": company, "admin": admin, "support": support, "support_user": support_user,
            "agent": agent, "agent_user": agent_user, "slug": company["slug"]}


def maldives(client, admin, **extra):
    return make_package(client, admin, title="Maldives Honeymoon", destination="Malé", country="Maldives",
                        price_per_person=945, child_price=None, tags=["honeymoon", "شهر عسل", "المالديف"],
                        seats_available=8, departure_dates=[future(20), future(48)], **extra)


# --- 1. Web booking in Arabic, finished by the team -----------------------------------------------


def test_arabic_web_booking_until_confirmed_and_dashboard(client, agency, scripted):
    admin, slug = agency["admin"], agency["slug"]
    pkg = maldives(client, admin)
    make_package(client, admin, title="Dubai Family Fun", destination="Dubai", country="UAE",
                 price_per_person=265, child_price=155, tags=["family", "دبي"])
    date = future(20)

    def recommend(messages):
        found = last_tool(messages)["results"]
        assert [p["title"] for p in found] == ["Maldives Honeymoon"]  # Arabic words found the package
        assert found[0]["seats_left"] == {future(20): 8, future(48): 8}
        return LLMResponse(f"عندنا Maldives Honeymoon – 6 أيام – {found[0]['price_per_person']} ر.ع. للشخص")

    def summary(messages):
        q = last_tool(messages)
        assert q["total_price"] == 1890 and q["seats_left_on_date"] == 8
        return LLMResponse("الإجمالي 1890 ر.ع. أأكد الحجز؟")

    def booked(messages):
        return LLMResponse(f"تم! رقم الحجز {last_tool(messages)['ticket_reference']}")

    scripted([
        LLMResponse(None, [ToolCall("s", "search_packages", {"query": "شهر عسل المالديف"})]), recommend,
        LLMResponse(None, [quote_call(pkg, date, 2)]), summary,
        LLMResponse(None, [book_call(pkg, date, 2, name="سالم الرواحي")]), booked,
    ])
    token = start_chat(client, slug, lang="ar")
    out = say(client, slug, token, "ابغى شهر عسل في المالديف")
    assert out["messages"][-1]["cards"][0]["title"] == "Maldives Honeymoon"
    out = say(client, slug, token, f"تمام، {date} لشخصين")
    assert out["messages"][-1]["cards"][0]["type"] == "quote"
    assert out["messages"][-1]["cards"][0]["total_price"] == 1890
    out = say(client, slug, token, "إيه أكدي. سالم الرواحي +968 9000 0101")
    assert out["status"] == "human"
    card = out["messages"][-1]["cards"][0]
    assert card["type"] == "ticket"
    ref = card["ticket_reference"]

    # The team sees the booking with its seats held, and the chat waiting for them.
    dash = client.get("/api/dashboard", headers=admin).json()
    assert dash["tickets_by_status"] == {"pending_payment": 1} and dash["pipeline_value"] == 1890
    assert dash["conversations_waiting"] == 1
    tickets = client.get("/api/tickets", headers=agency["agent"]).json()
    assert len(tickets) == 1 and tickets[0]["reference"] == ref and tickets[0]["seats_held"] == 2
    ticket = tickets[0]
    assert ticket["lead_traveler_name"] == "سالم الرواحي" and ticket["total_price"] == 1890
    assert seats_left(client, admin, pkg["id"], date) == 6

    # Admin assigns it, the ticket employee takes the payment.
    t = patch_ticket(client, admin, ticket["id"], assigned_to_id=agency["agent_user"]["id"])
    assert t["assigned_to"]["full_name"] == "Yousuf"
    t = patch_ticket(client, agency["agent"], ticket["id"], status="in_progress")
    assert t["status"] == "in_progress"
    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agency["agent"], json={"status": "paid"})
    assert r.status_code == 400  # needs the payment reference first
    t = patch_ticket(client, agency["agent"], ticket["id"], payment_reference="BM-TRF-48213", status="paid")
    assert t["status"] == "paid" and t["payment_reference"] == "BM-TRF-48213"
    t = patch_ticket(client, agency["agent"], ticket["id"], status="confirmed")
    assert t["status"] == "confirmed" and t["seats_held"] == 2
    # Support can't change tickets.
    assert client.patch(f"/api/tickets/{ticket['id']}", headers=agency["support"],
                        json={"internal_notes": "x"}).status_code == 403

    events = client.get(f"/api/tickets/{ticket['id']}/events", headers=admin).json()
    assert [e["action"] for e in events] == ["created", "assigned", "status", "payment_reference", "status", "status"]
    assert [(e["old_value"], e["new_value"]) for e in events if e["action"] == "status"] == [
        ("pending_payment", "in_progress"), ("in_progress", "paid"), ("paid", "confirmed")]

    # The conversation keeps the history for the team; the customer never sees internal notes.
    conv = client.get(f"/api/conversations/{ticket['conversation_id']}", headers=admin).json()
    system = [m["content"] for m in conv["messages"] if m["sender"] == "system"]
    assert f"Ticket {ref}: paid → confirmed by Yousuf" in system
    public = client.get(f"{PUBLIC.format(slug=slug)}/chats/{token}/messages").json()["messages"]
    assert all(m["sender"] != "system" for m in public)

    dash = client.get("/api/dashboard", headers=admin).json()
    assert dash["tickets_by_status"] == {"confirmed": 1}
    assert dash["confirmed_value"] == 1890 and dash["pipeline_value"] == 0
    analytics = client.get("/api/dashboard/analytics", headers=admin).json()
    assert analytics["funnel"] == {"conversations": 1, "with_booking": 1, "paid_or_confirmed": 1}
    assert analytics["paid_value"] == 1890 and analytics["top_packages"][0]["title"] == "Maldives Honeymoon"
    assert analytics["handed_to_team"] == 1
    assert seats_left(client, admin, pkg["id"], date) == 6


# --- 2. Customer asks for a person ----------------------------------------------------------------


def test_handover_take_over_reply_hand_back_and_close(client, agency, scripted):
    admin, slug, support = agency["admin"], agency["slug"], agency["support"]
    llm = scripted([
        LLMResponse(None, [ToolCall("h", "request_human_agent", {"reason": "Wants a corporate trip"})]),
        LLMResponse("I've asked one of our consultants to join."),
    ])
    token = start_chat(client, slug, name="Laila")
    out = say(client, slug, token, "Can I talk to a person about a trip for 25 colleagues?")
    assert out["status"] == "human"
    conv = client.get("/api/conversations?status=human", headers=support).json()[0]
    assert conv["handover_reason"] == "Wants a corporate trip" and conv["assigned_to"] is None
    assert client.get("/api/dashboard", headers=admin).json()["conversations_waiting"] == 1

    # While the team has the chat, the AI stays quiet.
    calls = len(llm.calls)
    assert say(client, slug, token, "Hello?")["messages"][-1]["sender"] == "customer"
    assert len(llm.calls) == calls

    r = client.post(f"/api/conversations/{conv['id']}/takeover", headers=support)
    assert r.json()["assigned_to"]["full_name"] == "Khalid"
    assert client.get("/api/dashboard", headers=admin).json()["conversations_waiting"] == 0
    # A colleague can't answer over Khalid's shoulder without forcing it.
    assert client.post(f"/api/conversations/{conv['id']}/messages", headers=admin,
                       json={"content": "Hi"}).status_code == 409
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=support,
                    json={"content": "Hello Laila, this is Khalid. I'll prepare an offer for your group."})
    assert r.status_code == 201
    msgs = client.get(f"{PUBLIC.format(slug=slug)}/chats/{token}/messages").json()["messages"]
    assert msgs[-1]["sender"] == "agent" and "Khalid" in msgs[-1]["content"]

    client.post(f"/api/conversations/{conv['id']}/release", headers=support)
    scripted([LLMResponse("Sure! Anything else I can help with?")])
    out = say(client, slug, token, "Thanks! One more question")
    assert out["status"] == "ai" and out["messages"][-1]["sender"] == "ai"

    r = client.post(f"/api/conversations/{conv['id']}/close", headers=support)
    assert r.json()["status"] == "closed"
    # Writing again reopens the chat with the AI.
    scripted([LLMResponse("Welcome back!")])
    out = say(client, slug, token, "Hi again")
    assert out["status"] == "ai" and out["messages"][-1]["content"] == "Welcome back!"
    detail = client.get(f"/api/conversations/{conv['id']}", headers=admin).json()
    events = [m["content"] for m in detail["messages"] if m["sender"] == "system"]
    assert events == ["Handed over to the team: Wants a corporate trip", "Khalid took over the conversation",
                      "Khalid handed the conversation back to the AI", "Khalid closed the conversation",
                      "The customer wrote again: conversation reopened with the AI"]
    analytics = client.get("/api/dashboard/analytics", headers=admin).json()
    assert analytics["handed_to_team"] == 1 and analytics["handled_by_ai"] == 0


# --- 3. WhatsApp customer (company's own Meta app, signed webhooks) -------------------------------


def wa_payload(number_id, wa_id, text, message_id, name="Hamad"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "96824000000", "phone_number_id": number_id},
        "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
        "messages": [{"from": wa_id, "id": message_id, "timestamp": "1700000000", "type": "text",
                      "text": {"body": text}}]}}]}]}


def signed_post(client, path, payload, secret):
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(path, content=body, headers={"X-Hub-Signature-256": f"sha256={sig}",
                                                    "Content-Type": "application/json"})


def test_whatsapp_customer_books_and_the_team_answers_on_whatsapp(client, agency, scripted, monkeypatch):
    admin = agency["admin"]
    monkeypatch.setattr(whatsapp_service, "verify_phone_number", lambda number_id, token: True)
    r = client.patch("/api/company", headers=admin, json={
        "whatsapp_phone_number_id": "1098765", "whatsapp_access_token": "EAAG-demo",
        "whatsapp_app_secret": "app-secret-1", "whatsapp_display_number": "+968 2400 0000"})
    assert r.status_code == 200
    status = client.get("/api/company/whatsapp", headers=admin).json()
    assert status["status"] == "connected" and status["mode"] == "own"
    hook = status["webhook_path"]
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)

    # The test message button sends through the same sender.
    r = client.post("/api/company/whatsapp/test-message", headers=admin, json={"phone": "+968 9000 0101"})
    assert r.status_code == 200 and wa.sent[-1][1] == "96890000101"
    wa.sent.clear()

    # Unsigned or wrongly signed deliveries are refused.
    payload = wa_payload("1098765", "96890000102", "مرحبا، ابغى عمرة", "wamid.in.1")
    assert client.post(hook, json=payload).status_code == 403
    assert signed_post(client, hook, payload, "wrong-secret").status_code == 403
    assert wa.sent == []

    pkg = make_package(client, admin, title="Umrah Premium", destination="Makkah", country="Saudi Arabia",
                       price_per_person=520, child_price=390, tags=["umrah", "عمرة"], seats_available=40,
                       departure_dates=[future(10), future(31)])
    scripted([
        LLMResponse(None, [ToolCall("s", "search_packages", {"query": "عمرة"})]),
        lambda m: LLMResponse(f"عندنا {last_tool(m)['results'][0]['title']} بـ 520 ر.ع. للشخص"),
        LLMResponse(None, [quote_call(pkg, future(10), 2), book_call(pkg, future(10), 2, name="حمد المسكري",
                                                                     phone="+968 9000 0102")]),
        lambda m: LLMResponse(f"تم الحجز {last_tool(m)['ticket_reference']}"),
    ])
    assert signed_post(client, hook, payload, "app-secret-1").status_code == 200
    assert wa.read == ["wamid.in.1"]
    assert wa.sent == [("1098765", "96890000102", "عندنا Umrah Premium بـ 520 ر.ع. للشخص")]
    # Meta retries the same delivery: it is ignored.
    assert signed_post(client, hook, payload, "app-secret-1").status_code == 200
    assert len(wa.sent) == 1

    second = wa_payload("1098765", "96890000102", "أكد لشخصين بتاريخ " + future(10), "wamid.in.2")
    assert signed_post(client, hook, second, "app-secret-1").status_code == 200
    assert wa.sent[-1][2].startswith("تم الحجز TRV-")
    convs = client.get("/api/conversations?channel=whatsapp", headers=admin).json()
    assert len(convs) == 1 and convs[0]["status"] == "human" and convs[0]["customer"]["name"] == "Hamad"
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    assert ticket["total_price"] == 1040 and ticket["seats_held"] == 2

    # The ticket employee answers on WhatsApp (within the 24-hour window).
    r = client.post(f"/api/conversations/{convs[0]['id']}/messages", headers=agency["agent"],
                    json={"content": "أهلاً حمد، أرسلت لك رابط الدفع"})
    assert r.status_code == 201 and r.json()["delivery_status"] == "sent"
    assert wa.sent[-1] == ("1098765", "96890000102", "أهلاً حمد، أرسلت لك رابط الدفع")
    # Delivery receipts update the message.
    receipt = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "1098765"},
                                                 "statuses": [{"id": f"wamid.out.{len(wa.sent)}",
                                                               "status": "read"}]}}]}]}
    signed_post(client, hook, receipt, "app-secret-1")
    detail = client.get(f"/api/conversations/{convs[0]['id']}", headers=admin).json()
    assert detail["messages"][-1]["delivery_status"] == "read"

    # After 24 hours without a customer message, free replies are refused (Meta's rule).
    with SessionLocal() as db:
        conv = db.get(Conversation, convs[0]["id"])
        conv.last_customer_message_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.commit()
    r = client.post(f"/api/conversations/{convs[0]['id']}/messages", headers=agency["agent"],
                    json={"content": "Hello?"})
    assert r.status_code == 409


def test_platform_webhook_needs_the_platform_secret(client, agency, scripted, monkeypatch):
    """A number on the platform's shared Meta app: messages come signed with the platform's app secret."""
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "platform-secret")
    monkeypatch.setattr(get_settings(), "whatsapp_default_access_token", "EAAG-platform")
    r = client.patch(f"/api/system/companies/{agency['company']['id']}", headers=login(
        client, "owner@example.com", "OwnerPass123!"), json={"whatsapp_phone_number_id": "2223334"})
    assert r.status_code == 200
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    scripted([LLMResponse("Hello! Where would you like to go?")])
    payload = wa_payload("2223334", "96890000103", "Hi", "wamid.p.1")
    assert signed_post(client, "/api/webhooks/whatsapp", payload, "wrong").status_code == 403
    assert signed_post(client, "/api/webhooks/whatsapp", payload, "platform-secret").status_code == 200
    assert wa.sent == [("2223334", "96890000103", "Hello! Where would you like to go?")]


# --- 4. Price change between the quote and the booking ---------------------------------------------


def test_price_change_after_the_quote_needs_a_new_quote(client, agency, scripted):
    admin, slug = agency["admin"], agency["slug"]
    pkg = maldives(client, admin)
    date = future(20)
    scripted([LLMResponse(None, [quote_call(pkg, date, 2)]), LLMResponse("Total 1890 OMR. Confirm?")])
    token = start_chat(client, slug)
    say(client, slug, token, f"Maldives on {date} for 2")

    # The agency raises the price before the customer confirms.
    r = client.put(f"/api/packages/{pkg['id']}", headers=admin, json={**{k: pkg[k] for k in (
        "title", "destination", "country", "description", "duration_days", "child_price", "departure_dates",
        "tags", "seats_available")}, "price_per_person": 990})
    assert r.status_code == 200 and r.json()["price_per_person"] == 990

    seen = {}

    def after_refusal(messages):
        seen["refused"] = last_tool(messages)
        return LLMResponse(None, [quote_call(pkg, date, 2, cid="q2")])

    def new_total(messages):
        seen["quote"] = last_tool(messages)
        return LLMResponse("Sorry, the price changed: the new total is 1980 OMR. Shall I book it?")

    scripted([LLMResponse(None, [book_call(pkg, date, 2)]), after_refusal, new_total])
    out = say(client, slug, token, "Yes, book it")
    assert "price changed" in seen["refused"]["error"] and seen["refused"]["new_total"] == 1980
    assert seen["quote"]["total_price"] == 1980
    assert out["status"] == "ai" and out["messages"][-1]["cards"][0]["total_price"] == 1980
    assert client.get("/api/tickets", headers=admin).json() == []

    scripted([LLMResponse(None, [book_call(pkg, date, 2)]), LLMResponse("Booked.")])
    say(client, slug, token, "OK, 1980 is fine, book it")
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    assert ticket["total_price"] == 1980


# --- 5. Sold-out date ------------------------------------------------------------------------------


def test_sold_out_date_the_ai_offers_the_other_dates(client, agency, scripted):
    admin, slug = agency["admin"], agency["slug"]
    pkg = maldives(client, admin)
    full, other = future(20), future(48)
    scripted([LLMResponse(None, [quote_call(pkg, full, 8), book_call(pkg, full, 8)]), LLMResponse("Booked")])
    say(client, slug, start_chat(client, slug), "Book 8 people")
    assert seats_left(client, admin, pkg["id"], full) == 0

    seen = {}

    def offer(messages):
        seen["quote"] = last_tool(messages)
        return LLMResponse(None, [ToolCall("s", "search_packages", {"query": "Maldives"})])

    def search(messages):
        seen["search"] = last_tool(messages)
        return LLMResponse(f"{full} is sold out, but {other} has seats. Shall I check it?")

    scripted([LLMResponse(None, [quote_call(pkg, full, 2)]), offer, search])
    out = say(client, slug, start_chat(client, slug), f"Maldives on {full} for two")
    assert seen["quote"]["error"] == f"Only 0 seats are left on {full}."
    assert seen["quote"]["dates_with_seats"] == [other]
    result = seen["search"]["results"][0]
    assert result["next_departures"] == [other] and result["seats_left"] == {other: 8}
    assert other in out["messages"][-1]["content"]
    # The customer page shows only the date with seats; the package stays on sale.
    public = client.get(f"{PUBLIC.format(slug=slug)}/packages").json()
    assert [p["title"] for p in public] == ["Maldives Honeymoon"]


# --- 6. Unpaid hold expires after 48 hours, staff re-hold on payment -------------------------------


def test_unpaid_booking_releases_its_seats_after_48_hours_and_staff_re_hold(client, agency, scripted,
                                                                             monkeypatch):
    admin, slug = agency["admin"], agency["slug"]
    pkg = maldives(client, admin)
    date = future(20)
    scripted([LLMResponse(None, [quote_call(pkg, date, 6), book_call(pkg, date, 6)]), LLMResponse("Booked")])
    say(client, slug, start_chat(client, slug), "Book 6")
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    assert ticket["seats_held"] == 6 and seats_left(client, admin, pkg["id"], date) == 2

    # Time travel: 49 hours later nobody paid.
    later = datetime.now(timezone.utc) + timedelta(hours=49)
    monkeypatch.setattr(seats, "_now", lambda: later)
    assert seats_left(client, admin, pkg["id"], date) == 8  # free again even before anyone looks
    listed = client.get(f"/api/tickets/{ticket['id']}", headers=admin).json()
    assert listed["seats_held"] == 0 and listed["seats_released"] is True
    events = client.get(f"/api/tickets/{ticket['id']}/events", headers=admin).json()
    assert events[-1]["action"] == "seats_released" and events[-1]["actor"] == "System"

    # Meanwhile another customer takes 3 seats; 5 are left, enough to re-hold the 6? No: staff get a clear 409.
    scripted([LLMResponse(None, [quote_call(pkg, date, 3), book_call(pkg, date, 3)]), LLMResponse("Booked")])
    say(client, slug, start_chat(client, slug), "Book 3")
    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agency["agent"],
                     json={"status": "paid", "payment_reference": "CARD-1"})
    assert r.status_code == 409 and "released" in r.json()["detail"]
    # The second customer cancels: now the first one can pay and gets the seats back.
    second = next(t for t in client.get("/api/tickets", headers=admin).json() if t["id"] != ticket["id"])
    patch_ticket(client, agency["agent"], second["id"], status="cancelled")
    t = patch_ticket(client, agency["agent"], ticket["id"], status="paid", payment_reference="CARD-1")
    assert t["seats_held"] == 6 and t["seats_released"] is False
    assert seats_left(client, admin, pkg["id"], date) == 2
    # A paid booking never expires.
    monkeypatch.setattr(seats, "_now", lambda: later + timedelta(days=10))
    assert client.get(f"/api/tickets/{ticket['id']}", headers=admin).json()["seats_held"] == 6


# --- 7. Cancellation gives the seats back -----------------------------------------------------------


def test_cancelling_a_paid_booking_gives_the_seats_back(client, agency, scripted):
    admin, slug, agent = agency["admin"], agency["slug"], agency["agent"]
    pkg = make_package(client, admin, title="Georgia", destination="Tbilisi", country="Georgia",
                       price_per_person=365, child_price=260, seats_available=3, departure_dates=[future(18)])
    scripted([LLMResponse(None, [quote_call(pkg, future(18), 2, 1), book_call(pkg, future(18), 2, 1)]),
              LLMResponse("Booked")])
    say(client, slug, start_chat(client, slug), "Georgia for 2 adults and a child")
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    assert ticket["total_price"] == 990
    patch_ticket(client, agent, ticket["id"], status="paid", payment_reference="BD-1")
    # Sold out: the trip disappears from the customer page and the AI search.
    assert client.get(f"{PUBLIC.format(slug=slug)}/packages").json() == []
    t = patch_ticket(client, agent, ticket["id"], status="cancelled")
    assert t["seats_held"] == 0 and t["payment_reference"] is None
    assert seats_left(client, admin, pkg["id"], future(18)) == 3
    assert [p["title"] for p in client.get(f"{PUBLIC.format(slug=slug)}/packages").json()] == ["Georgia"]
    # Only an admin may reopen it, and it takes the seats again.
    assert client.patch(f"/api/tickets/{ticket['id']}", headers=agent,
                        json={"status": "pending_payment"}).status_code == 403
    t = patch_ticket(client, admin, ticket["id"], status="pending_payment")
    assert t["seats_held"] == 3
    dash = client.get("/api/dashboard", headers=admin).json()
    assert dash["tickets_by_status"] == {"pending_payment": 1}


# --- 8. Two customers want the last seats at the same moment ----------------------------------------


class BookingBot:
    """Stateless scripted brain: "BOOK <n> <name>" quotes and books n adults; then reports the result."""

    def __init__(self, pkg, date):
        self.pkg, self.date = pkg, date

    def chat(self, messages, tools):
        last = messages[-1]
        if last["role"] == "user":
            _, n, name = last["content"].split(" ", 2)
            return LLMResponse(None, [quote_call(self.pkg, self.date, int(n)),
                                      book_call(self.pkg, self.date, int(n), name=name)])
        result = json.loads(last["content"])
        return LLMResponse(result.get("ticket_reference") or f"ERROR {result.get('error')}")


def test_two_customers_booking_the_last_seats_at_the_same_time(client, agency):
    from app.ai.llm import set_llm_client

    admin, slug = agency["admin"], agency["slug"]
    pkg = make_package(client, admin, title="Zanzibar", destination="Zanzibar", country="Tanzania",
                       price_per_person=495, seats_available=4, departure_dates=[future(25)])
    set_llm_client(BookingBot(pkg, future(25)))
    tokens = [start_chat(client, slug) for _ in range(2)]
    outcome: dict[int, str] = {}
    barrier = threading.Barrier(2)

    def customer(i):
        barrier.wait()
        outcome[i] = say(client, slug, tokens[i], f"BOOK 3 Customer{i}")["messages"][-1]["content"]

    threads = [threading.Thread(target=customer, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    winners = [o for o in outcome.values() if o.startswith("TRV-")]
    losers = [o for o in outcome.values() if o.startswith("ERROR")]
    assert len(winners) == 1 and len(losers) == 1, outcome
    assert "Only 1 seats" in losers[0]
    tickets = client.get("/api/tickets", headers=admin).json()
    assert len(tickets) == 1 and tickets[0]["seats_held"] == 3
    assert seats_left(client, admin, pkg["id"], future(25)) == 1


# --- 9. Team accounts: the account limit and delegates ----------------------------------------------


def test_company_admin_builds_the_team_within_the_account_limit(client, owner):
    company, admin = make_company(client, owner, name="Small Agency", admin_email="boss@small.om", max_users=3)
    _, support = add_user(client, admin, "s1@small.om", "support")
    # A delegate: a support employee who may manage accounts.
    delegate_user, delegate = add_user(client, admin, "lead@small.om", "support",
                                       permissions=["users.manage", "conversations.view", "conversations.reply",
                                                    "tickets.view"])
    r = client.post("/api/users", headers=admin, json={"email": "s3@small.om", "full_name": "Four",
                                                       "password": "Password123", "role": "support"})
    assert r.status_code == 409 and "Account limit reached (3/3)" in r.json()["detail"]

    # The owner raises the limit; the delegate may add support staff with their own permissions only.
    client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_users": 5})
    r = client.post("/api/users", headers=delegate, json={"email": "admin2@small.om", "full_name": "X",
                                                          "password": "Password123", "role": "company_admin"})
    assert r.status_code == 403
    r = client.post("/api/users", headers=delegate, json={
        "email": "t1@small.om", "full_name": "Tickets", "password": "Password123", "role": "ticket_agent",
        "permissions": ["tickets.view", "tickets.manage"]})
    assert r.status_code == 403 and "tickets.manage" in r.json()["detail"]
    r = client.post("/api/users", headers=delegate, json={
        "email": "t1@small.om", "full_name": "Tickets", "password": "Password123", "role": "support",
        "permissions": ["conversations.view", "tickets.view"]})
    assert r.status_code == 201
    admin_id = next(u["id"] for u in client.get("/api/users", headers=admin).json()["users"]
                    if u["role"] == "company_admin")
    assert client.patch(f"/api/users/{admin_id}", headers=delegate,
                        json={"password": "Hijacked123"}).status_code == 403
    assert client.delete(f"/api/users/{admin_id}", headers=delegate).status_code == 403
    # The company keeps at least one admin.
    assert client.patch(f"/api/users/{admin_id}", headers=admin, json={"is_active": False}).status_code == 400
    # Disabling an employee frees a seat and ends their session.
    s1 = next(u for u in client.get("/api/users", headers=admin).json()["users"] if u["email"] == "s1@small.om")
    client.patch(f"/api/users/{s1['id']}", headers=admin, json={"is_active": False})
    assert client.get("/api/auth/me", headers=support).status_code == 401
    listing = client.get("/api/users", headers=admin).json()
    assert listing["used"] == 3 and listing["max_users"] == 5
    assert delegate_user["role"] == "support"


# --- 10. Suspended company --------------------------------------------------------------------------


def test_suspended_company_page_goes_offline_and_staff_are_logged_out(client, owner, agency, scripted):
    admin, slug = agency["admin"], agency["slug"]
    make_package(client, admin)
    token = start_chat(client, slug)
    cid = agency["company"]["id"]
    r = client.patch(f"/api/system/companies/{cid}", headers=owner, json={"status": "suspended"})
    assert r.json()["status"] == "suspended"
    assert client.get(PUBLIC.format(slug=slug)).status_code == 404
    assert client.get(f"{PUBLIC.format(slug=slug)}/packages").status_code == 404
    r = client.post(f"{PUBLIC.format(slug=slug)}/chats/{token}/messages", json={"content": "hi"})
    assert r.status_code == 404
    for headers in (admin, agency["support"], agency["agent"]):
        r = client.get("/api/auth/me", headers=headers)
        assert r.status_code == 403 and r.json()["detail"] == "Your company account is suspended"
    r = client.post("/api/auth/login", json={"email": "admin@horizons.om", "password": "AdminPass123!"})
    assert r.status_code == 403
    # Reactivated: the page is back, old sessions stay closed, new logins work.
    client.patch(f"/api/system/companies/{cid}", headers=owner, json={"status": "active"})
    assert client.get(PUBLIC.format(slug=slug)).status_code == 200
    assert client.get("/api/auth/me", headers=admin).status_code == 401
    assert client.get("/api/auth/me", headers=login(client, "admin@horizons.om", "AdminPass123!")).status_code == 200


# --- 11. One email, several companies ---------------------------------------------------------------


def test_same_admin_email_in_two_companies_gets_the_login_chooser(client, owner):
    def create(name):
        r = client.post("/api/system/companies", headers=owner, json={
            "name": name, "admin_email": "sam@group.om", "admin_full_name": "Sam", "admin_password": "AdminPass123!"})
        assert r.status_code == 201, r.text
        return r.json()

    a, b = create("Alpha Travel"), create("Beta Tours")
    r = client.post("/api/auth/login", json={"email": "sam@group.om", "password": "AdminPass123!"})
    assert r.status_code == 200 and "access_token" not in r.json()
    choices = {c["account"]: c for c in r.json()["choose"]}
    assert set(choices) == {a["slug"], b["slug"]} and choices[b["slug"]]["company"] == "Beta Tours"
    r = client.post("/api/auth/login", json={"email": "sam@group.om", "password": "AdminPass123!",
                                             "account": b["slug"]})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/company", headers=headers).json()["name"] == "Beta Tours"
    make_package(client, headers, title="Beta only")
    r = client.post("/api/auth/login", json={"email": "sam@group.om", "password": "AdminPass123!",
                                             "account": a["slug"]})
    headers_a = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/packages", headers=headers_a).json() == []


# --- 12. Page editor ----------------------------------------------------------------------------------


def test_page_editor_changes_show_on_the_customer_page(client, agency):
    admin, slug = agency["admin"], agency["slug"]
    r = client.patch("/api/company/branding", headers=admin, json={
        "primary_color": "#a8641f", "accent_color": "#e3b26b", "hero_title_ar": "اكتشف عُمان والعالم",
        "about_en": "Since 2011 in Muscat.", "sections": ["search", "offers", "about", "contact"],
        "elements": {"budget_filter": False, "powered_by": False}, "cards": {"style": "photo", "show_seats": True},
        "texts": {"ar": {"welcome": "هلا! معك {agent} من {company}"}, "en": {"findTrips": "Search"}},
        "dashboard_color": "#ff0000"})
    assert r.status_code == 200
    page = client.get(PUBLIC.format(slug=slug)).json()
    b = page["branding"]
    assert b["primary_color"] == "#a8641f" and b["hero_title_ar"] == "اكتشف عُمان والعالم"
    assert b["sections"] == ["search", "offers", "about", "contact"]
    assert b["elements"]["budget_filter"] is False
    assert b["elements"]["powered_by"] is True  # only the platform owner can hide it
    assert b["cards"]["style"] == "photo" and b["cards"]["show_seats"] is True
    assert b["texts"]["en"] == {"findTrips": "Search"}
    assert "dashboard_color" not in b
    assert client.get("/api/auth/me", headers=admin).json()["company"]["branding"]["dashboard_color"] == "#0088b0"
    # The chat welcome follows the editor, with the names filled in.
    r = client.post(f"{PUBLIC.format(slug=slug)}/chats", json={"lang": "ar"})
    assert r.json()["messages"][0]["content"] == "هلا! معك Sara من Muscat Horizons"
    # Support staff can't change the page.
    assert client.patch("/api/company/branding", headers=agency["support"],
                        json={"primary_color": "#000000"}).status_code == 403


# --- 13. Taught answers and "Try your AI" -------------------------------------------------------------


def test_taught_answer_is_used_by_the_ai_and_try_your_ai_saves_nothing(client, agency, scripted):
    admin, slug = agency["admin"], agency["slug"]
    pkg = maldives(client, admin)
    r = client.post("/api/training", headers=admin, json={
        "question": "هل أقدر أدفع بالتقسيط؟", "answer": "نعم، عربون 30% والباقي على دفعتين شهريتين."})
    assert r.status_code == 201
    client.post("/api/training", headers=admin, json={"question": "Where is your office?",
                                                      "answer": "Al Khuwair, Muscat."})

    llm = scripted([LLMResponse("نعم، عربون 30% والباقي على دفعتين.")])
    token = start_chat(client, slug, lang="ar")
    say(client, slug, token, "ممكن أدفع بالتقسيط؟")
    system_prompt = llm.calls[0][0]["content"]
    assert "عربون 30% والباقي على دفعتين شهريتين" in system_prompt
    assert "Al Khuwair" not in system_prompt  # only the answers close to the question

    def counts():
        with SessionLocal() as db:
            return tuple(db.scalar(select(func.count(m.id))) for m in (Conversation, Customer, Message, Ticket,
                                                                       TicketEvent, TrainingExample))

    before = counts()
    scripted([
        LLMResponse(None, [quote_call(pkg, future(20), 2), book_call(pkg, future(20), 2)]),
        LLMResponse("Booked! Reference TEST-ONLY."),
    ])
    r = client.post("/api/training/try", headers=admin, json={"message": "Book the Maldives for 2 on " + future(20)})
    out = r.json()
    assert out["ok"] and out["simulated"] == ["booking"] and out["cards"][0]["type"] == "ticket"
    assert out["cards"][0]["ticket_reference"] == "TEST-ONLY"
    scripted([LLMResponse(None, [ToolCall("h", "request_human_agent", {"reason": "test"})]), LLMResponse("ok")])
    r = client.post("/api/training/try", headers=admin, json={"message": "I want a person",
                                                              "history": [{"role": "user", "content": "hi"}]})
    assert r.json()["simulated"] == ["handover"]
    assert counts() == before  # no chat, customer, message, ticket or answer was saved
    assert seats_left(client, admin, pkg["id"], future(20)) == 8
    # Only people who manage the AI can use it.
    assert client.post("/api/training/try", headers=agency["support"], json={"message": "hi"}).status_code == 403
