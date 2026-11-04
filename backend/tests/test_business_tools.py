"""Business tools: error capture and System health, Customers, CSV exports and the activity log."""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import Body, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app import diagnostics
from app.database import Base, SessionLocal
from app.main import app
from app.migrations import upgrade
from app.models import (
    AuditEvent,
    Company,
    Conversation,
    Customer,
    ErrorEvent,
    Message,
    Ticket,
    TicketEvent,
    User,
)
from app.ratelimit import limiter
from app.security import random_token
from app.timeutil import start_of_local_day
from tests.conftest import login, make_company, make_package


# --- helpers -----------------------------------------------------------------------------------

def _staff(client, admin, email, role, permissions=None):
    body = {"email": email, "full_name": f"{role} person", "password": "Password123", "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post("/api/users", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json(), login(client, email, "Password123")


def _company_id(client, headers) -> int:
    return client.get("/api/auth/me", headers=headers).json()["company"]["id"]


def _customer(company_id, name, phone=None, email=None, channels=("web",), tickets=(), when=None):
    """A customer with one conversation per channel and the given tickets (status, total, created_at)."""
    when = when or datetime.now(timezone.utc)
    with SessionLocal() as db:
        c = Customer(company_id=company_id, name=name, phone=phone, email=email, created_at=when)
        db.add(c)
        db.flush()
        conv_ids = []
        for i, ch in enumerate(channels):
            conv = Conversation(company_id=company_id, customer_id=c.id, channel=ch, created_at=when + timedelta(minutes=i),
                                last_message_at=when + timedelta(minutes=i + 1))
            db.add(conv)
            db.flush()
            conv_ids.append(conv.id)
            db.add(Message(conversation_id=conv.id, sender="customer", content="hello", created_at=when))
        ticket_ids = []
        for status, total, created in tickets:
            t = Ticket(company_id=company_id, reference=random_token(6)[:8].upper(), customer_id=c.id,
                       conversation_id=conv_ids[0] if conv_ids else None, package_title="Salalah Khareef",
                       departure_date="2030-08-01", adults=2, children=0, lead_traveler_name=name or "Guest",
                       contact_phone=phone, total_price=Decimal(str(total)), currency="OMR", status=status,
                       created_at=created or when, updated_at=created or when)
            db.add(t)
            db.flush()
            ticket_ids.append(t.id)
        db.commit()
        return c.id, conv_ids, ticket_ids


def _csv(response) -> list[list[str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def _errors():
    with SessionLocal() as db:
        return db.scalars(select(ErrorEvent).order_by(ErrorEvent.id)).all()


def _audit(company_id):
    with SessionLocal() as db:
        return db.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id).order_by(AuditEvent.id)).all()


@pytest.fixture
def two(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="admin@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    return a, admin_a, b, admin_b


# --- 1. Error capture ----------------------------------------------------------------------------

SECRET_BODY = "BODY-SECRET-hunter2"


@pytest.fixture
def boom_route():
    async def boom(request: Request, payload: dict = Body(default={})):
        raise RuntimeError("Could not charge ahmed.ali@example.com with key sk-live-ABCDEF1234567890abcdef "
                           "password=hunter2 phone +968 9123 4567")

    app.add_api_route("/api/test-boom/{key}", boom, methods=["POST"])
    route = app.router.routes[-1]
    yield
    app.router.routes.remove(route)


def test_server_errors_are_recorded_without_secrets(client, two, boom_route):
    a, admin_a, _, _ = two
    me = client.get("/api/auth/me", headers=admin_a).json()
    token = admin_a["Authorization"].split()[1]
    quiet = TestClient(app, raise_server_exceptions=False)
    key = "Zx9" + "k" * 30
    r = quiet.post(f"/api/test-boom/{key}?token=QUERY-SECRET&email=x@y.com", headers=admin_a,
                   json={"password": SECRET_BODY, "note": SECRET_BODY})
    assert r.status_code == 500
    rows = _errors()
    assert len(rows) == 1
    e = rows[0]
    assert (e.source, e.method, e.status, e.error_type) == ("server", "POST", 500, "RuntimeError")
    assert e.path == "/api/test-boom/:key"
    assert e.user_id == me["id"] and e.company_id == a["id"]
    stored = " ".join(str(getattr(e, c.name)) for c in ErrorEvent.__table__.columns)
    for secret in (SECRET_BODY, "hunter2", "QUERY-SECRET", "sk-live-ABCDEF1234567890abcdef", token, key,
                   "ahmed.ali@example.com", "9123 4567"):
        assert secret not in stored
    assert "a***@example.com" in e.message and "password=[hidden]" in e.message
    assert len(e.message) <= 300

    # The same error again within the hour only raises the count.
    quiet.post(f"/api/test-boom/{key}", headers=admin_a, json={})
    rows = _errors()
    assert len(rows) == 1 and rows[0].count == 2


def test_5xx_answers_and_logged_errors_are_recorded(client, two):
    _, admin_a, _, _ = two
    webhook = client.get("/api/company/whatsapp", headers=admin_a).json()["webhook_path"]
    # No app secret: the company's webhook answers 503, the owner must see that.
    assert client.post(webhook + "?hub.verify_token=abc", content=b'{"secret": "x"}').status_code == 503
    logging.getLogger("app.services.conversations").error("Could not send with token=EAAG1234567890abcdefXYZ")
    rows = _errors()
    assert [(r.status, r.method) for r in rows] == [(503, "POST"), (None, "LOG")]
    assert rows[0].path == "/api/webhooks/whatsapp/c/:key"
    assert "EAAG1234567890" not in (rows[1].message or "") and "token=[hidden]" in rows[1].message
    assert rows[1].path == "app/services/conversations"


def test_scrub_and_clean_path():
    s = diagnostics.scrub("Bearer abc.def.ghi Authorization=Basic Zm9vOmJhcg== jwt eyJhbGciOiJI.eyJzdWIiOjF9.c2lnbmF0dXJl "
                          "mail sara@oman.om " + "x" * 400)
    assert "abc.def.ghi" not in s and "Zm9vOmJhcg" not in s and "eyJ" not in s and "sara@" not in s
    assert len(s) <= 300
    assert diagnostics.clean_path("/api/x?token=1#frag") == "/api/x"
    assert diagnostics.clean_path("https://evil.example/api/a/b?c=d") == "/api/a/b"
    assert diagnostics.clean_path("/c/sunrise-travel-and-tours") == "/c/sunrise-travel-and-tours"
    assert diagnostics.clean_path("/api/customers/by/sara@oman.om") == "/api/customers/by/:email"


def test_errors_are_pruned_by_age_and_count(client, monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(days=31)
    with SessionLocal() as db:
        db.add(ErrorEvent(created_at=old, last_seen_at=old, source="server", fingerprint="old", count=1))
        db.commit()
    monkeypatch.setattr(diagnostics, "MAX_ROWS", 3)
    for i in range(5):
        diagnostics.record_error("server", method="GET", path=f"/api/x{i}", status=500, message=f"m{i}")
    rows = _errors()
    assert [r.path for r in rows] == ["/api/x2", "/api/x3", "/api/x4"]


# --- 2. Client error reports ---------------------------------------------------------------------

def _report(client, headers=None, **body):
    payload = {"kind": "api", "message": "Request failed (404)", "page": "/app/branding?x=1",
               "api_path": "/api/company/branding?y=2", "method": "GET", "status": 404, "build": "2026-11-01T10:00:00Z"}
    payload.update(body)
    return client.post("/api/client-errors", headers=headers or {}, json=payload)


def test_client_errors_are_stored_and_scrubbed(client, two):
    a, admin_a, _, _ = two
    assert _report(client, admin_a, message="token=abcdef123 failed for sara@oman.om").status_code == 204
    assert _report(client, kind="crash", api_path=None, method=None, status=None,
                   message="TypeError: x is undefined").status_code == 204  # no login needed
    rows = _errors()
    assert len(rows) == 2
    api_err, crash = rows
    assert (api_err.source, api_err.method, api_err.path, api_err.page, api_err.status) == \
        ("client", "GET", "/api/company/branding", "/app/branding", 404)
    assert api_err.company_id == a["id"] and api_err.error_type == "api"
    assert "abcdef123" not in api_err.message and "sara@" not in api_err.message
    assert api_err.release == "web 2026-11-01T10:00:00Z"
    assert (crash.method, crash.path, crash.user_id) == ("PAGE", "/app/branding", None)
    # Bad reports are refused.
    assert _report(client, kind="whatever").status_code == 422
    assert client.post("/api/client-errors", content=b"not json").status_code == 422


def test_client_errors_size_limit(client):
    assert _report(client, message="x" * 1001).status_code == 422
    big = b'{"kind": "error", "message": "' + b"x" * 5000 + b'"}'
    assert client.post("/api/client-errors", content=big, headers={"content-type": "application/json"}).status_code == 413
    assert _errors() == []


def test_client_errors_rate_limits(client, two):
    _, admin_a, _, _ = two
    for i in range(10):
        assert _report(client, admin_a, message=f"m{i}").status_code == 204
    assert _report(client, admin_a, message="one more").status_code == 429  # per user
    limiter.reset()
    for i in range(20):
        assert _report(client, message=f"anon {i}").status_code == 204
    assert _report(client, message="too many").status_code == 429  # per address
    assert len(_errors()) == 30


# --- 3. System health (owner only) ----------------------------------------------------------------

def test_system_health_is_owner_only(client, owner, two):
    a, admin_a, b, _ = two
    for path in ("/api/system/health", "/api/system/errors"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=admin_a).status_code == 403
    _customer(a["id"], "WA customer", channels=("whatsapp",))
    _customer(b["id"], "IG customer", channels=("instagram",))
    _report(client, admin_a, message="alpha problem")
    diagnostics.record_error("server", method="GET", path="/api/x", status=500, message="server problem")

    h = client.get("/api/system/health", headers=owner).json()
    assert h["database"]["ok"] is True and h["database"]["latency_ms"] >= 0
    assert h["version"] and h["release"] and h["started_at"]
    channels = {c["channel"]: c for c in h["channels"]}
    assert channels["whatsapp"]["incoming_24h"] == 1 and channels["instagram"]["incoming_24h"] == 1
    assert h["errors_24h"] == {"server": 1, "client": 1}

    everything = client.get("/api/system/errors", headers=owner).json()
    assert len(everything) == 2
    only_client = client.get("/api/system/errors?source=client", headers=owner).json()
    assert [e["message"] for e in only_client] == ["alpha problem"]
    assert only_client[0]["company_name"] == "Alpha Travel"
    assert client.get(f"/api/system/errors?company_id={b['id']}", headers=owner).json() == []
    # Older than the period: not listed.
    with SessionLocal() as db:
        for e in db.scalars(select(ErrorEvent)):
            e.last_seen_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
    assert client.get("/api/system/errors?hours=24", headers=owner).json() == []
    assert len(client.get("/api/system/errors?hours=168", headers=owner).json()) == 2


# --- 4. Customers -----------------------------------------------------------------------------------

def test_customers_are_isolated_and_need_permissions(client, two):
    a, admin_a, b, admin_b = two
    mine, _, _ = _customer(a["id"], "Salim Al Harthy", phone="+968 9111 2222", email="salim@example.com",
                           channels=("web", "whatsapp"), tickets=[("confirmed", 300, None), ("cancelled", 99, None),
                                                                 ("pending_payment", 100, None)])
    theirs, _, _ = _customer(b["id"], "Beta customer", phone="+968 9333 4444")
    _customer(a["id"], "No booking yet", channels=("instagram",))

    data = client.get("/api/customers", headers=admin_a).json()
    assert data["total"] == 2 and data["currency"] == "OMR"
    names = [c["name"] for c in data["customers"]]
    assert "Beta customer" not in names
    salim = next(c for c in data["customers"] if c["id"] == mine)
    assert salim["channels"] == ["web", "whatsapp"] and salim["conversations"] == 2
    assert salim["bookings"] == 2 and salim["total_booked"] == 400 and salim["total_paid"] == 300

    assert [c["name"] for c in client.get("/api/customers?has_booking=true", headers=admin_a).json()["customers"]] \
        == ["Salim Al Harthy"]
    assert [c["name"] for c in client.get("/api/customers?channel=instagram", headers=admin_a).json()["customers"]] \
        == ["No booking yet"]
    assert [c["name"] for c in client.get("/api/customers?q=9111", headers=admin_a).json()["customers"]] \
        == ["Salim Al Harthy"]
    assert client.get("/api/customers?sort=booked", headers=admin_a).json()["customers"][0]["id"] == mine

    # Another company's customer does not exist for this one.
    assert client.get(f"/api/customers/{theirs}", headers=admin_a).status_code == 404
    assert client.patch(f"/api/customers/{theirs}", headers=admin_a, json={"name": "x"}).status_code == 404
    assert client.get(f"/api/customers/{mine}", headers=admin_b).status_code == 404
    assert all(c["id"] != mine for c in client.get("/api/customers", headers=admin_b).json()["customers"])

    detail = client.get(f"/api/customers/{mine}", headers=admin_a).json()
    assert len(detail["conversation_list"]) == 2 and len(detail["ticket_list"]) == 3

    # Ticket employees see customers but can't change them or download the list.
    _, agent = _staff(client, admin_a, "agent@alpha.com", "ticket_agent")
    assert client.get("/api/customers", headers=agent).status_code == 200
    assert client.patch(f"/api/customers/{mine}", headers=agent, json={"notes": "x"}).status_code == 403
    assert client.get("/api/customers/export.csv", headers=agent).status_code == 403
    # Support has customers.manage by default.
    support_user, support = _staff(client, admin_a, "support@alpha.com", "support")
    assert "customers.manage" in support_user["permissions"]
    r = client.patch(f"/api/customers/{mine}", headers=support,
                     json={"notes": "Prefers calls after 6pm", "tags": ["VIP", "vip", " family "], "email": ""})
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "Prefers calls after 6pm" and r.json()["tags"] == ["VIP", "family"]
    assert r.json()["email"] is None
    assert client.patch(f"/api/customers/{mine}", headers=support, json={"email": "not-an-email"}).status_code == 422
    # Support has no tickets.view: the bookings list is not sent.
    nobody, no_view = _staff(client, admin_a, "nobody@alpha.com", "support", permissions=["packages.view"])
    assert client.get("/api/customers", headers=no_view).status_code == 403
    # A support account without tickets.view does not get the booking list.
    _, chats_only = _staff(client, admin_a, "chats@alpha.com", "support",
                           permissions=["conversations.view", "customers.manage"])
    d = client.get(f"/api/customers/{mine}", headers=chats_only).json()
    assert d["ticket_list"] == [] and d["can_see_tickets"] is False


def test_customer_csv_is_protected_against_formulas(client, two):
    a, admin_a, b, _ = two
    _customer(a["id"], "=HYPERLINK(\"http://evil\",\"x\")", phone="+968 9000 0000", email="@cmd|calc")
    _customer(a["id"], "-2+3", tickets=[("paid", 12.5, None)])
    _customer(b["id"], "Other company customer")
    rows = _csv(client.get("/api/customers/export.csv", headers=admin_a))
    assert rows[0][0] == "Name"
    body = rows[1:]
    assert len(body) == 2
    cells = [cell for row in body for cell in row]
    assert "'=HYPERLINK(\"http://evil\",\"x\")" in cells and "'+968 9000 0000" in cells and "'@cmd|calc" in cells
    assert "'-2+3" in cells and "12.500" in cells
    assert not any(cell.startswith(("=", "+", "-", "@")) for cell in cells)
    assert "Other company customer" not in cells


# --- 5. Exports -------------------------------------------------------------------------------------

def test_exports_filter_dates_and_stay_in_the_company(client, two):
    a, admin_a, b, admin_b = two
    day = lambda d: start_of_local_day(datetime(2030, 1, d).date()) + timedelta(hours=10)  # noqa: E731
    _, _, (t1, t2, t3) = _customer(a["id"], "Alpha guest", tickets=[
        ("pending_payment", 100, day(1)), ("confirmed", 200, day(5)), ("cancelled", 300, day(10))])
    _customer(b["id"], "Beta guest", tickets=[("confirmed", 999, day(5))])
    with SessionLocal() as db:
        db.add(TicketEvent(ticket_id=t2, actor="Alpha Admin", action="status", old_value="in_progress",
                           new_value="paid", created_at=day(6)))
        db.commit()

    rows = _csv(client.get("/api/exports/tickets.csv?date_from=2030-01-01&date_to=2030-01-05", headers=admin_a))
    assert [r[2] for r in rows[1:]] == ["pending_payment", "confirmed"]  # the 5th is included
    assert all("Beta guest" not in r for r in rows)
    rows = _csv(client.get("/api/exports/tickets.csv?date_from=2030-01-02&status=cancelled", headers=admin_a))
    assert [r[2] for r in rows[1:]] == ["cancelled"]
    rows = _csv(client.get("/api/exports/tickets.csv?status=open", headers=admin_a))
    assert [r[2] for r in rows[1:]] == ["pending_payment"]
    assert client.get("/api/exports/tickets.csv?date_from=2030-01-05&date_to=2030-01-01",
                      headers=admin_a).status_code == 400

    pay = _csv(client.get("/api/exports/payments.csv?date_from=2030-01-06&date_to=2030-01-06", headers=admin_a))
    assert len(pay) == 2 and pay[1][4] == "200.000" and pay[1][8] == "Alpha Admin"
    assert len(_csv(client.get("/api/exports/payments.csv?date_to=2030-01-05", headers=admin_a))) == 1
    beta = _csv(client.get("/api/exports/payments.csv", headers=admin_b))
    assert [r[4] for r in beta[1:]] == ["999.000"]

    _, agent = _staff(client, admin_a, "agent@alpha.com", "ticket_agent")  # no reports.view
    assert client.get("/api/exports/tickets.csv", headers=agent).status_code == 403
    assert client.get("/api/exports/payments.csv", headers=agent).status_code == 403


# --- 6. Activity log --------------------------------------------------------------------------------

def test_key_actions_are_logged_per_company(client, owner, two):
    a, admin_a, b, admin_b = two
    login(client, "admin@alpha.com", "AdminPass123!")
    pkg = make_package(client, admin_a, title="Jebel Akhdar weekend")
    body = {k: pkg[k] for k in ("title", "destination", "country", "description", "duration_days",
                                 "price_per_person", "departure_dates")}
    assert client.put(f"/api/packages/{pkg['id']}", headers=admin_a, json={**body, "title": "Jebel Akhdar 3 days"}
                      ).status_code == 200
    user, _ = _staff(client, admin_a, "agent@alpha.com", "ticket_agent")
    assert client.patch(f"/api/users/{user['id']}", headers=admin_a, json={"is_active": False}).status_code == 200
    _, _, (ticket,) = _customer(a["id"], "Guest", tickets=[("pending_payment", 50, None)])
    assert client.patch(f"/api/tickets/{ticket}", headers=admin_a, json={"status": "in_progress"}).status_code == 200
    assert client.patch(f"/api/tickets/{ticket}", headers=admin_a,
                        json={"payment_reference": "RCPT-778899"}).status_code == 200
    assert client.patch("/api/company/branding", headers=admin_a, json={"primary_color": "#0E7C66"}).status_code == 200
    assert client.post("/api/training", headers=admin_a, json={"question": "Visa?", "answer": "Yes"}).status_code == 201
    r = client.patch("/api/company", headers=admin_a,
                     json={"whatsapp_access_token": "EAAG-very-secret-token-123", "contact_email": "hi@alpha.com"})
    assert r.status_code == 200, r.text
    assert client.delete(f"/api/packages/{pkg['id']}", headers=admin_a).status_code == 204

    events = _audit(a["id"])
    actions = [e.action for e in events]
    for expected in ("auth.login", "package.created", "package.updated", "user.created", "user.disabled",
                     "ticket.status", "ticket.payment", "branding.saved", "ai.training", "whatsapp.credentials",
                     "settings.saved", "package.deleted"):
        assert expected in actions, (expected, actions)
    status = next(e for e in events if e.action == "ticket.status")
    assert status.detail == "pending_payment → in_progress" and status.actor == "Alpha Travel Admin"
    stored = " ".join(f"{e.target} {e.detail}" for e in events)
    assert "EAAG-very-secret-token-123" not in stored and "RCPT-778899" not in stored and "Password123" not in stored
    assert {e.action for e in _audit(b["id"])} <= {"auth.login", "user.created"}  # its own first admin

    # The company admin's Activity page, with filters; another company sees nothing of it.
    page = client.get("/api/activity", headers=admin_a).json()
    assert page["items"][0]["action"] == "package.deleted" and page["items"][0]["label"] == "Package deleted"
    tickets_only = client.get("/api/activity?action=ticket", headers=admin_a).json()["items"]
    assert {i["action"] for i in tickets_only} == {"ticket.status", "ticket.payment"}
    assert all(i["action"] != "package.created" for i in client.get("/api/activity", headers=admin_b).json()["items"])
    paged = client.get("/api/activity?limit=2", headers=admin_a).json()
    assert len(paged["items"]) == 2 and paged["has_more"]
    more = client.get(f"/api/activity?limit=2&before_id={paged['items'][-1]['id']}", headers=admin_a).json()
    assert more["items"][0]["id"] < paged["items"][-1]["id"]

    # Only company admins (not support) and the owner.
    _, support = _staff(client, admin_a, "support@alpha.com", "support")
    assert client.get("/api/activity", headers=support).status_code == 403
    assert client.get("/api/activity", headers=owner).status_code == 403
    owner_view = client.get(f"/api/system/companies/{a['id']}/activity", headers=owner).json()
    assert any(i["action"] == "ticket.payment" for i in owner_view["items"])
    assert client.get(f"/api/system/companies/{a['id']}/activity", headers=admin_a).status_code == 403
    assert client.get("/api/system/companies/99999/activity", headers=owner).status_code == 404


def test_customer_edits_are_logged(client, two):
    a, admin_a, _, _ = two
    cid, _, _ = _customer(a["id"], "Old name")
    client.patch(f"/api/customers/{cid}", headers=admin_a, json={"name": "New name", "notes": "VIP"})
    e = [x for x in _audit(a["id"]) if x.action == "customer.updated"]
    assert len(e) == 1 and e[0].target == "New name" and e[0].detail == "name, notes"


# --- 7. Upgrade: existing support accounts get customers.manage once ----------------------------------

def test_upgrade_gives_support_customers_manage_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/old.db")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE customers DROP COLUMN notes"))
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        db.add(Company(id=1, name="Old", slug="old"))
        db.flush()
        for i, (role, perms) in enumerate([("support", ["conversations.view", "conversations.reply"]),
                                           ("support", ["packages.view"]),
                                           ("ticket_agent", ["conversations.view"])]):
            db.add(User(company_id=1, email=f"u{i}@old.com", full_name=f"U{i}", password_hash="x", role=role,
                        permissions=perms))
        db.commit()
    upgrade(engine)
    with Session(engine) as db:
        users = db.scalars(select(User).order_by(User.id)).all()
        assert users[0].permissions == ["conversations.view", "conversations.reply", "customers.manage"]
        assert users[1].permissions == ["packages.view"] and users[2].permissions == ["conversations.view"]
        first_id = users[0].id
        users[0].permissions = ["conversations.view"]  # the admin takes it away again
        db.commit()
    upgrade(engine)
    with Session(engine) as db:
        assert db.get(User, first_id).permissions == ["conversations.view"]
    engine.dispose()


def test_owner_test_error_reaches_the_list(client, owner, two):
    _, admin_a, _, _ = two
    quiet = TestClient(app, raise_server_exceptions=False)
    assert quiet.post("/api/system/health/test-error", headers=admin_a).status_code == 403
    assert quiet.post("/api/system/health/test-error", headers=owner).status_code == 500
    listed = client.get("/api/system/errors", headers=owner).json()
    assert [(e["error_type"], e["path"], e["status"]) for e in listed] == \
        [("DiagnosticTestError", "/api/system/health/test-error", 500)]
