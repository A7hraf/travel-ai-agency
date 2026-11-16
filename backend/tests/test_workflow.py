"""Request workflows: default steps per service, the owner's own steps, one request's own steps, payments in
installments (before or after the service), appointments, and closing with who, why and at which step."""

from datetime import date, timedelta

from app import workflow
from app.database import SessionLocal
from app.models import Ticket
from tests.test_library import switch
from tests.test_request_files import JPEG, b64
from tests.test_requests_flow import PHONE, services, wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

IN_30 = (date.today() + timedelta(days=30)).isoformat()
IN_35 = (date.today() + timedelta(days=35)).isoformat()


def new_request(client, admin, key, answers):
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)[key]["id"], "name": "Omar", "phone": "+" + PHONE,
        "answers": answers, "summary": "Test"})
    assert r.status_code == 201, r.text
    return r.json(), f"/api/tickets/{r.json()['id']}"


def quote_and_approve(client, admin, base, part, price):
    oid = client.post(f"{base}/options", headers=admin, json={"category": part, "title": "Choice", "price": price}).json()["options"][0]["id"]
    assert client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]}).status_code == 200
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [oid]})
    client.post(f"{base}/send-final", headers=admin, json={})
    return client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"}).json()


def steps_of(t):
    return [(s["key"], s["state"]) for s in t["process"]["steps"]]


TRIP = {"destination": "Georgia", "depart_date": IN_30, "return_date": IN_35, "adults": "1", "full_name": "Omar",
        "phone": "+" + PHONE}


def test_every_service_has_a_default_workflow_and_the_owner_can_change_it(client, wa):
    _, admin, _ = wa
    svc = services(client, admin)
    for key in ("packages", "custom_trip", "flights", "hotel", "visa", "embassy", "airport_assist", "airport_transfer", "concierge"):
        assert svc[key]["workflow"] and svc[key]["workflow_custom"] is False, key
    assert [s["type"] for s in svc["embassy"]["workflow"]] == ["intake", "review", "documents", "schedule", "payment", "task", "feedback"]
    hotel = {k: v for k, v in svc["hotel"].items() if k not in ("id", "key", "position", "workflow_custom")}
    url = f"/api/services/{svc['hotel']['id']}"
    # Rules: one intake and it comes first, payments add up to at most 100% and the last one is the rest.
    bad = [
        [{"key": "review", "type": "review"}, {"key": "intake", "type": "intake"}],
        [{"key": "a", "type": "payment", "pay_mode": "percent", "pay_value": 70}, {"key": "b", "type": "payment", "pay_mode": "percent", "pay_value": 50}],
        [{"key": "a", "type": "payment", "pay_mode": "percent", "pay_value": 50}],
        [{"key": "a", "type": "booking"}, {"key": "b", "type": "booking"}],
    ]
    for steps in bad:
        assert client.put(url, headers=admin, json={**hotel, "workflow": steps}).status_code == 422, steps
    deposit_first = [{"key": "intake", "type": "intake"}, {"key": "deposit", "type": "payment", "pay_mode": "percent", "pay_value": 20},
                     {"key": "review", "type": "review"}, {"key": "quote", "type": "quote"},
                     {"key": "balance", "type": "payment", "label_en": "Balance", "label_ar": "الباقي"},
                     {"key": "booking", "type": "booking"}]
    saved = client.put(url, headers=admin, json={**hotel, "workflow": deposit_first}).json()
    assert saved["workflow_custom"] and [s["key"] for s in saved["workflow"]] == [s["key"] for s in deposit_first]
    assert saved["workflow"][1]["label_ar"] == "الدفع"  # a label left empty gets the step's own name
    # Saving the default again puts the service back on the default.
    again = client.put(url, headers=admin, json={**hotel, "workflow": hotel["workflow"]}).json()
    assert again["workflow_custom"] is False
    # Saving the service without its workflow keeps it.
    client.put(url, headers=admin, json={**hotel, "workflow": deposit_first})
    rest = {k: v for k, v in hotel.items() if k != "workflow"}
    assert client.put(url, headers=admin, json=rest).json()["workflow_custom"] is True


