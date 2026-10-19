"""Regression tests for the process, data and security audit."""

from datetime import timedelta

from fastapi import HTTPException

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import Conversation, Customer, MediaFile, Ticket, utcnow
from app.timeutil import local_today, start_of_local_day
from tests.conftest import future, login, make_company, make_package
from tests.test_branding import upload


def add_user(client, headers, email, role="support", permissions=None, path="/api/users"):
    body = {"email": email, "full_name": email.split("@")[0], "password": "Password123", "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post(path, headers=headers, json=body)
    return r


def booked_ticket(client, company, admin, scripted, pkg, adults=2):
    scripted([LLMResponse(None, [ToolCall("q", "quote_booking", {
        "package_id": pkg["id"], "departure_date": future(30), "adults": adults}),
        ToolCall("b", "create_booking_ticket", {
        "package_id": pkg["id"], "departure_date": future(30), "adults": adults,
        "lead_traveler_name": "Ali", "contact_phone": "+968"})]), LLMResponse("Booked")])
    slug = company["slug"]
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "book"})
    return client.get("/api/tickets", headers=admin).json()[0]


# --- Accounts ---------------------------------------------------------------------------------


def test_users_manage_is_not_full_admin(client, company_a):
    company, admin = company_a
    assert add_user(client, admin, "hr@bluesky.com", permissions=["users.manage", "conversations.view"]).status_code == 201
    hr = login(client, "hr@bluesky.com", "Password123")
    me = client.get("/api/auth/me", headers=hr).json()
    # can't raise its own permissions
    r = client.patch(f"/api/users/{me['id']}", headers=hr, json={"permissions": ["users.manage", "settings.manage"]})
    assert r.status_code == 400
    # can't create admins or give permissions it doesn't have
    assert add_user(client, hr, "boss@bluesky.com", role="company_admin").status_code == 403
    assert add_user(client, hr, "x@bluesky.com", permissions=["settings.manage"]).status_code == 403
    assert add_user(client, hr, "ok@bluesky.com", permissions=["conversations.view"]).status_code == 201
    # can't touch the real admin
    admin_id = client.get("/api/auth/me", headers=admin).json()["id"]
    assert client.patch(f"/api/users/{admin_id}", headers=hr, json={"password": "Hijacked123"}).status_code == 403
    assert client.delete(f"/api/users/{admin_id}", headers=hr).status_code == 403
    assert client.get("/api/auth/me", headers=admin).status_code == 200


def test_disabled_accounts_lose_old_logins_and_free_a_seat(client, owner):
    company, admin = make_company(client, owner, max_users=2)
    assert add_user(client, admin, "s1@bluesky.com").status_code == 201
    s1 = login(client, "s1@bluesky.com", "Password123")
    assert add_user(client, admin, "s2@bluesky.com").status_code == 409  # 2/2 used
    user_id = client.get("/api/auth/me", headers=s1).json()["id"]
    client.patch(f"/api/users/{user_id}", headers=admin, json={"is_active": False})
    assert add_user(client, admin, "s2@bluesky.com").status_code == 201  # the disabled account frees its seat
    # re-enabling needs a free seat, and the old login never works again
    assert client.patch(f"/api/users/{user_id}", headers=admin, json={"is_active": True}).status_code == 409
    owner_r = client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_users": 3})
    assert owner_r.status_code == 200
    assert client.patch(f"/api/users/{user_id}", headers=admin, json={"is_active": True}).status_code == 200
    assert client.get("/api/auth/me", headers=s1).status_code == 401
    # the limit can't go below the accounts in use
    r = client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_users": 1})
    assert r.status_code == 400


def test_company_is_created_with_its_admin_or_not_at_all(client, owner, monkeypatch):
    from app.routers import system_admin

    make_company(client, owner, name="Alpha", admin_email="a@alpha.com")

    def broken(*args, **kwargs):
        raise HTTPException(400, "admin could not be created")
    monkeypatch.setattr(system_admin, "create_company_user", broken)
    r = client.post("/api/system/companies", headers=owner, json={
        "name": "Beta", "admin_email": "b@beta.com", "admin_full_name": "Beta Admin", "admin_password": "Password123"})
    assert r.status_code == 400
    names = [c["name"] for c in client.get("/api/system/companies", headers=owner).json()]
    assert names == ["Alpha"]


def _company(client, owner, name, email, password):
    r = client.post("/api/system/companies", headers=owner, json={
        "name": name, "admin_email": email, "admin_full_name": f"{name} Admin", "admin_password": password})
    assert r.status_code == 201, r.text
    return r.json(), None


