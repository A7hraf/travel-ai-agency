"""Employees finishing bookings: assignment, statuses, seats, dashboard, packages."""

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import TravelPackage
from tests.conftest import future, login, make_package


def create_ticket(client, company, admin, scripted, pkg, adults=2):
    scripted([
        LLMResponse(None, [ToolCall("b", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": adults,
            "lead_traveler_name": "Ali", "contact_phone": "+1"})]),
        LLMResponse("Booked."),
    ])
    slug = company["slug"]
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "book"})
    return client.get("/api/tickets", headers=admin).json()[0]


def add_user(client, admin, email, role):
    client.post("/api/users", headers=admin, json={
        "email": email, "full_name": email.split("@")[0], "password": "Password123", "role": role})
    return login(client, email, "Password123")


def test_ticket_workflow_and_seats(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=5)
    ticket = create_ticket(client, company, admin, scripted, pkg, adults=2)
    agent = add_user(client, admin, "agent@bluesky.com", "ticket_agent")

    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={"status": "in_progress"})
    assert r.json()["status"] == "in_progress"
    assert r.json()["assigned_to"]["full_name"] == "agent"  # picked up by whoever starts it

    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={
        "status": "paid", "payment_reference": "BANK-123", "internal_notes": "Paid by transfer"})
    assert r.json()["payment_reference"] == "BANK-123"

    client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={"status": "confirmed"})
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["seats_available"] == 3

    client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={"status": "cancelled"})
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["seats_available"] == 5

    # Status changes are visible in the conversation history for the team.
    conv = client.get(f"/api/conversations/{ticket['conversation_id']}", headers=admin).json()
    assert any("confirmed" in m["content"] for m in conv["messages"] if m["sender"] == "system")


def test_assigning_to_others_needs_permission(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    ticket = create_ticket(client, company, admin, scripted, pkg)
    agent = add_user(client, admin, "agent@bluesky.com", "ticket_agent")
    support = add_user(client, admin, "support@bluesky.com", "support")
    team = {u["email"]: u["id"] for u in client.get("/api/team", headers=admin).json()}

    # support can see tickets but not change them
    assert client.get("/api/tickets", headers=support).status_code == 200
    assert client.patch(f"/api/tickets/{ticket['id']}", headers=support, json={"status": "paid"}).status_code == 403

    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agent,
                     json={"assigned_to_id": team["support@bluesky.com"]})
    assert r.status_code == 403
    r = client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={"assigned_to_id": team["agent@bluesky.com"]})
    assert r.status_code == 200
    r = client.patch(f"/api/tickets/{ticket['id']}", headers=admin,
                     json={"assigned_to_id": team["support@bluesky.com"]})
    assert r.json()["assigned_to"]["id"] == team["support@bluesky.com"]

    mine = client.get("/api/tickets", headers=agent, params={"mine": True}).json()
    assert mine == []


def test_dashboard_numbers(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    create_ticket(client, company, admin, scripted, pkg, adults=2)
    d = client.get("/api/dashboard", headers=admin).json()
    assert d["tickets_by_status"] == {"pending_payment": 1}
    assert d["pipeline_value"] == 4000
    assert d["conversations_by_status"] == {"human": 1}
    assert d["conversations_waiting"] == 1
    assert d["packages_active"] == 1


def test_public_storefront_hides_unavailable_packages(client, company_a):
    company, admin = company_a
    make_package(client, admin, title="Open Trip")
    make_package(client, admin, title="Hidden Trip", is_active=False)
    make_package(client, admin, title="Sold Out", seats_available=0)
    past = make_package(client, admin, title="Past Trip", departure_dates=[future(3)])
    with SessionLocal() as db:  # its dates passed since it was created
        db.get(TravelPackage, past["id"]).departure_dates = ["2020-01-01"]
        db.commit()
    make_package(client, admin, title="Flexible Trip", departure_dates=[])
    titles = [p["title"] for p in client.get(f"/api/public/companies/{company['slug']}/packages").json()]
    assert sorted(titles) == ["Flexible Trip", "Open Trip"]


def test_deleting_a_booked_package_archives_it(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    create_ticket(client, company, admin, scripted, pkg)
    assert client.delete(f"/api/packages/{pkg['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["is_active"] is False

    unused = make_package(client, admin, title="Unused")
    client.delete(f"/api/packages/{unused['id']}", headers=admin)
    assert client.get(f"/api/packages/{unused['id']}", headers=admin).status_code == 404


def test_deleting_employee_and_company_with_history(client, owner, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    ticket = create_ticket(client, company, admin, scripted, pkg)
    agent = add_user(client, admin, "agent@bluesky.com", "ticket_agent")
    client.patch(f"/api/tickets/{ticket['id']}", headers=agent, json={"status": "in_progress"})
    client.post(f"/api/conversations/{ticket['conversation_id']}/messages", headers=agent, json={"content": "Hi"})

    agent_id = next(u["id"] for u in client.get("/api/users", headers=admin).json()["users"]
                    if u["email"] == "agent@bluesky.com")
    assert client.delete(f"/api/users/{agent_id}", headers=admin).status_code == 204
    t = client.get(f"/api/tickets/{ticket['id']}", headers=admin).json()
    assert t["assigned_to"] is None
    conv = client.get(f"/api/conversations/{ticket['conversation_id']}", headers=admin).json()
    assert conv["messages"][-1]["content"] == "Hi" and conv["messages"][-1]["author_name"] is None

    assert client.delete(f"/api/system/companies/{company['id']}", headers=owner).status_code == 204
    assert client.get("/api/system/stats", headers=owner).json()["tickets"] == 0
