"""The calendar: appointments linked to requests, trips leaving and coming back, and WhatsApp reminders to the
staff member in charge and to the client (inside the 24-hour window, or with the company's approved template)."""

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.services.calendar import send_reminders
from tests.conftest import make_company
from tests.test_library import switch
from tests.test_request_files import hotel_request
from tests.test_requests_flow import PHONE, wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)


def soon(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def remind():
    with SessionLocal() as db:
        return send_reminders(db)


def test_calendar_and_reminders(client, wa, scripted, owner):
    company, admin, fake = wa
    assert client.get("/api/calendar", headers=admin).status_code == 403
    switch(client, owner, company["id"], calendar=True)
    assert client.patch("/api/auth/profile", headers=admin, json={"whatsapp_number": "hello"}).status_code == 422
    me = client.patch("/api/auth/profile", headers=admin, json={"whatsapp_number": "+968 9777 1111"}).json()
    assert me["whatsapp_number"] == "+96897771111"
    tid, ref, base = hotel_request(client, admin, scripted)

    a = client.post("/api/calendar", headers=admin, json={
        "kind": "airport", "title": "Meet at Muscat airport", "starts_at": soon(30), "location": "Arrivals hall",
        "ticket_id": tid, "remind_minutes": 60, "remind_client": True})
    assert a.status_code == 201, a.text
    a = a.json()
    assert a["reference"] == ref and a["client"] == "Omar" and a["assigned_to"]
    cal = client.get("/api/calendar", headers=admin).json()
    assert [x["id"] for x in cal["appointments"]] == [a["id"]]
    assert any(t["kind"] == "departure" and t["reference"] == ref for t in cal["trips"])

    # The staff member never wrote to the company's WhatsApp and there is no template: noted, not sent.
    # The client wrote just now (window open) but client reminders are a separate part, still off.
    before = len(fake.sent)
    assert remind() == 0
    got = client.get("/api/calendar", headers=admin).json()["appointments"][0]
    assert "24-hour window" in got["reminder_note"] and "not switched on" in got["reminder_note"]
    assert len(fake.sent) == before
    assert remind() == 0  # tried once only

    # With the template and client reminders on: a moved appointment is reminded again.
    switch(client, owner, company["id"], calendar_client_reminders=True)
    assert client.put("/api/calendar/settings/template", headers=admin, json={"name": "trip_reminder", "language": "ar"}).status_code == 200
    body = {k: a[k] for k in ("kind", "title", "location", "ticket_id", "remind_minutes", "remind_client")}
    client.put(f"/api/calendar/{a['id']}", headers=admin, json={**body, "starts_at": soon(45)})
    assert remind() == 2
    staff_msg = [m for m in fake.sent if m[1] == "96897771111"][-1][2]
    assert staff_msg.startswith("[template trip_reminder/ar]") and "Meet at Muscat airport" in staff_msg and ref in staff_msg
    client_msg = [m for m in fake.sent if m[1] == PHONE][-1][2]
    assert "Meet at Muscat airport" in client_msg and "تذكير" in client_msg and not client_msg.startswith("[template")
    assert client.get("/api/calendar", headers=admin).json()["appointments"][0]["reminder_note"] is None

    # Not yet due: nothing sent. Another company can't link this request.
    client.post("/api/calendar", headers=admin, json={"title": "Visa paperwork", "starts_at": soon(600)})
    assert remind() == 0
    other, other_admin = make_company(client, owner, name="Other Co", admin_email="admin@other.com")
    switch(client, owner, other["id"], calendar=True)
    assert client.post("/api/calendar", headers=other_admin, json={"title": "Meeting", "starts_at": soon(10), "ticket_id": tid}).status_code == 404
    assert client.put(f"/api/calendar/{a['id']}", headers=other_admin, json={**body, "starts_at": soon(45)}).status_code == 404
    assert client.post("/api/calendar", headers=admin, json={"title": "No zone", "starts_at": "2026-12-01T10:00:00"}).status_code == 422