def test_documents_then_deposit_then_balance_after_the_documents(client, wa):
    _, admin, fake = wa
    t, base = new_request(client, admin, "custom_trip", TRIP)
    assert t["status"] == "new" and t["current_step"]["type"] == "review"  # every answer given: details done
    # This request pays 30% before the booking and the rest after the travel documents.
    steps = [{k: s[k] for k in ("key", "type", "label_en", "label_ar", "pay_mode", "pay_value")}
             for s in client.get(base, headers=admin).json()["process"]["steps"]]
    pay = next(i for i, s in enumerate(steps) if s["type"] == "payment")
    steps[pay].update(key="deposit", pay_mode="percent", pay_value=30, label_en="Deposit", label_ar="العربون")
    steps.insert(next(i for i, s in enumerate(steps) if s["type"] == "delivery") + 1,
                 {"key": "balance", "type": "payment", "pay_mode": "rest", "label_en": "Balance", "label_ar": "الباقي"})
    t = client.put(f"{base}/workflow", headers=admin, json={"steps": steps}).json()
    assert [i["amount"] for i in t["process"]["installments"]] == [0, 0]  # no price yet

    # Sending choices passes the team review; the client approves the final quotation.
    t = quote_and_approve(client, admin, base, "hotel", "1000")
    assert t["status"] == "working" and t["current_step"]["type"] == "documents"
    assert [i["amount"] for i in t["process"]["installments"]] == [300, 700]
    assert "Passport copy" in fake.sent[-1][2]
    # The passport arrives: the documents step finishes by itself and the client is asked for the deposit.
    t = client.post(f"{base}/files", headers=admin, json={"kind": "client_file", "name": "passport.jpg",
                                                          "content_type": "image/jpeg", "data_base64": b64(JPEG)}).json()
    fid = t["request_files"][-1]["id"]
    t = client.patch(f"{base}/files/{fid}", headers=admin, json={"kind": "client_file", "requirement": "passport"}).json()
    assert t["status"] == "pending_payment" and t["process"]["due_now"] == 300
    assert "300.000 OMR" in fake.sent[-1][2] and "1,000.000 OMR" in fake.sent[-1][2]
    # Part of the deposit: still waiting; the whole deposit: the booking starts, the client hears it.
    t = client.post(f"{base}/payments", headers=admin, json={"amount": "100", "reference": "TRX-1"}).json()
    assert t["status"] == "in_progress" and t["process"]["due_now"] == 200
    t = client.post(f"{base}/payments", headers=admin, json={"amount": "200", "reference": "TRX-2"}).json()
    assert t["status"] == "paid" and t["current_step"]["type"] == "booking" and "Payment received" in fake.sent[-1][2]
    # Booking, then the travel documents: the balance is asked for after them.
    for step in t["booking_steps"]:
        if step["key"] != "documents":
            t = client.post(f"{base}/checklist", headers=admin, json={"step": step["key"], "done": True}).json()
    assert t["current_step"]["type"] == "delivery"
    t = client.post(f"{base}/files", headers=admin, json={"kind": "document", "name": "ticket.pdf", "content_type": "application/pdf",
                                                          "data_base64": b64(b"%PDF-1.4 test")}).json()
    t = client.post(f"{base}/send-documents", headers=admin, json={}).json()
    assert t["status"] == "pending_payment" and t["current_step"]["key"] == "balance" and t["process"]["due_now"] == 700
    t = client.post(f"{base}/payments", headers=admin, json={"amount": "700", "reference": "TRX-3"}).json()
    assert t["status"] == "confirmed" and t["current_step"]["type"] == "trip" and t["payment_reference"] == "TRX-3"
    # The trip ends: the feedback step; the client's rating finishes the request.
    with SessionLocal() as db:
        assert workflow.pass_finished_trips(db, date.today() + timedelta(days=40)) == 1
        ticket = db.get(Ticket, t["id"])
        assert workflow.active(ticket)["type"] == "feedback" and ticket.status == "confirmed"
    events = [e["action"] for e in client.get(f"{base}/events", headers=admin).json()]
    assert events.count("step_done") >= 6 and "workflow_changed" in events


def test_payment_after_the_service_and_what_only_an_admin_can_pass(client, wa, company_a):
    _, admin, _ = wa
    t, base = new_request(client, admin, "concierge", {"details": "Dinner on a dhow", "full_name": "Omar", "phone": "+" + PHONE})
    steps = [{k: s[k] for k in ("key", "type", "label_en", "label_ar")} for s in t["process"]["steps"]]
    order = {s["type"]: s for s in steps}
    steps = [order[k] for k in ("intake", "review", "quote", "booking", "payment", "feedback")]
    t = client.put(f"{base}/workflow", headers=admin, json={"steps": steps}).json()
    # Done steps can't be moved or removed.
    assert client.put(f"{base}/workflow", headers=admin, json={"steps": steps[1:]}).status_code == 422
    t = quote_and_approve(client, admin, base, "other", "250")
    assert t["status"] == "working" and t["current_step"]["type"] == "booking"  # no payment before the service
    assert client.post(f"{base}/workflow/done", headers=admin, json={"key": "payment"}).status_code == 409
    t = client.post(f"{base}/workflow/done", headers=admin, json={"key": "booking", "note": "Table booked"}).json()
    assert t["status"] == "pending_payment" and t["process"]["due_now"] == 250
    # An employee can't pass a payment that was not made; a company admin can (paid outside the system).
    r = client.post("/api/users", headers=admin, json={"email": "agent@bluesky.com", "full_name": "Agent", "password": "AgentPass123!",
                                                       "role": "ticket_agent"})
    assert r.status_code == 201, r.text
    agent = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": "agent@bluesky.com", "password": "AgentPass123!"}).json()["access_token"]}
    assert client.post(f"{base}/workflow/done", headers=agent, json={"key": "payment"}).status_code == 403
    t = client.post(f"{base}/workflow/done", headers=admin, json={"key": "payment", "note": "Paid in cash at the office"}).json()
    assert t["status"] == "confirmed" and t["current_step"]["type"] == "feedback"
    assert next(s for s in t["process"]["steps"] if s["key"] == "payment")["note"] == "Paid in cash at the office"