def test_one_email_can_run_several_companies(client, owner):
    """The platform owner can create any number of companies with the same admin email (their own,
    while testing), and the login asks which company to open."""
    a, _ = _company(client, owner, "Alpha", "me@owner.com", "AdminPass123!")
    b, _ = _company(client, owner, "Beta", "me@owner.com", "AdminPass123!")
    _company(client, owner, "Gamma", "owner@example.com", "OwnerPass123!")
    names = [c["name"] for c in client.get("/api/system/companies", headers=owner).json()]
    assert names == ["Alpha", "Beta", "Gamma"]

    r = client.post("/api/auth/login", json={"email": "me@owner.com", "password": "AdminPass123!"})
    assert r.status_code == 200 and "access_token" not in r.json()
    assert {c["account"] for c in r.json()["choose"]} == {a["slug"], b["slug"]}
    r = client.post("/api/auth/login", json={"email": "me@owner.com", "password": "AdminPass123!", "account": b["slug"]})
    assert r.json()["user"]["company"]["name"] == "Beta"
    # The owner's own email and password: the platform console or the test company.
    r = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "OwnerPass123!"})
    assert {c["account"] for c in r.json()["choose"]} == {"platform", "gamma"}
    r = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "OwnerPass123!",
                                             "account": "platform"})
    assert r.json()["user"]["role"] == "system_admin"
    # A wrong password reveals nothing about where the email has accounts.
    r = client.post("/api/auth/login", json={"email": "me@owner.com", "password": "Wrong-pass1"})
    assert r.status_code == 401 and "choose" not in r.text
    # Inside one company the email is still unique.
    admin_b = {"Authorization": "Bearer " + client.post("/api/auth/login", json={
        "email": "me@owner.com", "password": "AdminPass123!", "account": b["slug"]}).json()["access_token"]}
    r = client.post("/api/users", headers=admin_b, json={
        "email": "me@owner.com", "full_name": "Twin", "password": "Password123", "role": "support"})
    assert r.status_code == 409
    # ...and another company's staff list stays invisible: the same email is accepted in Beta.
    r = client.post("/api/users", headers=admin_b, json={
        "email": "admin@alpha-only.com", "full_name": "Sam", "password": "Password123", "role": "support"})
    assert r.status_code == 201


def test_company_names_and_web_addresses(client, owner):
    base = {"admin_full_name": "Admin", "admin_password": "Password123"}
    r = client.post("/api/system/companies", headers=owner, json={"name": "رحلات الخليج", "admin_email": "a@g.com",
                                                                  **base})
    assert r.status_code == 422 and "English" in r.text
    r = client.post("/api/system/companies", headers=owner, json={"name": "رحلات الخليج", "slug": "gulf-trips",
                                                                  "admin_email": "a@g.com", **base})
    assert r.status_code == 201 and r.json()["slug"] == "gulf-trips"
    for bad in ({"name": "   "}, {"name": "Ok Name", "slug": "api"}, {"name": "Ok Name", "currency": "1$x"}):
        body = {"admin_email": "z@z.com", **base, **bad}
        assert client.post("/api/system/companies", headers=owner, json=body).status_code == 422, bad


# --- Tickets ----------------------------------------------------------------------------------


def test_ticket_status_rules_and_history(client, company_a, scripted):
    company, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "t@bluesky.com", "full_name": "Tariq", "password": "Password123", "role": "ticket_agent"})
    agent = login(client, "t@bluesky.com", "Password123")
    pkg = make_package(client, admin, seats_available=8)
    ticket = booked_ticket(client, company, admin, scripted, pkg)
    url = f"/api/tickets/{ticket['id']}"

    assert client.patch(url, headers=agent, json={"status": "confirmed"}).status_code == 400  # must be paid first
    assert client.patch(url, headers=agent, json={"status": "paid"}).status_code == 400  # needs a payment reference
    assert client.patch(url, headers=agent, json={"status": "paid", "payment_reference": "BANK-1"}).status_code == 200
    assert client.patch(url, headers=agent, json={"status": "pending_payment"}).status_code == 400
    assert client.patch(url, headers=agent, json={"total_price": 0.001}).status_code == 403  # admins only
    assert client.patch(url, headers=agent, json={"status": "confirmed"}).status_code == 200
    assert client.patch(url, headers=agent, json={"status": "cancelled"}).status_code == 200
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["seats_left_by_date"][future(30)] == 8
    assert client.patch(url, headers=agent, json={"status": "pending_payment"}).status_code == 403  # admin reopens
    assert client.patch(url, headers=admin, json={"status": "pending_payment"}).status_code == 200
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["seats_left_by_date"][future(30)] == 6
    assert client.patch(url, headers=admin, json={"total_price": 3500}).status_code == 200

    events = client.get(f"{url}/events", headers=admin).json()
    actions = [(e["action"], e["old_value"], e["new_value"]) for e in events]
    assert ("payment_reference", None, "BANK-1") in actions
    assert ("status", "paid", "confirmed") in actions and ("price", "4000.000", "3500.000") in actions
    assert {e["actor"] for e in events} >= {"AI", "Tariq"}


