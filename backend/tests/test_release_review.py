"""Release review: tenant isolation of the new endpoints, export date limits, MRR of ended trials,
error capture (scrubbing, flood protection, never on the event loop, database down) and the
retention of the activity log."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app import audit as audit_module
from app import database, diagnostics
from app.database import SessionLocal
from app.main import app
from app.models import AuditEvent, Customer, ErrorEvent, Subscription, SubscriptionPayment
from app.routers import diagnostics as diagnostics_router
from app.timeutil import local_today
from tests.conftest import login, make_company
from tests.test_plans import time_travel


def _customer(company_id: int, name: str = "Ali Al Balushi") -> int:
    with SessionLocal() as db:
        c = Customer(company_id=company_id, name=name, phone="+96891234567")
        db.add(c)
        db.commit()
        return c.id


def _errors():
    with SessionLocal() as db:
        return db.scalars(select(ErrorEvent).order_by(ErrorEvent.id)).all()


@pytest.fixture
def two(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="admin@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    return a, admin_a, b, admin_b


# --- Tenant isolation and roles ------------------------------------------------------------------


def test_new_endpoints_keep_companies_apart(client, owner, two):
    a, admin_a, b, admin_b = two
    customer_id = _customer(a["id"])
    assert client.get(f"/api/customers/{customer_id}", headers=admin_a).status_code == 200
    assert client.get(f"/api/customers/{customer_id}", headers=admin_b).status_code == 404
    assert client.patch(f"/api/customers/{customer_id}", headers=admin_b, json={"notes": "x"}).status_code == 404
    assert client.get("/api/customers", headers=admin_b).json()["total"] == 0
    assert "Balushi" not in client.get("/api/customers/export.csv", headers=admin_b).text

    r = client.post(f"/api/system/companies/{a['id']}/payments", headers=owner,
                    json={"amount": 15, "paid_on": local_today().isoformat(), "method": "cash"})
    payment_id = r.json()["id"]
    assert client.get(f"/api/company/plan/payments/{payment_id}/invoice", headers=admin_a).status_code == 200
    assert client.get(f"/api/company/plan/payments/{payment_id}/invoice", headers=admin_b).status_code == 404
    for url in (f"/api/system/payments/{payment_id}/invoice", f"/api/system/companies/{a['id']}/payments",
                f"/api/system/companies/{a['id']}/activity", f"/api/system/companies/{a['id']}/subscription",
                "/api/system/plans", "/api/system/billing", "/api/system/errors", "/api/system/health"):
        assert client.get(url, headers=admin_b).status_code == 403, url
    assert client.delete(f"/api/system/payments/{payment_id}", headers=admin_b).status_code == 403
    assert all(i["actor"] != "Alpha Travel Admin" for i in client.get("/api/activity", headers=admin_b).json()["items"])


def test_roles_on_the_new_pages(client, two):
    a, admin_a, _, _ = two
    customer_id = _customer(a["id"])
    for email, role in (("sup@alpha.com", "support"), ("tick@alpha.com", "ticket_agent")):
        r = client.post("/api/users", headers=admin_a, json={"email": email, "full_name": role, "password": "Password123",
                                                            "role": role})
        assert r.status_code == 201, r.text
    support, agent = login(client, "sup@alpha.com", "Password123"), login(client, "tick@alpha.com", "Password123")
    for headers in (support, agent):
        assert client.get("/api/activity", headers=headers).status_code == 403
        assert client.get("/api/company/plan", headers=headers).status_code == 403
        assert client.get("/api/company/plan/notice", headers=headers).status_code == 200
    assert client.get("/api/customers/export.csv", headers=support).status_code == 200
    assert client.get("/api/customers/export.csv", headers=agent).status_code == 403
    assert client.patch(f"/api/customers/{customer_id}", headers=agent, json={"notes": "x"}).status_code == 403
    assert client.get("/api/exports/tickets.csv", headers=agent).status_code == 403  # no reports.view


def test_a_delegate_cannot_hand_out_customers_manage(client, two):
    _, admin_a, _, _ = two
    perms = ["packages.view", "conversations.view", "tickets.view", "users.manage"]
    r = client.post("/api/users", headers=admin_a, json={"email": "del@alpha.com", "full_name": "Delegate",
                                                        "password": "Password123", "role": "support", "permissions": perms})
    delegate_id = r.json()["id"]
    delegate = login(client, "del@alpha.com", "Password123")
    r = client.patch(f"/api/users/{delegate_id}", headers=delegate, json={"permissions": [*perms, "customers.manage"]})
    assert r.status_code == 400
    new = {"email": "new@alpha.com", "full_name": "New", "password": "Password123", "role": "support"}
    assert client.post("/api/users", headers=delegate,
                       json={**new, "permissions": ["conversations.view", "customers.manage"]}).status_code == 403
    assert client.post("/api/users", headers=delegate, json=new).status_code == 403  # the role's defaults include it


# --- Exports and money ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["date_from=0001-01-01", "date_to=9999-12-31", "date_from=1999-12-31"])
def test_export_dates_out_of_range_are_refused(client, company_a, query):
    _, admin = company_a
    for what in ("tickets", "payments"):
        r = client.get(f"/api/exports/{what}.csv?{query}", headers=admin)
        assert r.status_code == 400, (what, r.status_code)
        assert r.json()["detail"] == "Choose dates between 2000 and 2100"
    assert client.get("/api/exports/tickets.csv?date_from=2000-01-01&date_to=2100-12-31", headers=admin).status_code == 200


def test_an_ended_trial_in_its_grace_period_is_not_revenue(client, owner, monkeypatch):
    make_company(client, owner, name="Trial Travel", admin_email="admin@trial.com")  # Pro, 14 day trial
    time_travel(monkeypatch, 16)  # trial over, inside the 7 day grace period
    overview = client.get("/api/system/billing", headers=owner).json()
    assert overview["mrr"] == 0 and overview["counts"]["past_due"] == 1


def test_deleting_a_company_removes_its_plan_data(client, owner, two):
    a, _, b, _ = two
    client.post(f"/api/system/companies/{a['id']}/payments", headers=owner,
                json={"amount": 15, "paid_on": local_today().isoformat(), "method": "cash"})
    assert client.delete(f"/api/system/companies/{a['id']}", headers=owner).status_code == 204
    with SessionLocal() as db:
        for model in (Subscription, SubscriptionPayment, AuditEvent):
            assert not db.scalar(select(func.count()).select_from(model).where(model.company_id == a["id"])), model
        assert db.scalar(select(func.count()).select_from(Subscription).where(Subscription.company_id == b["id"])) == 1


# --- Error capture -------------------------------------------------------------------------------


def test_scrub_hides_omani_phone_numbers_and_passwords_in_addresses():
    s = diagnostics.scrub("call 91234567 or +968 9123 4567; db postgresql://app:S3cr3t-pw@dpg-abc/app on 2026-11-04")
    assert "91234567" not in s and "9123 4567" not in s
    assert "S3cr3t" not in s and "postgresql://app:[hidden]@dpg-abc/app" in s
    assert "2026-11-04" in s


def test_browser_reports_never_push_server_errors_out(client, monkeypatch):
    monkeypatch.setattr(diagnostics, "MAX_ROWS", 3)
    diagnostics.record_error("server", method="GET", path="/api/real", status=500, message="real problem")
    for i in range(6):
        diagnostics.record_error("client", method="PAGE", path=f"/flood{i}", page=f"/flood{i}", error_type="error",
                                 message=f"noise {i}")
    rows = _errors()
    assert [r.path for r in rows if r.source == "server"] == ["/api/real"]
    assert [r.path for r in rows if r.source == "client"] == ["/flood3", "/flood4", "/flood5"]


def test_browser_reports_have_a_limit_for_everyone_together(client, monkeypatch):
    monkeypatch.setattr(diagnostics_router, "CLIENT_ERRORS_PER_MINUTE", 2)
    codes = [client.post("/api/client-errors", json={"kind": "error", "message": f"m{i}"}).status_code
             for i in range(3)]
    assert codes == [204, 204, 429]


@pytest.fixture
def boom_route():
    async def boom(request: Request):
        raise RuntimeError("boom")

    app.add_api_route("/api/test-release-boom", boom, methods=["GET"])
    route = app.router.routes[-1]
    yield
    app.router.routes.remove(route)


def test_errors_are_written_off_the_event_loop(client, monkeypatch, boom_route):
    """A slow database must not stall every other request while an error is being recorded."""
    on_loop = []

    def spy(*args):
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)

    monkeypatch.setattr(diagnostics, "_record", spy)
    assert client.post("/api/client-errors", json={"kind": "error", "message": "x"}).status_code == 204
    quiet = TestClient(app, raise_server_exceptions=False)
    assert quiet.get("/api/test-release-boom").status_code == 500
    assert on_loop == [False, False]


def test_error_capture_survives_a_database_outage(client, monkeypatch, boom_route):
    def broken():
        raise OperationalError("SELECT 1", {}, Exception("could not connect to server"))

    monkeypatch.setattr(database, "SessionLocal", broken)
    assert client.post("/api/client-errors", json={"kind": "error", "message": "x"}).status_code == 204
    quiet = TestClient(app, raise_server_exceptions=False)
    assert quiet.get("/api/test-release-boom").status_code == 500


# --- Activity log retention ----------------------------------------------------------------------


def test_activity_log_keeps_a_year_and_a_row_cap(client, two, monkeypatch):
    a, _, b, _ = two
    old = datetime.now(timezone.utc) - timedelta(days=400)
    with SessionLocal() as db:
        for company in (a, b):
            db.add(AuditEvent(company_id=company["id"], actor="Old", action="package.created", created_at=old))
        for i in range(5):
            db.add(AuditEvent(company_id=a["id"], actor="Someone", action="package.updated", target=f"P{i}"))
        db.commit()
    monkeypatch.setattr(audit_module, "MAX_ROWS_PER_COMPANY", 3)
    login(client, "admin@alpha.com", "AdminPass123!")
    with SessionLocal() as db:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.company_id == a["id"]).order_by(AuditEvent.id)).all()
        others = db.scalars(select(AuditEvent).where(AuditEvent.company_id == b["id"])).all()
    assert [(r.action, r.target) for r in rows] == [("package.updated", "P3"), ("package.updated", "P4"),
                                                    ("auth.login", None)]
    assert any(r.actor == "Old" for r in others)  # another company's log is left alone
