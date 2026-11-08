"""The platform owner's "Create demo company": a ready-made Omani agency for presentations."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import Company, Customer, Message, Ticket, TicketEvent, TicketStatus, TravelPackage, User
from app.security import verify_password
from app.services import seats
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, login, make_company

URL = "/api/system/demo-company"
ALL_STATUSES = {s.value for s in TicketStatus}


def create_demo(client, owner, **body):
    r = client.post(URL, headers=owner, json={"name": "Muscat Horizons Travel", **body})
    assert r.status_code == 201, r.text
    return r.json()


def login_as(client, demo, role="company_admin"):
    entry = next(x for x in demo["logins"] if x["role"] == role)
    return login(client, entry["email"], entry["password"])


def test_only_the_platform_owner_can_create_a_demo_company(client, owner, company_a):
    _, admin = company_a
    assert client.post(URL, json={"name": "Demo"}).status_code == 401
    assert client.post(URL, headers=admin, json={"name": "Demo"}).status_code == 403
    assert client.post(URL, headers=owner, json={"name": "Demo"}).status_code == 201


def test_demo_company_has_realistic_data(client, owner):
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    demo = create_demo(client, owner)
    company = demo["company"]
    assert company["slug"] == "muscat-horizons-travel"
    assert demo["customer_page"] == "/c/muscat-horizons-travel"
    assert company["currency"] == "OMR" and company["package_count"] == 12
    assert {x["role"] for x in demo["logins"]} == {"company_admin", "support", "ticket_agent"}
    assert [x["role"] for x in demo["logins"]].count("support") == 2
    assert demo["counts"]["training"] >= 15

    admin = login_as(client, demo)
    settings = client.get("/api/company", headers=admin).json()
    assert settings["ai_agent_name"] == "Sara"
    assert "سارة" in settings["ai_welcome_message_ar"] and "Sara" in settings["ai_welcome_message"]
    for policy in ("30% deposit", "Cancellation", "visa", "Bank transfer", "Sunday to Thursday"):
        assert policy.lower() in settings["knowledge_base"].lower()

    packages = client.get("/api/packages", headers=admin).json()
    assert len(packages) == 12
    today = datetime.now(timezone.utc).date().isoformat()
    for p in packages:
        assert p["currency"] == "OMR" and p["price_per_person"] > 0 and p["hotel_name"]
        assert len(p["departure_dates"]) >= 3 and all(d > today for d in p["departure_dates"])
        assert p["includes"] and p["excludes"] and p["seats_available"]
        assert " · " in p["title"]  # English · Arabic
        assert any("؀" <= ch <= "ۿ" for ch in " ".join(p["tags"]))
    assert sum(p["is_featured"] for p in packages) >= 4
    assert any(p["child_price"] for p in packages)

    training = client.get("/api/training", headers=admin).json()
    assert 15 <= len(training) <= 20
    assert any("؀" <= ch <= "ۿ" for ch in training[0]["question"] + training[1]["question"])

    tickets = client.get("/api/tickets", headers=admin).json()
    assert 10 <= len(tickets) <= 15
    assert {t["status"] for t in tickets} == ALL_STATUSES
    for t in tickets:
        if t["status"] in ("paid", "confirmed"):
            assert t["payment_reference"]
        events = client.get(f"/api/tickets/{t['id']}/events", headers=admin).json()
        assert events[0]["action"] == "created"
        if t["status"] != "pending_payment":
            assert any(e["action"] == "status" for e in events)

    convs = client.get("/api/conversations", headers=admin).json()
    assert len(convs) >= 30
    assert {c["channel"] for c in convs} == {"web", "whatsapp"}
    assert {c["status"] for c in convs} == {"ai", "human", "closed"}
    oldest = min(datetime.fromisoformat(c["created_at"]) for c in convs)
    assert oldest < datetime.now(timezone.utc) - timedelta(days=25)  # spread over the last month
    waiting = [c for c in convs if c["status"] == "human" and not c["assigned_to"]]
    assert waiting
    detail = client.get(f"/api/conversations/{convs[0]['id']}", headers=admin).json()
    assert any(m["sender"] == "customer" for m in detail["messages"])

    dash = client.get("/api/dashboard", headers=admin).json()
    assert dash["confirmed_value"] > 0 and dash["pipeline_value"] > 0
    assert dash["conversations_waiting"] == len(waiting)
    analytics = client.get("/api/dashboard/analytics?days=30", headers=admin).json()
    assert analytics["funnel"]["conversations"] >= 30 and analytics["funnel"]["paid_or_confirmed"] >= 4
    assert analytics["handled_by_ai"] > 0 and analytics["handed_to_team"] > 0
    assert analytics["top_packages"]

    # Sample customers are fictional and nothing went out on WhatsApp.
    assert wa.sent == [] and wa.read == []
    assert company["whatsapp_connected"] is False
    with SessionLocal() as db:
        customers = db.scalars(select(Customer).where(Customer.company_id == company["id"])).all()
        for c in customers:
            assert c.phone.startswith("+968 9000 0")
            assert c.email is None or c.email.endswith("@example.com")
            assert c.whatsapp_id is None or c.whatsapp_id.startswith("demo-")
        assert any(c.whatsapp_id for c in customers)


def test_without_sample_activity(client, owner):
    demo = create_demo(client, owner, include_activity=False, language="en")
    admin = login_as(client, demo)
    assert client.get("/api/tickets", headers=admin).json() == []
    assert client.get("/api/conversations", headers=admin).json() == []
    packages = client.get("/api/packages", headers=admin).json()
    assert len(packages) == 12 and all(" · " not in p["title"] for p in packages)


def _active_holds(db, company_id):
    """Seats held on each (package, date), counted like services/seats.py."""
    now = datetime.now(timezone.utc)
    held = defaultdict(int)
    for t in db.scalars(select(Ticket).where(Ticket.company_id == company_id)):
        expired = t.status == TicketStatus.PENDING_PAYMENT and t.seats_held and \
            (t.seats_held_at or t.created_at) < now - timedelta(hours=seats.hold_hours())
        if t.seats_held and t.status != TicketStatus.CANCELLED and not expired:
            held[(t.package_id, t.departure_date)] += t.seats_held
    return held


def test_demo_tickets_keep_seat_counts_correct(client, owner):
    demo = create_demo(client, owner)
    cid = demo["company"]["id"]
    admin = login_as(client, demo)
    with SessionLocal() as db:
        tickets = db.scalars(select(Ticket).where(Ticket.company_id == cid)).all()
        for t in tickets:
            travellers = t.adults + t.children
            if t.status == TicketStatus.CANCELLED:
                assert t.seats_held == 0
            elif t.seats_held == 0:
                # Only an unpaid booking whose hold ran out, with the release in its history.
                assert t.status == TicketStatus.PENDING_PAYMENT and seats.was_released(db, t)
            else:
                assert t.seats_held == travellers
        released = [t for t in tickets if t.seats_held == 0 and t.status == TicketStatus.PENDING_PAYMENT]
        assert len(released) == 1
        event = db.scalar(select(TicketEvent).where(TicketEvent.ticket_id == released[0].id,
                                                    TicketEvent.action == seats.RELEASED_ACTION))
        assert event.created_at < datetime.now(timezone.utc)
        held = _active_holds(db, cid)
        packages = {p.id: p for p in db.scalars(select(TravelPackage).where(TravelPackage.company_id == cid))}
        for (package_id, dep), n in held.items():
            assert n <= packages[package_id].seats_available, (package_id, dep, n)  # never overbooked
            assert dep in packages[package_id].departure_dates

    # The packages page shows exactly the seats left after the holds.
    for p in client.get("/api/packages", headers=admin).json():
        for dep, left in p["seats_left_by_date"].items():
            assert left == p["seats_available"] - held.get((p["id"], dep), 0)
    # One trip is nearly full, so the page shows "few seats left".
    assert any(left <= 2 for p in client.get("/api/packages", headers=admin).json()
               for left in p["seats_left_by_date"].values())


def test_demo_pending_holds_expire_like_real_bookings(client, owner, monkeypatch):
    demo = create_demo(client, owner)
    admin = login_as(client, demo)
    pending = [t for t in client.get("/api/tickets", headers=admin).json()
               if t["status"] == "pending_payment" and t["seats_held"]]
    assert pending
    later = datetime.now(timezone.utc) + timedelta(hours=49)
    monkeypatch.setattr(seats, "_now", lambda: later)
    tickets = {t["id"]: t for t in client.get("/api/tickets", headers=admin).json()}
    for t in pending:
        assert tickets[t["id"]]["seats_held"] == 0 and tickets[t["id"]]["seats_released"]
    # Paid and confirmed bookings keep their seats.
    assert all(t["seats_held"] for t in tickets.values() if t["status"] in ("paid", "confirmed"))


def test_logins_work_and_passwords_are_never_stored(client, owner, caplog):
    caplog.set_level(logging.DEBUG)
    demo = create_demo(client, owner)
    passwords = [x["password"] for x in demo["logins"]]
    assert len(set(passwords)) == 4
    for x in demo["logins"]:
        pw = x["password"]
        assert len(pw) >= 16 and any(c.isdigit() for c in pw) and any(c.isupper() for c in pw)
        assert x["email"].endswith("@muscat-horizons-travel.example")
        headers = login(client, x["email"], pw)
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["role"] == x["role"] and me["company"]["slug"] == "muscat-horizons-travel"
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.company_id == demo["company"]["id"])).all()
        for u in users:
            assert u.password_hash not in passwords and u.password_hash.startswith("$2")
            assert any(verify_password(pw, u.password_hash) for pw in passwords)
        # No column of any demo row holds a password in plain text.
        for model in (User, Company, Message, Ticket, TicketEvent):
            for row in db.scalars(select(model)):
                text = " ".join(str(getattr(row, c.key)) for c in model.__table__.columns)
                assert not any(pw in text for pw in passwords), model
    assert not any(pw in caplog.text for pw in passwords)
    # Shown once: nothing else returns them.
    company_id = demo["company"]["id"]
    for path in (f"/api/system/companies/{company_id}", f"/api/system/companies/{company_id}/users",
                 "/api/system/companies"):
        assert not any(pw in client.get(path, headers=owner).text for pw in passwords)


def test_admin_email_can_be_the_owners_choice(client, owner):
    _, other_admin = make_company(client, owner, name="Other Co", admin_email="ali@agency.com")
    demo = create_demo(client, owner, admin_email="ali@agency.com", slug="ali-demo")
    entry = next(x for x in demo["logins"] if x["role"] == "company_admin")
    assert entry["email"] == "ali@agency.com"
    # Same email in two companies: the password picks the account.
    headers = login(client, "ali@agency.com", entry["password"])
    assert client.get("/api/auth/me", headers=headers).json()["company"]["slug"] == "ali-demo"


def test_two_demo_companies_coexist_and_are_isolated(client, owner):
    a = create_demo(client, owner)
    b = create_demo(client, owner)
    assert a["company"]["slug"] == "muscat-horizons-travel" and b["company"]["slug"] == "muscat-horizons-travel-2"
    assert {x["email"] for x in a["logins"]}.isdisjoint({x["email"] for x in b["logins"]})
    admin_a, admin_b = login_as(client, a), login_as(client, b)
    tickets_a = client.get("/api/tickets", headers=admin_a).json()
    tickets_b = client.get("/api/tickets", headers=admin_b).json()
    assert len(tickets_a) == len(tickets_b)
    assert {t["id"] for t in tickets_a}.isdisjoint({t["id"] for t in tickets_b})
    assert client.get(f"/api/tickets/{tickets_b[0]['id']}", headers=admin_a).status_code == 404
    conv_b = client.get("/api/conversations", headers=admin_b).json()[0]
    assert client.get(f"/api/conversations/{conv_b['id']}", headers=admin_a).status_code == 404
    pkg_b = client.get("/api/packages", headers=admin_b).json()[0]
    assert client.get(f"/api/packages/{pkg_b['id']}", headers=admin_a).status_code == 404
    # Each company's seats only count its own bookings.
    with SessionLocal() as db:
        assert _active_holds(db, a["company"]["id"]).keys().isdisjoint(_active_holds(db, b["company"]["id"]).keys())


def test_web_address_rules(client, owner, company_a):
    company, _ = company_a
    r = client.post(URL, headers=owner, json={"name": "Demo", "slug": company["slug"]})
    assert r.status_code == 409
    assert client.post(URL, headers=owner, json={"name": "Demo", "slug": "admin"}).status_code == 422
    assert client.post(URL, headers=owner, json={"name": "Demo", "slug": "Bad Slug"}).status_code == 422
    # An Arabic name gets an English web address.
    demo = create_demo(client, owner, name="سفريات الأفق")
    assert demo["company"]["slug"] == "demo-travel" and demo["company"]["name"] == "سفريات الأفق"


def test_demo_creation_is_rate_limited(client, owner):
    for i in range(3):
        create_demo(client, owner, include_activity=False, slug=f"demo-{i}")
    r = client.post(URL, headers=owner, json={"name": "One more", "include_activity": False})
    assert r.status_code == 429


def test_demo_customer_page_and_ai_search(client, owner, scripted):
    demo = create_demo(client, owner)
    slug = demo["company"]["slug"]
    info = client.get(f"/api/public/companies/{slug}").json()
    assert info["ai_agent_name"] == "Sara" and info["currency"] == "OMR"
    assert info["branding"]["primary_color"] == "#a8641f" and info["branding"]["about_ar"]
    public = client.get(f"/api/public/companies/{slug}/packages").json()
    assert len(public) == 12 and public[0]["is_featured"]

    seen = {}

    def answer(messages):
        import json
        seen["results"] = json.loads(messages[-1]["content"])["results"]
        return LLMResponse("عندنا عمرة مميزة")

    scripted([LLMResponse(None, [ToolCall("s1", "search_packages", {"query": "عمرة"})]), answer])
    r = client.post(f"/api/public/companies/{slug}/chats", json={"lang": "ar"})
    assert r.status_code == 201 and "سارة" in r.json()["messages"][0]["content"]
    token = r.json()["token"]
    out = client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "ابغى عمرة"}).json()
    assert out["status"] == "ai"
    assert seen["results"][0]["title"].startswith("Umrah Premium")


@pytest.mark.parametrize("language", ["en", "ar"])
def test_package_language(client, owner, language):
    demo = create_demo(client, owner, include_activity=False, language=language)
    admin = login_as(client, demo)
    titles = [p["title"] for p in client.get("/api/packages", headers=admin).json()]
    arabic = [any("؀" <= ch <= "ۿ" for ch in t) for t in titles]
    assert all(arabic) if language == "ar" else not any(arabic)


def test_luxury_concierge_demo_company(client, owner):
    set_whatsapp_sender(FakeWhatsApp())
    demo = create_demo(client, owner, name="Escape", slug="werescape", profile="luxury")
    assert demo["customer_page"] == "/c/werescape" and demo["company"]["package_count"] == 12
    assert demo["counts"]["tickets"] >= 10 and demo["counts"]["conversations"] >= 20

    admin = login_as(client, demo)
    settings = client.get("/api/company", headers=admin).json()
    assert "concierge" in settings["ai_welcome_message"] and "Escape" in settings["ai_welcome_message"]
    assert "concierge" in settings["knowledge_base"].lower()
    assert client.get("/api/company/branding", headers=admin).json()["bg_color"] == "#222a20"
    packages = client.get("/api/packages", headers=admin).json()
    assert any("VIP Umrah" in p["title"] for p in packages)
    assert min(float(p["price_per_person"]) for p in packages) >= 300

    # The sample answers follow the luxury catalogue, not the family one.
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.slug == "werescape"))
        texts = [m.content for m in db.scalars(select(Message)) if m.content]
        assert company is not None
    joined = "\n".join(texts)
    assert "Tbilisi & Batumi" not in joined and "Georgia: Tbilisi & Kazbegi is 7 days from 845.000 OMR" in joined
    assert "{" + "budget}" not in joined


def test_unknown_profile_is_refused(client, owner):
    r = client.post(URL, headers=owner, json={"name": "Demo", "profile": "space"})
    assert r.status_code == 422