def test_only_unassigned_tickets_can_be_taken_without_assign_permission(client, company_a, scripted):
    company, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "t@bluesky.com", "full_name": "Tariq", "password": "Password123", "role": "ticket_agent"})
    agent = login(client, "t@bluesky.com", "Password123")
    agent_id = client.get("/api/auth/me", headers=agent).json()["id"]
    admin_id = client.get("/api/auth/me", headers=admin).json()["id"]
    ticket = booked_ticket(client, company, admin, scripted, make_package(client, admin))
    url = f"/api/tickets/{ticket['id']}"
    client.patch(url, headers=admin, json={"assigned_to_id": admin_id})
    assert client.patch(url, headers=agent, json={"assigned_to_id": agent_id}).status_code == 403


def test_package_edit_keeps_seats_taken_meanwhile(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=4)
    loaded = client.get(f"/api/packages/{pkg['id']}", headers=admin).json()
    booked_ticket(client, company, admin, scripted, pkg, adults=2)  # while the form is open
    body = {k: loaded[k] for k in ("title", "destination", "country", "duration_days", "price_per_person",
                                   "departure_dates", "seats_available")}
    body.update(description="New text", seats_loaded=loaded["seats_available"])
    # Bookings no longer change the seats per departure date, only the seats left on the booked date.
    saved = client.put(f"/api/packages/{pkg['id']}", headers=admin, json=body).json()
    assert saved["seats_available"] == 4 and saved["seats_left_by_date"][future(30)] == 2
    body.update(seats_available=10)  # the employee really changed it
    assert client.put(f"/api/packages/{pkg['id']}", headers=admin, json=body).json()["seats_available"] == 10


def test_package_values_are_checked(client, company_a):
    _, admin = company_a
    base = {"title": "Trip", "destination": "x", "country": "x", "duration_days": 3, "price_per_person": 100}
    for bad in ({"price_per_person": 0}, {"price_per_person": 1e12}, {"currency": "1$x"},
                {"image_url": "http://plain.example/a.jpg"}):
        assert client.post("/api/packages", headers=admin, json={**base, **bad}).status_code == 422, bad
    assert client.post("/api/packages", headers=admin, json={**base, "departure_dates": ["2020-01-01"]}).status_code == 400
    r = client.post("/api/packages", headers=admin, json={**base, "departure_dates": ["2020-01-01", future(9)]})
    assert r.json()["departure_dates"] == [future(9)]


# --- Dashboard ----------------------------------------------------------------------------------


def test_dashboard_days_follow_oman_time_and_currencies_are_not_mixed(client, company_a, scripted):
    company, admin = company_a
    just_after_midnight = start_of_local_day(local_today()) + timedelta(minutes=30)  # 20:30 UTC the day before
    with SessionLocal() as db:
        customer = Customer(company_id=company["id"])
        db.add(customer)
        db.flush()
        db.add(Conversation(company_id=company["id"], customer_id=customer.id, channel="web",
                            created_at=just_after_midnight))
        db.commit()
    omr = make_package(client, admin, title="OMR trip", price_per_person=100)
    usd = make_package(client, admin, title="USD trip", price_per_person=100, currency="USD")
    booked_ticket(client, company, admin, scripted, omr, adults=1)
    scripted([LLMResponse(None, [ToolCall("q", "quote_booking", {
        "package_id": usd["id"], "departure_date": future(30), "adults": 1}),
        ToolCall("b", "create_booking_ticket", {
        "package_id": usd["id"], "departure_date": future(30), "adults": 1,
        "lead_traveler_name": "Sam", "contact_phone": "+1"})]), LLMResponse("Booked")])
    slug = company["slug"]
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "book"})

    a = client.get("/api/dashboard/analytics", headers=admin, params={"days": 7}).json()
    assert a["daily"][-1]["date"] == local_today().isoformat()
    assert a["daily"][-1]["web"] == 3  # the 00:30 Oman chat counts today
    assert a["booked_value"] == 100 and sum(d["booked_value"] for d in a["daily"]) == 100
    d = client.get("/api/dashboard", headers=admin).json()
    assert d["pipeline_value"] == 100 and d["other_currencies"] == {"USD": 100}


