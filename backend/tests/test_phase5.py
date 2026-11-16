"""Quotation design and photos with AI descriptions, the AI package creator, broadcasts, the check-in in the
middle of a trip, calendar reminder defaults (and the owner's reminders), and analytics levels."""

import base64
from datetime import date, datetime, timedelta, timezone

from app.ai.llm import LLMResponse, ToolCall, set_llm_client
from app.database import SessionLocal
from app.models import Ticket
from app.services.broadcasts import send_checkins
from app.services.calendar import send_reminders
from tests.test_library import switch
from tests.test_requests_flow import PHONE, wa, wa_say  # noqa: F401 (fixture)
from tests.test_team_ops import ai_request, kinds, make_agent
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()


def photo(client, h):
    return client.post("/api/media", headers=h, json={"content_type": "image/png", "data_base64": PNG}).json()["url"]


def test_quotation_design_photos_reference_and_ai_details(client, wa, scripted, owner):
    company, admin, _ = wa
    switch(client, owner, company["id"], quotes=True)
    design = client.get("/api/quote-settings", headers=admin).json()
    saved = client.put("/api/quote-settings", headers=admin, json={**design, "reference_prefix": "q-", "show_item_prices": False}).json()
    assert saved["reference_prefix"] == "q-" and saved["show_item_prices"] is False
    assert client.put("/api/quote-settings", headers=admin, json={**design, "reference_prefix": "Q <b>"}).status_code == 422
    t, base = ai_request(client, admin, scripted)
    set_llm_client(None)  # the AI writer below uses the built-in offline writer
    opt = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Atlantis", "provider": "Atlantis", "price": "900"}).json()["options"][0]
    # Photos: uploaded ones only; several per item, kept after the choices are sent.
    p1, p2 = photo(client, admin), photo(client, admin)
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [opt["id"]]})
    url = f"{base}/options/{opt['id']}/presentation"
    assert client.put(url, headers=admin, json={"photos": ["https://evil.example/x.png"]}).status_code == 422
    t = client.put(url, headers=admin, json={"image_url": p1, "photos": [p2, p2], "details": "Palm island resort"}).json()
    o = t["options"][0]
    assert o["photos"] == [p2] and o["details"] == "Palm island resort"
    q = client.get(f"{base}/quotation", headers=admin).json()
    assert q["items"][0]["photos"] == [p1, p2] and q["reference"] == f"Q-{t['reference']}" and q["design"]["show_item_prices"] is False
    # Another company's photo can't be used.
    _, other = make_company_admin(client, owner)
    assert client.put(url, headers=admin, json={"photos": [photo(client, other)]}).status_code == 422
    # This request's own reference and note; an employee changing the reference tells the admins.
    agent_user, agent = make_agent(client, admin)
    t = client.put(f"{base}/quotation", headers=agent, json={"reference": "dxb-2026-07", "note_en": "Prices held 3 days"}).json()
    assert t["quote_meta"]["reference"] == "DXB-2026-07"
    q = client.get(f"{base}/quotation", headers=admin).json()
    assert q["reference"] == "DXB-2026-07" and q["note_en"] == "Prices held 3 days" and q["request_reference"] == t["reference"]
    assert "reference_changed" in kinds(client, admin)
    # The AI writes the missing descriptions, when the company has it.
    r = client.put(url, headers=admin, json={"image_url": p1, "photos": [p2], "details": ""})
    assert r.status_code == 200 and r.json()["options"][0]["details"] is None, r.text
    assert client.post(f"{base}/quotation/ai-details", headers=admin).status_code == 403
    switch(client, owner, company["id"], quote_writer=True)
    r = client.post(f"{base}/quotation/ai-details", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["options"][0]["details"].startswith("Atlantis")
    assert client.post(f"{base}/quotation/ai-details", headers=admin).status_code == 409


def make_company_admin(client, owner):
    from tests.conftest import make_company

    return make_company(client, owner, name="Other Travel", admin_email="admin@other.com")


def test_ai_package_creator(client, wa, owner):
    company, admin, _ = wa
    set_llm_client(None)
    idea = {"text": "Abu Dhabi Formula 1 weekend, 3 days, grandstand tickets and transfers included."}
    assert client.post("/api/packages/ai-draft", headers=admin, json=idea).status_code == 403
    switch(client, owner, company["id"], package_builder={"on": True, "limit": 1})
    d = client.post("/api/packages/ai-draft", headers=admin, json=idea).json()
    assert d["kind"] == "experience" and d["price_mode"] == "on_request" and d["duration_days"] == 3
    assert client.post("/api/packages/ai-draft", headers=admin, json=idea).status_code == 429  # the monthly limit
    body = {**d, "destination": "Abu Dhabi", "country": "UAE", "departure_dates": []}
    assert client.post("/api/packages", headers=admin, json=body).status_code == 201  # no price: priced on request
    assert client.post("/api/packages", headers=admin, json={**body, "price_mode": "shown"}).status_code == 422


def test_broadcasts_to_a_group(client, wa, scripted, owner):
    company, admin, fake = wa
    ai_request(client, admin, scripted)  # the client has chatted on WhatsApp (window open)
    assert client.post("/api/broadcasts/preview", headers=admin, json={}).status_code == 403
    switch(client, owner, company["id"], broadcasts=True)
    assert client.post("/api/broadcasts/preview", headers=admin, json={}).json()["count"] == 1
    assert client.post("/api/broadcasts/preview", headers=admin, json={"booked": True}).json()["count"] == 0
    assert client.post("/api/broadcasts/preview", headers=admin, json={"tag": "vip"}).json()["count"] == 0
    r = client.post("/api/broadcasts", headers=admin, json={"text_en": "Summer offer: 10% off Salalah", "text_ar": "عرض الصيف"})
    assert r.status_code == 201 and r.json()["sent"] == 1
    assert fake.sent[-1][1] == PHONE and fake.sent[-1][2] == "Summer offer: 10% off Salalah"  # the client writes English
    assert client.get("/api/broadcasts", headers=admin).json()[0]["sent"] == 1
    assert client.post("/api/broadcasts", headers=admin, json={"text_en": "x", "audience": {"booked": True}}).status_code == 409
    _, agent = make_agent(client, admin)
    assert client.post("/api/broadcasts/preview", headers=agent, json={}).status_code == 403


def test_checkin_in_the_middle_of_the_trip(client, wa, scripted):
    company, admin, fake = wa
    t, base = ai_request(client, admin, scripted)
    with SessionLocal() as db:
        ticket = db.get(Ticket, t["id"])
        ticket.status = "confirmed"
        ticket.departure_date = (date.today() - timedelta(days=3)).isoformat()
        ticket.return_date = (date.today() + timedelta(days=3)).isoformat()
        db.commit()
        assert send_checkins(db, date.today()) == 1
        assert send_checkins(db, date.today()) == 0  # once per trip
    assert "How is your trip" in fake.sent[-1][2]
    rec = ToolCall("c", "record_trip_checkin", {"reference": t["reference"], "comment": "The room is not clean", "problem": True})
    llm = wa_say(client, "the room is not clean", "wamid.c1", [LLMResponse(None, [rec]), LLMResponse("Sorry, we are on it")], scripted)
    assert "how their trip" in llm.calls[0][0]["content"]
    assert "client_problem" in kinds(client, admin)
    with SessionLocal() as db:
        assert db.get(Ticket, t["id"]).checkin["problem"] is True


def test_reminder_defaults_and_the_owners_reminder(client, wa, scripted, owner):
    company, admin, fake = wa
    switch(client, owner, company["id"], calendar=True)
    client.patch("/api/auth/profile", headers=admin, json={"whatsapp_number": "+968 9777 1111"})
    agent_user, agent = make_agent(client, admin)
    s = client.put("/api/calendar/settings/reminders", headers=admin,
                   json={"staff_minutes": 120, "client_minutes": 1440, "remind_client": False, "remind_owner": True}).json()
    assert s["staff_minutes"] == 120
    assert client.put("/api/calendar/settings/reminders", headers=agent, json=s).status_code == 403
    t, _ = ai_request(client, admin, scripted)
    starts = (datetime.now(timezone.utc) + timedelta(minutes=90)).isoformat()
    a = client.post("/api/calendar", headers=admin, json={"kind": "airport", "title": "Meet at the airport", "starts_at": starts,
                                                          "ticket_id": t["id"], "assigned_to_id": agent_user["id"]}).json()
    assert a["remind_minutes"] == 120 and a["remind_owner"] is True and a["client_remind_minutes"] == 1440
    with SessionLocal() as db:
        send_reminders(db)
    got = client.get("/api/calendar", headers=admin).json()["appointments"][0]
    assert got["owner_reminded_at"] and got["staff_reminded_at"]  # the owner's WhatsApp: through the template outside 24 h
    assert kinds(client, agent)[0] == "appointment_soon"


def test_analytics_levels(client, wa, scripted, owner):
    company, admin, _ = wa
    switch(client, owner, company["id"], insights={"on": True, "levels": ["basic"]})
    m = client.get("/api/insights", headers=admin).json()["metrics"]
    assert "chats" in m and "packages" not in m and "finance" not in m and "revenue" not in m["bookings"]
    switch(client, owner, company["id"], insights={"on": True, "levels": ["basic", "finance", "deep"]})
    m = client.get("/api/insights", headers=admin).json()["metrics"]
    assert "finance" in m and "revenue" in m["bookings"] and "cancel_reasons" in m and "customers_searched_for" not in m
    switch(client, owner, company["id"], insights={"on": True, "levels": []})
    assert "customers_searched_for" in client.get("/api/insights", headers=admin).json()["metrics"]
