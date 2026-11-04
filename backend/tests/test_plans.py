"""Subscription plans: catalogue, company subscriptions, payments, limits, grace period, MRR."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.ai.llm import LLMResponse
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.migrations import upgrade
from app.models import Company, Plan, Subscription
from app.services import plans as plans_service
from app.services import whatsapp as whatsapp_service
from app.services.conversations import process_whatsapp_payload
from app.services.whatsapp import set_whatsapp_sender
from app.timeutil import local_today
from tests.conftest import FakeWhatsApp, login, make_company, make_package
from tests.test_whatsapp import wa_payload

PUBLIC = "/api/public/companies/{slug}"


def plans_by_name(client, owner) -> dict:
    r = client.get("/api/system/plans", headers=owner)
    assert r.status_code == 200, r.text
    return {p["name"]: p for p in r.json()}


def set_plan(client, owner, company_id, name, **extra):
    plan_id = plans_by_name(client, owner)[name]["id"]
    r = client.patch(f"/api/system/companies/{company_id}/subscription", headers=owner, json={"plan_id": plan_id, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def edit_plan(client, owner, name, **changes):
    plan = plans_by_name(client, owner)[name]
    body = {k: v for k, v in plan.items() if k not in ("id", "is_archived", "companies")} | changes
    r = client.put(f"/api/system/plans/{plan['id']}", headers=owner, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def add_user(client, admin, email):
    return client.post("/api/users", headers=admin, json={
        "email": email, "full_name": "Staff Member", "password": "Password123", "role": "support"})


def start_chat(client, slug):
    r = client.post(f"{PUBLIC.format(slug=slug)}/chats", json={"name": "Salim"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def say(client, slug, token, text="Hi"):
    return client.post(f"{PUBLIC.format(slug=slug)}/chats/{token}/messages", json={"content": text})


def time_travel(monkeypatch, days: int):
    day = local_today() + timedelta(days=days)
    monkeypatch.setattr(plans_service, "today", lambda: day)
    return day


@pytest.fixture
def wa_stub(monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_allow_unsigned", True)
    monkeypatch.setattr(whatsapp_service, "verify_phone_number", lambda number_id, token: True)
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    return wa


# --- Catalogue -----------------------------------------------------------------------------------


def test_default_plans_are_seeded_and_editable(client, owner):
    plans = plans_by_name(client, owner)
    assert {"Starter", "Business", "Pro"} <= set(plans)
    assert [p["name"] for p in plans.values() if p["is_default"]] == ["Pro"]
    assert plans["Starter"]["price_monthly"] == 15.0 and plans["Starter"]["allow_instagram"] is False
    assert plans["Pro"]["max_packages"] is None  # unlimited

    body = {"name": "Umrah Season", "name_ar": "موسم العمرة", "price_monthly": 12.345, "price_yearly": 120.5,
            "trial_days": 7, "max_users": 4, "max_packages": 10, "max_ai_conversations": None,
            "allow_whatsapp": True, "allow_instagram": True, "allow_page_editor": False,
            "allow_remove_powered_by": False, "priority_support": True,
            "features": ["  Umrah packages ", ""], "features_ar": ["باقات العمرة"], "description": "Seasonal"}
    r = client.post("/api/system/plans", headers=owner, json=body)
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["price_monthly"] == 12.345 and plan["features"] == ["Umrah packages"]
    assert plan["max_ai_conversations"] is None and plan["is_default"] is False

    assert client.post("/api/system/plans", headers=owner, json={**body, "price_monthly": 1.2345}).status_code == 422

    r = client.put(f"/api/system/plans/{plan['id']}", headers=owner, json={**body, "price_monthly": 9, "is_default": True})
    assert r.json()["price_monthly"] == 9 and r.json()["is_default"] is True
    assert [p["name"] for p in plans_by_name(client, owner).values() if p["is_default"]] == ["Umrah Season"]

    # The default plan can't be archived; another one can, and it can't be chosen any more.
    assert client.post(f"/api/system/plans/{plan['id']}/archive", headers=owner, json={"archived": True}).status_code == 400
    starter = plans_by_name(client, owner)["Starter"]
    r = client.post(f"/api/system/plans/{starter['id']}/archive", headers=owner, json={"archived": True})
    assert r.json()["is_archived"] is True
    company, _ = make_company(client, owner)
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner, json={"plan_id": starter["id"]})
    assert r.status_code == 400 and "archived" in r.json()["detail"]


def test_plan_endpoints_are_for_the_owner_only(client, owner, company_a):
    company, admin = company_a
    for method, path in [("get", "/api/system/plans"), ("get", "/api/system/billing"),
                         ("get", "/api/system/subscriptions"),
                         ("get", f"/api/system/companies/{company['id']}/subscription"),
                         ("get", f"/api/system/companies/{company['id']}/payments")]:
        assert getattr(client, method)(path, headers=admin).status_code == 403
        assert getattr(client, method)(path).status_code == 401
    assert client.post("/api/system/plans", headers=admin, json={}).status_code == 403
    assert client.post(f"/api/system/companies/{company['id']}/subscription/extend", headers=admin,
                       json={"months": 1}).status_code == 403
    assert client.post(f"/api/system/companies/{company['id']}/payments", headers=admin, json={
        "amount": 1, "paid_on": "2026-01-01", "method": "cash"}).status_code == 403
    # The owner has no company plan page.
    assert client.get("/api/company/plan", headers=owner).status_code == 403


# --- New companies ----------------------------------------------------------------------------------


def test_new_company_starts_a_trial_and_follows_the_plan_limit(client, owner):
    company, admin = make_company(client, owner, max_users=None)
    sub = client.get(f"/api/system/companies/{company['id']}/subscription", headers=owner).json()
    assert sub["plan"]["name"] == "Pro" and sub["status"] == "trial" and sub["state"] == "trial"
    assert sub["trial_end"] == (local_today() + timedelta(days=14)).isoformat()
    assert sub["max_users"] == 25 and sub["max_users_custom"] is False

    starter = plans_by_name(client, owner)["Starter"]
    other, _ = make_company(client, owner, name="Small Co", admin_email="s@small.com", max_users=None,
                            plan_id=starter["id"], billing_cycle="yearly")
    sub = client.get(f"/api/system/companies/{other['id']}/subscription", headers=owner).json()
    assert sub["plan"]["name"] == "Starter" and sub["billing_cycle"] == "yearly" and sub["max_users"] == 3

    # A limit given on creation is the company's own limit.
    custom, _ = make_company(client, owner, name="Custom Co", admin_email="c@custom.com", max_users=7)
    sub = client.get(f"/api/system/companies/{custom['id']}/subscription", headers=owner).json()
    assert sub["max_users"] == 7 and sub["max_users_custom"] is True


# --- Limits -----------------------------------------------------------------------------------------


def test_staff_limit_follows_the_plan_unless_custom(client, owner):
    company, admin = make_company(client, owner, max_users=None)
    set_plan(client, owner, company["id"], "Starter")  # 3 accounts
    assert add_user(client, admin, "s1@bluesky.com").status_code == 201
    assert add_user(client, admin, "s2@bluesky.com").status_code == 201
    r = add_user(client, admin, "s3@bluesky.com")
    assert r.status_code == 409 and r.json()["detail"].startswith("Account limit reached (3/3)")

    # The owner raises the plan's limit: the company follows it.
    edit_plan(client, owner, "Starter", max_users=4)
    assert add_user(client, admin, "s3@bluesky.com").status_code == 201
    assert client.get("/api/users", headers=admin).json()["max_users"] == 4

    # A plan below the active accounts is refused...
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner,
                     json={"plan_id": edit_plan(client, owner, "Business", max_users=2)["id"]})
    assert r.status_code == 400 and "4 active accounts" in r.json()["detail"]
    # ...unless the company has its own limit, which plan changes leave alone.
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner, json={"account_limit": 6})
    assert r.json()["max_users"] == 6 and r.json()["max_users_custom"] is True
    edit_plan(client, owner, "Starter", max_users=3)
    assert client.get("/api/users", headers=admin).json()["max_users"] == 6
    # Back to the plan's limit (not below the active accounts).
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner, json={"account_limit": None})
    assert r.status_code == 400
    edit_plan(client, owner, "Starter", max_users=5)
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner, json={"account_limit": None})
    assert r.json()["max_users"] == 5 and r.json()["max_users_custom"] is False


def test_package_limit(client, owner, company_a):
    company, admin = company_a
    edit_plan(client, owner, "Starter", max_packages=2)
    set_plan(client, owner, company["id"], "Starter")
    first = make_package(client, admin, title="One")
    make_package(client, admin, title="Two")
    body = {"title": "Three", "destination": "Dubai", "country": "UAE", "duration_days": 3, "price_per_person": 100}
    r = client.post("/api/packages", headers=admin, json=body)
    assert r.status_code == 409
    assert r.json()["detail"] == ("Package limit reached (2/2) on the Starter plan. Hide a package or contact the "
                                  "platform to upgrade.")
    # A hidden package does not count, and can't be shown again while the limit is reached.
    r = client.put(f"/api/packages/{first['id']}", headers=admin, json={**body, "title": "One", "is_active": False})
    assert r.status_code == 200
    assert client.post("/api/packages", headers=admin, json=body).status_code == 201
    r = client.put(f"/api/packages/{first['id']}", headers=admin, json={**body, "title": "One", "is_active": True})
    assert r.status_code == 409
    usage = client.get(f"/api/system/companies/{company['id']}/subscription", headers=owner).json()["usage"]
    assert usage["packages"] == 2 and usage["max_packages"] == 2


def test_channels_need_a_plan_that_includes_them(client, owner, company_a, wa_stub, scripted):
    company, admin = company_a
    set_plan(client, owner, company["id"], "Starter")  # WhatsApp yes, Instagram no
    r = client.patch("/api/company", headers=admin, json={"instagram_access_token": "IGQ-token"})
    assert r.status_code == 403
    assert r.json()["detail"] == "The Starter plan does not include Instagram. Upgrade the plan to connect it."
    r = client.patch(f"/api/system/companies/{company['id']}/instagram", headers=owner,
                     json={"instagram_account_id": "1784"})
    assert r.status_code == 403

    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-P",
                                                          "whatsapp_access_token": "EAAG"})
    assert r.status_code == 200
    edit_plan(client, owner, "Starter", allow_whatsapp=False)
    r = client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-Q"})
    assert r.status_code == 403 and "does not include WhatsApp" in r.json()["detail"]
    r = client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"whatsapp_phone_number_id": "777"})
    assert r.status_code == 403
    # Saving other settings still works for the number that is already connected.
    assert client.patch("/api/company", headers=admin, json={"ai_agent_name": "Mona"}).status_code == 200

    # Messages to the connected number are ignored while the plan has no WhatsApp.
    llm = scripted([LLMResponse("Hello!")])
    process_whatsapp_payload(wa_payload("PNID-P", "96890000001", "Hi", "wamid.plan1"))
    assert wa_stub.sent == [] and llm.calls == []
    assert client.get("/api/conversations", headers=admin).json() == []
    edit_plan(client, owner, "Starter", allow_whatsapp=True)
    process_whatsapp_payload(wa_payload("PNID-P", "96890000001", "Hi", "wamid.plan2"))
    assert wa_stub.sent and wa_stub.sent[0][2] == "Hello!"


def test_page_editor_and_powered_by_follow_the_plan(client, owner, company_a):
    company, admin = company_a
    slug = company["slug"]
    # Pro: the company may hide "Powered by Ghanjah" itself.
    r = client.patch("/api/company/branding", headers=admin, json={"elements": {"powered_by": False}})
    assert r.status_code == 200
    assert client.get(PUBLIC.format(slug=slug)).json()["branding"]["elements"]["powered_by"] is False
    # Business: it shows again and the company can't hide it.
    set_plan(client, owner, company["id"], "Business")
    assert client.get(PUBLIC.format(slug=slug)).json()["branding"]["elements"]["powered_by"] is True
    client.patch("/api/company/branding", headers=admin, json={"elements": {"powered_by": False}})
    assert client.get(PUBLIC.format(slug=slug)).json()["branding"]["elements"]["powered_by"] is True
    # Starter: no page editor for the company (the owner can still edit the page).
    set_plan(client, owner, company["id"], "Starter")
    r = client.patch("/api/company/branding", headers=admin, json={"primary_color": "#112233"})
    assert r.status_code == 403
    assert r.json()["detail"] == "The Starter plan does not include the page editor. Contact the platform to upgrade."
    assert client.patch(f"/api/system/companies/{company['id']}/branding", headers=owner,
                        json={"primary_color": "#112233"}).status_code == 200
    notice = client.get("/api/company/plan/notice", headers=admin).json()
    assert notice["page_editor"] is False and notice["instagram"] is False and notice["plan_name"] == "Starter"


def test_ai_monthly_conversation_limit(client, owner, company_a, scripted, monkeypatch):
    company, admin = company_a
    slug = company["slug"]
    edit_plan(client, owner, "Pro", max_ai_conversations=1)
    llm = scripted([LLMResponse("Welcome to Oman!"), LLMResponse("Sure, Salalah is lovely.")])

    first = start_chat(client, slug)
    assert say(client, slug, first).json()["messages"][-1]["content"] == "Welcome to Oman!"
    # The chat that already started keeps its AI.
    assert say(client, slug, first, "Salalah?").json()["messages"][-1]["content"] == "Sure, Salalah is lovely."

    second = start_chat(client, slug)
    r = say(client, slug, second)
    assert r.json()["status"] == "human"
    assert r.json()["messages"][-1]["content"] == plans_service.TEAM_WILL_REPLY
    assert len(llm.calls) == 2
    convs = client.get("/api/conversations?status=human", headers=admin).json()
    assert convs[0]["handover_reason"] == "AI monthly conversation limit reached, please answer the customer"
    detail = client.get(f"/api/conversations/{convs[0]['id']}", headers=admin).json()
    assert any(m["content"] == "Handed over to the team: the plan's limit of 1 AI conversations this month was "
               "reached" for m in detail["messages"])
    usage = client.get(f"/api/system/companies/{company['id']}/subscription", headers=owner).json()["usage"]
    assert usage["ai_conversations"] == 1 and usage["max_ai_conversations"] == 1

    # Next month the count starts again.
    client.post(f"/api/system/companies/{company['id']}/subscription/extend", headers=owner, json={"months": 12})
    next_month = (local_today().replace(day=1) + timedelta(days=32)).replace(day=1)
    monkeypatch.setattr(plans_service, "today", lambda: next_month)
    scripted([LLMResponse("New month, new trips!")])
    third = start_chat(client, slug)
    assert say(client, slug, third).json()["messages"][-1]["content"] == "New month, new trips!"


def test_hourly_ai_limit_still_applies(client, company_a, scripted, monkeypatch):
    company, _ = company_a
    monkeypatch.setattr(get_settings(), "ai_max_replies_per_company_per_hour", 1)
    scripted([LLMResponse("One"), LLMResponse("Two")])
    token = start_chat(client, company["slug"])
    assert say(client, company["slug"], token).json()["messages"][-1]["content"] == "One"
    r = say(client, company["slug"], token, "again")
    assert r.json()["status"] == "human"


# --- Grace period and expiry ---------------------------------------------------------------------


def test_grace_period_then_pause(client, owner, company_a, scripted, monkeypatch, wa_stub):
    company, admin = company_a
    slug = company["slug"]
    end = local_today() + timedelta(days=5)
    r = client.patch(f"/api/system/companies/{company['id']}/subscription", headers=owner,
                     json={"status": "active", "current_period_end": end.isoformat()})
    assert r.json()["state"] == "active" and r.json()["grace_until"] == (end + timedelta(days=7)).isoformat()
    client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-G", "whatsapp_access_token": "x"})

    # In the grace period everything keeps working, staff see a "payment due" banner.
    time_travel(monkeypatch, 8)
    assert client.get(PUBLIC.format(slug=slug)).status_code == 200
    scripted([LLMResponse("Still here!")])
    token = start_chat(client, slug)
    assert say(client, slug, token).json()["messages"][-1]["content"] == "Still here!"
    notice = client.get("/api/company/plan/notice", headers=admin).json()
    assert notice["state"] == "grace" and notice["banner"] == "past_due"

    # After the grace period: the customer page and the AI pause, staff keep their dashboard.
    time_travel(monkeypatch, 13)
    r = client.get(PUBLIC.format(slug=slug))
    assert r.status_code == 423 and r.json()["detail"] == "This travel agency's page is paused"
    assert say(client, slug, token).status_code == 423
    assert client.get("/api/company/plan/notice", headers=admin).json()["banner"] == "expired"
    assert client.get("/api/packages", headers=admin).status_code == 200
    llm = scripted([LLMResponse("must not answer")])
    process_whatsapp_payload(wa_payload("PNID-G", "96890000002", "Hello?", "wamid.g1"))
    assert llm.calls == []
    assert wa_stub.sent[-1][2] == plans_service.TEAM_WILL_REPLY  # the customer is not left without an answer
    waiting = client.get("/api/conversations?status=human", headers=admin).json()
    assert waiting[0]["handover_reason"] == "AI paused: the subscription has expired, please answer the customer"

    # A longer grace period (platform setting) opens it again; so does a payment.
    r = client.put("/api/system/billing/settings", headers=owner, json={"grace_days": 10})
    assert r.json()["grace_days"] == 10
    assert client.get(PUBLIC.format(slug=slug)).status_code == 200
    client.put("/api/system/billing/settings", headers=owner, json={"grace_days": 7})
    assert client.get(PUBLIC.format(slug=slug)).status_code == 423
    client.post(f"/api/system/companies/{company['id']}/subscription/extend", headers=owner, json={"months": 1})
    assert client.get(PUBLIC.format(slug=slug)).status_code == 200


def test_trial_and_cancellation(client, owner, company_a, monkeypatch):
    company, admin = company_a
    base = f"/api/system/companies/{company['id']}/subscription"
    r = client.post(f"{base}/trial", headers=owner, json={"days": 5})
    assert r.json()["status"] == "trial" and r.json()["days_left"] == 5
    assert client.get("/api/company/plan/notice", headers=admin).json()["banner"] == "trial_ending"
    time_travel(monkeypatch, 13)  # 5 days + 7 days grace are over
    assert client.get(PUBLIC.format(slug=company["slug"])).status_code == 423

    monkeypatch.setattr(plans_service, "today", local_today)
    client.post(f"{base}/extend", headers=owner, json={"months": 1})
    r = client.post(f"{base}/cancel", headers=owner)
    assert r.json()["status"] == "cancelled" and r.json()["state"] == "cancelled"
    end = date.fromisoformat(r.json()["current_period_end"])
    # Cancelled: works to the end of the period, then pauses without a grace period.
    monkeypatch.setattr(plans_service, "today", lambda: end)
    assert client.get(PUBLIC.format(slug=company["slug"])).status_code == 200
    monkeypatch.setattr(plans_service, "today", lambda: end + timedelta(days=1))
    assert client.get(PUBLIC.format(slug=company["slug"])).status_code == 423


def test_extend_buttons(client, owner, company_a):
    company, _ = company_a
    base = f"/api/system/companies/{company['id']}/subscription"
    today = local_today()
    # From a trial: the paid month starts today.
    r = client.post(f"{base}/extend", headers=owner, json={"months": 1}).json()
    assert r["status"] == "active" and r["trial_end"] is None
    assert r["current_period_start"] == today.isoformat()
    month_end = date.fromisoformat(r["current_period_end"])
    assert month_end == plans_service.add_months(today, 1) - timedelta(days=1)
    # +1 year continues after the paid period.
    r = client.post(f"{base}/extend", headers=owner, json={"months": 12}).json()
    assert date.fromisoformat(r["current_period_end"]) == plans_service.add_months(month_end + timedelta(days=1), 12) \
        - timedelta(days=1)
    assert client.post(f"{base}/extend", headers=owner, json={"months": 3}).status_code == 422
    assert plans_service.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


# --- Payments --------------------------------------------------------------------------------------


def test_payment_extends_the_period_and_shows_on_my_plan(client, owner, company_a):
    company, admin = company_a
    other, admin_b = make_company(client, owner, name="Other Travel", admin_email="b@other.com")
    base = f"/api/system/companies/{company['id']}"
    sub = client.get(f"{base}/subscription", headers=owner).json()
    period = sub["next_period"]
    assert period["start"] == local_today().isoformat()  # a trial: the paid period starts today

    r = client.post(f"{base}/payments", headers=owner, json={
        "amount": 75, "paid_on": local_today().isoformat(), "method": "bank_transfer", "reference": "TRX-991",
        "period_start": period["start"], "period_end": period["end"]})
    assert r.status_code == 201, r.text
    payment = r.json()
    assert payment["invoice_number"] == f"INV-{local_today().year}-{payment['id']:05d}"
    assert payment["plan_name"] == "Pro" and payment["created_by"] == "owner@example.com"
    sub = client.get(f"{base}/subscription", headers=owner).json()
    assert sub["status"] == "active" and sub["current_period_end"] == period["end"]
    assert sub["payments_total"] == 75

    # A payment without "extend" leaves the period alone.
    later = (date.fromisoformat(period["end"]) + timedelta(days=60)).isoformat()
    client.post(f"{base}/payments", headers=owner, json={
        "amount": 10.5, "paid_on": local_today().isoformat(), "method": "cash", "period_start": period["end"],
        "period_end": later, "extend": False})
    assert client.get(f"{base}/subscription", headers=owner).json()["current_period_end"] == period["end"]
    listing = client.get(f"{base}/payments", headers=owner).json()
    assert listing["total"] == 85.5 and len(listing["payments"]) == 2
    bad = client.post(f"{base}/payments", headers=owner, json={
        "amount": 1, "paid_on": "2026-01-01", "method": "cash", "period_start": "2026-02-01", "period_end": "2026-01-01"})
    assert bad.status_code == 422

    # The company admin sees its own plan and payments (read-only), never another company's.
    mine = client.get("/api/company/plan", headers=admin).json()
    assert mine["plan"]["name"] == "Pro" and mine["payments_total"] == 85.5 and len(mine["payments"]) == 2
    assert "notes" not in mine
    assert client.get("/api/company/plan", headers=admin_b).json()["payments"] == []
    invoice = client.get(f"/api/company/plan/payments/{payment['id']}/invoice", headers=admin)
    assert invoice.status_code == 200 and invoice.json()["company"]["name"] == company["name"]
    assert client.get(f"/api/company/plan/payments/{payment['id']}/invoice", headers=admin_b).status_code == 404
    assert client.get(f"/api/system/payments/{payment['id']}/invoice", headers=owner).json()["payment"]["amount"] == 75
    assert client.get(f"/api/system/payments/{payment['id']}/invoice", headers=admin).status_code == 403

    # Other employees don't see the plan page, but get the banner information.
    client.post("/api/users", headers=admin, json={"email": "sup@bluesky.com", "full_name": "Sup", "password":
                                                   "Password123", "role": "support"})
    support = login(client, "sup@bluesky.com", "Password123")
    assert client.get("/api/company/plan", headers=support).status_code == 403
    assert client.get("/api/company/plan/notice", headers=support).status_code == 200

    assert client.delete(f"/api/system/payments/{payment['id']}", headers=owner).status_code == 204
    assert client.get(f"{base}/payments", headers=owner).json()["total"] == 10.5


def test_mrr_and_status_counts(client, owner):
    def company(name, plan, **sub):
        c, _ = make_company(client, owner, name=name, admin_email=f"admin@{name.lower()}.com")
        if "current_period_end" in sub:
            sub["current_period_start"] = (today - timedelta(days=60)).isoformat()
        set_plan(client, owner, c["id"], plan, **sub)
        return c

    today = local_today()
    year = (today + timedelta(days=300)).isoformat()
    company("Alpha", "Pro", status="active", current_period_end=year)                            # 75
    company("Beta", "Business", status="active", billing_cycle="yearly", current_period_end=year)  # 350 / 12
    company("Gamma", "Starter", status="active", custom_price=20, current_period_end=year)       # 20
    company("Delta", "Pro")                                                                       # trial: no MRR
    company("Eps", "Pro", status="active", current_period_end=(today - timedelta(days=3)).isoformat())  # grace: 75
    company("Zeta", "Pro", status="active", current_period_end=(today - timedelta(days=30)).isoformat())  # expired
    company("Eta", "Pro", status="cancelled", current_period_end=(today + timedelta(days=10)).isoformat())  # no MRR

    overview = client.get("/api/system/billing", headers=owner).json()
    assert overview["mrr"] == round(75 + 350 / 12 + 20 + 75, 3)
    assert overview["counts"] == {"trial": 1, "active": 3, "past_due": 1, "expired": 1, "cancelled": 1}
    assert overview["expiring_soon"] == 2  # Delta's trial (14 days) and Eta's cancellation (10 days)
    subs = {s["company_id"]: s for s in client.get("/api/system/subscriptions", headers=owner).json()}
    assert len(subs) == 7 and {s["state"] for s in subs.values()} == {"trial", "active", "grace", "expired", "cancelled"}


# --- Upgrade of an existing database ---------------------------------------------------------------


def test_existing_companies_are_not_locked_out_by_the_upgrade(client, owner, wa_stub, scripted):
    """Companies made before plans existed: their subscription is created at the next start."""
    company, admin = make_company(client, owner, max_users=8)
    make_package(client, admin)
    client.patch("/api/company", headers=admin, json={"whatsapp_phone_number_id": "PNID-OLD", "whatsapp_access_token": "x"})
    client.patch("/api/company/branding", headers=admin, json={"elements": {"powered_by": False}})
    with SessionLocal() as db:
        db.execute(delete(Subscription))
        db.commit()

    upgrade(engine)
    upgrade(engine)  # twice: changes nothing

    sub = client.get(f"/api/system/companies/{company['id']}/subscription", headers=owner).json()
    assert sub["status"] == "active" and sub["state"] == "active"
    assert sub["current_period_end"] == plans_service.add_months(local_today(), 12).isoformat()
    assert sub["max_users"] == 8  # the limit the owner had set
    assert sub["plan"]["allow_whatsapp"] and sub["plan"]["allow_remove_powered_by"]  # what it already uses
    assert client.get(PUBLIC.format(slug=company["slug"])).json()["branding"]["elements"]["powered_by"] is False
    scripted([LLMResponse("Hello again")])
    process_whatsapp_payload(wa_payload("PNID-OLD", "96890000003", "Hi", "wamid.old1"))
    assert wa_stub.sent[-1][2] == "Hello again"
    assert client.get("/api/company/plan/notice", headers=admin).json()["banner"] is None


def test_upgrade_of_an_old_database_file(tmp_path):
    """A database file from before plans: tables are created, plans seeded, every company gets an
    active subscription on a plan that allows what it uses (or the Legacy plan)."""
    old = create_engine(f"sqlite:///{tmp_path}/old.db")
    Base.metadata.create_all(old)
    with old.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_conversations_company_ai_started"))
        conn.execute(text("ALTER TABLE conversations DROP COLUMN ai_started_at"))
        for table in ("subscription_payments", "subscriptions", "plans"):
            conn.execute(text(f"DROP TABLE {table}"))
    with Session(old) as db:
        db.add_all([
            Company(name="Small", slug="small", max_users=3),
            Company(name="Insta", slug="insta", max_users=10, instagram_account_id="IG-1",
                    branding={"elements": {"powered_by": False}}),
            Company(name="Huge", slug="huge", max_users=60),
        ])
        db.commit()
    # What init_db does at start: create the missing tables, then upgrade.
    Base.metadata.create_all(old)
    upgrade(old)
    upgrade(old)
    with Session(old) as db:
        assert db.scalar(select(Plan).where(Plan.is_default.is_(True))).name == "Pro"
        rows = {c.slug: (s, s.plan, c) for s, c in db.execute(
            select(Subscription, Company).join(Company, Company.id == Subscription.company_id)).all()}
        assert set(rows) == {"small", "insta", "huge"}
        assert rows["small"][1].name == "Starter" and rows["small"][2].max_users == 3
        assert rows["insta"][1].name == "Pro"  # Instagram and no "Powered by"
        assert rows["huge"][1].name == "Legacy" and rows["huge"][1].is_archived
        assert rows["huge"][2].max_users == 60
        for sub, _, _ in rows.values():
            assert sub.status == "active" and sub.current_period_end > local_today() + timedelta(days=360)
    old.dispose()