def test_handled_by_ai_counts_chats_the_team_touched(client, company_a, scripted):
    company, admin = company_a
    scripted([LLMResponse("Hello")])
    slug = company["slug"]
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "hi"})
    conv_id = client.get("/api/conversations", headers=admin).json()[0]["id"]
    client.post(f"/api/conversations/{conv_id}/takeover", headers=admin)
    client.post(f"/api/conversations/{conv_id}/release", headers=admin)
    a = client.get("/api/dashboard/analytics", headers=admin).json()
    assert a["handled_by_ai"] == 0 and a["handed_to_team"] == 1


# --- Conversations ------------------------------------------------------------------------------


def test_take_over_from_a_colleague_needs_force(client, company_a, scripted):
    company, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "Sami", "password": "Password123", "role": "support"})
    support = login(client, "s@bluesky.com", "Password123")
    scripted([LLMResponse("Hello")])
    slug = company["slug"]
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "hi"})
    conv_id = client.get("/api/conversations", headers=admin).json()[0]["id"]
    taken = client.post(f"/api/conversations/{conv_id}/takeover", headers=support)
    assert taken.status_code == 200 and taken.json()["assigned_to"]["full_name"] == "Sami"
    r = client.post(f"/api/conversations/{conv_id}/takeover", headers=admin)
    assert r.status_code == 409 and "Sami" in r.json()["detail"]
    assert client.post(f"/api/conversations/{conv_id}/takeover?force=true", headers=admin).status_code == 200
    closed = client.post(f"/api/conversations/{conv_id}/close", headers=admin).json()
    assert closed["assigned_to"] is None


def test_whatsapp_reply_after_24_hours_is_refused(client, company_a):
    company, admin = company_a
    with SessionLocal() as db:
        customer = Customer(company_id=company["id"], whatsapp_id="96891234567")
        db.add(customer)
        db.flush()
        conv = Conversation(company_id=company["id"], customer_id=customer.id, channel="whatsapp",
                            status="human", last_customer_message_at=utcnow() - timedelta(days=3))
        db.add(conv)
        db.commit()
        conv_id = conv.id
    r = client.post(f"/api/conversations/{conv_id}/messages", headers=admin, json={"content": "Hello?"})
    assert r.status_code == 409 and "24 hours" in r.json()["detail"]


# --- Uploads and limits -------------------------------------------------------------------------


def test_unused_photos_are_cleaned_when_storage_is_full(client, company_a, monkeypatch):
    from app.routers import media

    company, admin = company_a
    monkeypatch.setattr(media, "MAX_FILES_PER_COMPANY", 2)
    used = upload(client, admin).json()["url"]
    make_package(client, admin, image_url=used)
    upload(client, admin)
    with SessionLocal() as db:  # make both uploads old enough to be cleaned
        for m in db.query(MediaFile).all():
            m.created_at = utcnow() - timedelta(days=1)
        db.commit()
    assert upload(client, admin).status_code == 201  # the unused one was removed
    with SessionLocal() as db:
        keys = {m.key for m in db.query(MediaFile).all()}
    assert used.removeprefix("/api/media/") in keys and len(keys) == 2


def test_chat_start_is_limited_per_company(client, company_a, monkeypatch):
    company, _ = company_a
    slug = company["slug"]
    codes = []
    for i in range(65):
        r = client.post(f"/api/public/companies/{slug}/chats", json={},
                        headers={"X-Forwarded-For": f"10.0.{i}.1"})
        codes.append(r.status_code)
    assert 429 in codes


def test_seats_held_column_is_kept_consistent(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=None)
    ticket = booked_ticket(client, company, admin, scripted, pkg, adults=3)
    # The package becomes limited after the booking: cancelling must not add seats that were never taken.
    body = {"title": pkg["title"], "destination": "Male", "country": "Maldives", "duration_days": 6,
            "price_per_person": 2000, "departure_dates": pkg["departure_dates"], "seats_available": 5}
    client.put(f"/api/packages/{pkg['id']}", headers=admin, json=body)
    client.patch(f"/api/tickets/{ticket['id']}", headers=admin, json={"status": "cancelled"})
    assert client.get(f"/api/packages/{pkg['id']}", headers=admin).json()["seats_available"] == 5
    with SessionLocal() as db:
        assert db.get(Ticket, ticket["id"]).seats_held == 0