def test_embassy_appointment_from_the_clients_times_to_the_calendar(client, wa, owner):
    company, admin, fake = wa
    switch(client, owner, company["id"], calendar=True)
    t, base = new_request(client, admin, "embassy", {
        "destination": "Germany", "nationality": "Omani", "purpose": "Visa interview", "preferred_times": "Sunday morning",
        "adults": "1", "full_name": "Omar", "phone": "+" + PHONE})
    assert t["current_step"]["type"] == "review"
    client.put(f"{base}/money", headers=admin, json={"total_price": "40"})
    t = client.post(f"{base}/workflow/done", headers=admin, json={"key": "review"}).json()
    assert t["current_step"]["type"] == "documents" and "Passport copy" in fake.sent[-1][2]
    t = client.post(f"{base}/workflow/done", headers=admin, json={"key": "documents"}).json()
    assert t["status"] == "working" and t["current_step"]["type"] == "schedule"
    assert "times are not possible" in fake.sent[-1][2]
    # The client can't confirm before a time is booked; the team books it and the client is asked to confirm.
    assert client.post(f"{base}/workflow/schedule/confirm", headers=admin).status_code == 409
    client.put(f"{base}/workflow/schedule/appointment", headers=admin, json={"client_times": "Sunday morning, not Thursday"})
    at = (date.today() + timedelta(days=5)).isoformat() + "T05:30:00Z"
    t = client.put(f"{base}/workflow/schedule/appointment", headers=admin, json={"starts_at": at, "location": "German Embassy, Muscat"}).json()
    step = next(s for s in t["process"]["steps"] if s["key"] == "schedule")
    assert step["client_times"] == "Sunday morning, not Thursday" and step["appointment"]["location"] == "German Embassy, Muscat"
    assert "reply *confirm*" in fake.sent[-1][2] and "German Embassy" in fake.sent[-1][2]
    day = date.today() + timedelta(days=5)
    cal = client.get(f"/api/calendar?start={day.isoformat()}&end={day.isoformat()}", headers=admin).json()
    assert any(a["ticket_id"] == t["id"] and a["location"] == "German Embassy, Muscat" for a in cal["appointments"])
    t = client.post(f"{base}/workflow/schedule/confirm", headers=admin).json()
    assert t["status"] == "pending_payment" and t["process"]["due_now"] == 40
    assert any("confirmed ✅" in m[2] for m in fake.sent[-3:]) and "40.000 OMR" in fake.sent[-1][2]


def test_closing_keeps_who_why_and_the_step(client, wa):
    _, admin, _ = wa
    t, base = new_request(client, admin, "hotel", {**TRIP, "rooms": "1"})
    assert client.post(f"{base}/close", headers=admin, json={"by": "client", "reason": "x"}).status_code == 422
    t = client.post(f"{base}/close", headers=admin, json={"by": "client", "reason": "Changed travel dates"}).json()
    info = t["process"]["cancel"]
    assert t["status"] == "cancelled" and info["by"] == "client" and info["reason"] == "Changed travel dates"
    assert info["step"] == "review" and info["step_ar"] == "مراجعة الفريق" and "(for the client)" in info["name"]
    assert client.post(f"{base}/close", headers=admin, json={"reason": "Again"}).status_code == 409
    assert client.put(f"{base}/workflow", headers=admin, json={"steps": t["process"]["steps"]}).status_code == 409
    # Reopened by an admin: the reason is cleared and the request starts again.
    t = client.patch(base, headers=admin, json={"status": "new"}).json()
    assert t["status"] == "new" and t["process"]["cancel"] is None and t["current_step"]["type"] == "quote"
    # A cancellation from the status menu keeps its reason too.
    t = client.patch(base, headers=admin, json={"status": "cancelled", "cancel_reason": "No answer for two weeks"}).json()
    assert t["process"]["cancel"]["by"] == "team" and t["process"]["cancel"]["reason"] == "No answer for two weeks"


def test_requests_made_before_workflows_get_one_from_their_status(client, wa):
    _, admin, _ = wa
    t, base = new_request(client, admin, "hotel", {**TRIP, "rooms": "1"})
    t = quote_and_approve(client, admin, base, "hotel", "500")
    with SessionLocal() as db:
        ticket = db.get(Ticket, t["id"])
        ticket.workflow = None  # as stored before workflows existed
        ticket.status = "paid"
        db.commit()
    t = client.get(base, headers=admin).json()
    states = dict(steps_of(t))
    assert states["payment"] == "done" and states["booking"] == "active" and states["trip"] == "pending"
