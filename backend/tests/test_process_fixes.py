"""Business-process fixes: seats per departure date, seat holds that expire, bookings at the quoted total,
ticket status rules and package prices."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal, engine
from app.migrations import BACKFILL
from app.models import Ticket, TravelPackage
from app.services import seats
from tests.conftest import future, login, make_package


def quote(pkg, adults=2, date=None, children=0):
    return ToolCall("q", "quote_booking", {"package_id": pkg["id"], "departure_date": date or future(30),
                                           "adults": adults, "children": children})


def book(pkg, adults=2, date=None, children=0):
    return ToolCall("b", "create_booking_ticket", {
        "package_id": pkg["id"], "departure_date": date or future(30), "adults": adults, "children": children,
        "lead_traveler_name": "Ali", "contact_phone": "+968"})


def chat(client, company, scripted, steps, token=None, text_="book"):
    llm = scripted(steps)
    slug = company["slug"]
    token = token or client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": text_})
    return token, llm


def results(llm) -> list[dict]:
    messages = llm.calls[-1]
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    return [json.loads(m["content"]) for m in messages[last_user:] if m["role"] == "tool"]


def quote_and_book(client, company, scripted, pkg, adults=2, date=None):
    chat(client, company, scripted, [LLMResponse(None, [quote(pkg, adults, date), book(pkg, adults, date)]),
                                     LLMResponse("Booked")])


def add_user(client, admin, email, permissions, role="support"):
    r = client.post("/api/users", headers=admin, json={
        "email": email, "full_name": email.split("@")[0], "password": "Password123", "role": role,
        "permissions": permissions})
    assert r.status_code == 201, r.text
    return login(client, email, "Password123")


def age_ticket(ticket_id, hours):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        t.created_at = t.seats_held_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        db.commit()


# --- 1. Seats per departure date ----------------------------------------------------------------


def test_seats_are_counted_per_departure_date(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=10)
    quote_and_book(client, company, scripted, pkg, adults=9)
    # The booked date has 1 seat left; the other date still has all 10.
    _, llm = chat(client, company, scripted, [LLMResponse(None, [quote(pkg, 2), quote(pkg, 2, future(60))]),
                                              LLMResponse("ok")])
    on_booked, on_other = results(llm)
    assert on_booked["error"] == f"Only 1 seats are left on {future(30)}." and on_booked["dates_with_seats"]
    assert on_other["total_price"] == 4000 and on_other["seats_left_on_date"] == 10
    quote_and_book(client, company, scripted, pkg, adults=9, date=future(60))
    assert len(client.get("/api/tickets", headers=admin).json()) == 2

    staff = client.get(f"/api/packages/{pkg['id']}", headers=admin).json()
    assert staff["seats_available"] == 10
    assert staff["seats_left_by_date"] == {future(30): 1, future(60): 1}
    public = client.get(f"/api/public/companies/{company['slug']}/packages").json()[0]
    assert public["seats_left_by_date"] == {future(30): 1, future(60): 1} and public["seats_available"] == 1

    # The AI sees the seats left on each date.
    _, llm = chat(client, company, scripted, [LLMResponse(None, [ToolCall("s", "search_packages", {})]),
                                              LLMResponse("ok")])
    assert results(llm)[0]["results"][0]["seats_left"] == {future(30): 1, future(60): 1}


def test_sold_out_date_is_hidden_and_package_disappears_when_every_date_is_full(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=2)
    quote_and_book(client, company, scripted, pkg, adults=2)
    _, llm = chat(client, company, scripted, [LLMResponse(None, [ToolCall("d", "get_package_details",
                                                                          {"package_id": pkg["id"]})]),
                                              LLMResponse("ok")])
    details = results(llm)[0]
    assert details["next_departures"] == [future(60)] and details["all_upcoming_departures"] == [future(60)]
    quote_and_book(client, company, scripted, pkg, adults=2, date=future(60))
    assert client.get(f"/api/public/companies/{company['slug']}/packages").json() == []


def test_two_bookings_at_the_same_moment_cannot_take_the_same_last_seats(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=3)
    quote_and_book(client, company, scripted, pkg, adults=1)  # a customer to attach the bookings to
    customer_id = client.get("/api/tickets", headers=admin).json()[0]["customer"]["id"]

    def new_ticket(db, name):
        t = Ticket(company_id=company["id"], reference=f"TRV-{name}", customer_id=customer_id, package_id=pkg["id"],
                   package_title="x", departure_date=future(30), adults=2, lead_traveler_name="X", total_price=1,
                   currency="OMR")
        db.add(t)
        db.flush()
        return t

    with SessionLocal() as db:  # B: an existing booking without seats (e.g. released), paid by an employee
        b_id = new_ticket(db, "B").id
        db.commit()
    outcome: dict[str, str] = {}
    a_holds = threading.Event()

    def take(name):
        with SessionLocal() as db:
            try:
                if name == "A":
                    t = new_ticket(db, "A")
                    seats.hold(db, t)
                    a_holds.set()
                    time.sleep(0.5)  # B counts the seats meanwhile
                else:
                    seats.hold(db, db.get(Ticket, b_id))
                db.commit()
                outcome[name] = "held"
            except seats.NotEnoughSeats:
                db.rollback()
                outcome[name] = "refused"

    a = threading.Thread(target=take, args=("A",))
    a.start()
    assert a_holds.wait(5)
    b = threading.Thread(target=take, args=("B",))
    b.start()
    a.join()
    b.join()
    assert outcome == {"A": "held", "B": "refused"}


def test_upgrade_adds_back_the_seats_of_existing_bookings(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=10)
    quote_and_book(client, company, scripted, pkg, adults=3)
    with SessionLocal() as db:  # an old database: the booked seats were taken off the one pool
        db.get(TravelPackage, pkg["id"]).seats_available = 7
        db.commit()
    with engine.begin() as conn:
        conn.execute(text(BACKFILL[("tickets", "seats_held_at")]))
    staff = client.get(f"/api/packages/{pkg['id']}", headers=admin).json()
    assert staff["seats_available"] == 10 and staff["seats_left_by_date"][future(30)] == 7


# --- 2. Seat holds expire; group size ---------------------------------------------------------------


def test_unpaid_hold_expires_and_staff_re_hold_on_payment(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=4)
    quote_and_book(client, company, scripted, pkg, adults=4)
    first = client.get("/api/tickets", headers=admin).json()[0]
    assert first["seats_held"] == 4 and first["seats_released"] is False
    age_ticket(first["id"], 49)

    # The expired hold no longer blocks the date, even before anyone lists the tickets.
    _, llm = chat(client, company, scripted, [LLMResponse(None, [quote(pkg, 4)]), LLMResponse("ok")])
    assert results(llm)[0]["seats_left_on_date"] == 4

    listed = {t["id"]: t for t in client.get("/api/tickets", headers=admin).json()}[first["id"]]
    assert listed["seats_held"] == 0 and listed["seats_released"] is True
    events = client.get(f"/api/tickets/{first['id']}/events", headers=admin).json()
    assert events[-1]["action"] == "seats_released"
    assert events[-1]["new_value"] == "Seats released: not paid within 48 hours"

    # Paying later takes the seats again.
    r = client.patch(f"/api/tickets/{first['id']}", headers=admin, json={"status": "paid", "payment_reference": "R1"})
    assert r.status_code == 200 and r.json()["seats_held"] == 4 and r.json()["seats_released"] is False


def test_paying_a_released_booking_fails_clearly_when_the_seats_were_sold(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=4)
    quote_and_book(client, company, scripted, pkg, adults=3)
    first = client.get("/api/tickets", headers=admin).json()[0]
    age_ticket(first["id"], 49)
    quote_and_book(client, company, scripted, pkg, adults=3)  # another customer takes the seats
    assert len(client.get("/api/tickets", headers=admin).json()) == 2
    r = client.patch(f"/api/tickets/{first['id']}", headers=admin, json={"status": "paid", "payment_reference": "R1"})
    assert r.status_code == 409
    assert "released" in r.json()["detail"] and f"only 1 seats are left on {future(30)}" in r.json()["detail"]


def test_holds_of_paid_or_handled_bookings_never_expire(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=4)
    quote_and_book(client, company, scripted, pkg, adults=2)
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    client.patch(f"/api/tickets/{ticket['id']}", headers=admin, json={"status": "in_progress"})
    age_ticket(ticket["id"], 100)
    assert client.get(f"/api/tickets/{ticket['id']}", headers=admin).json()["seats_held"] == 2


def test_big_groups_go_to_a_consultant(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=50)
    _, llm = chat(client, company, scripted, [LLMResponse(None, [quote(pkg, 8, children=2)]), LLMResponse("ok")])
    assert "up to 9 travelers" in results(llm)[0]["error"] and "request_human_agent" in results(llm)[0]["error"]


# --- 3. The booking total is the quoted total ---------------------------------------------------------


def test_booking_needs_a_quote_for_the_same_details(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    _, llm = chat(client, company, scripted, [LLMResponse(None, [book(pkg)]), LLMResponse("ok")])
    assert "quote_booking" in results(llm)[0]["error"]
    _, llm = chat(client, company, scripted, [LLMResponse(None, [quote(pkg, 2), book(pkg, 3)]), LLMResponse("ok")])
    assert "No quote for these booking details" in results(llm)[1]["error"]
    assert client.get("/api/tickets", headers=admin).json() == []


def test_price_change_after_the_quote_needs_a_new_confirmation(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    token, _ = chat(client, company, scripted, [LLMResponse(None, [quote(pkg)]), LLMResponse("4000, confirm?")])
    body = {k: pkg[k] for k in ("title", "destination", "country", "description", "duration_days",
                                "child_price", "departure_dates", "tags", "seats_available")}
    body["price_per_person"] = 3000
    assert client.put(f"/api/packages/{pkg['id']}", headers=admin, json=body).status_code == 200

    _, llm = chat(client, company, scripted, [LLMResponse(None, [book(pkg)]), LLMResponse("Price changed")],
                  token=token, text_="yes")
    refused = results(llm)[0]
    assert "price changed" in refused["error"] and refused["new_total"] == 6000
    assert client.get("/api/tickets", headers=admin).json() == []

    chat(client, company, scripted, [LLMResponse(None, [quote(pkg)]), LLMResponse("Now 6000, confirm?")],
         token=token, text_="ok?")
    chat(client, company, scripted, [LLMResponse(None, [book(pkg)]), LLMResponse("Booked")], token=token, text_="yes")
    assert client.get("/api/tickets", headers=admin).json()[0]["total_price"] == 6000


# --- 4. Ticket status rules ----------------------------------------------------------------------------


def test_cancel_and_reopen_clear_the_payment_reference(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    quote_and_book(client, company, scripted, pkg)
    url = f"/api/tickets/{client.get('/api/tickets', headers=admin).json()[0]['id']}"
    assert client.patch(url, headers=admin, json={"status": "paid", "payment_reference": "RCPT-1"}).status_code == 200
    r = client.patch(url, headers=admin, json={"status": "cancelled"})
    assert r.json()["payment_reference"] is None
    assert client.patch(url, headers=admin, json={"status": "pending_payment"}).status_code == 200
    assert client.patch(url, headers=admin, json={"status": "paid"}).status_code == 400  # needs a new receipt
    events = [(e["action"], e["old_value"], e["new_value"]) for e in client.get(f"{url}/events", headers=admin).json()]
    assert ("payment_reference", "RCPT-1", None) in events


def test_departed_bookings_can_only_be_cancelled(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    quote_and_book(client, company, scripted, pkg)
    tid = client.get("/api/tickets", headers=admin).json()[0]["id"]
    with SessionLocal() as db:
        db.get(Ticket, tid).departure_date = "2020-01-01"
        db.commit()
    r = client.patch(f"/api/tickets/{tid}", headers=admin, json={"payment_reference": "R", "status": "paid"})
    assert r.status_code == 400 and "has passed" in r.json()["detail"]
    assert client.patch(f"/api/tickets/{tid}", headers=admin, json={"status": "cancelled"}).status_code == 200


def test_ticket_changes_need_view_and_assignees_must_see_tickets(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    quote_and_book(client, company, scripted, pkg)
    tid = client.get("/api/tickets", headers=admin).json()[0]["id"]
    blind = add_user(client, admin, "m@bluesky.com", ["tickets.manage"])
    assert client.patch(f"/api/tickets/{tid}", headers=blind, json={}).status_code == 403
    add_user(client, admin, "cs@bluesky.com", ["conversations.view"])
    cs_id = next(u["id"] for u in client.get("/api/team", headers=admin).json() if u["email"] == "cs@bluesky.com")
    r = client.patch(f"/api/tickets/{tid}", headers=admin, json={"assigned_to_id": cs_id})
    assert r.status_code == 400 and "tickets.view" in r.json()["detail"]


def test_ticket_search_treats_wildcards_as_text(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    quote_and_book(client, company, scripted, pkg)
    assert client.get("/api/tickets", headers=admin, params={"q": "_"}).json() == []
    assert client.get("/api/tickets", headers=admin, params={"q": "%"}).json() == []
    assert len(client.get("/api/tickets", headers=admin, params={"q": "Ali"}).json()) == 1


# --- 5. Package prices -----------------------------------------------------------------------------------


def test_prices_that_round_to_zero_are_refused(client, company_a):
    _, admin = company_a
    base = {"title": "Trip", "destination": "Male", "country": "Maldives", "duration_days": 3}
    for bad in ({"price_per_person": 0.0004}, {"price_per_person": 10, "child_price": 0.0004}):
        assert client.post("/api/packages", headers=admin, json={**base, **bad}).status_code == 422, bad
    ok = client.post("/api/packages", headers=admin, json={**base, "price_per_person": 0.0005, "child_price": 0})
    assert ok.status_code == 201 and ok.json()["price_per_person"] == 0.001 and ok.json()["child_price"] == 0

