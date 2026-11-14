"""Business accounts: clients and vendors of a travel company, their logins, limits and features."""

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.database import SessionLocal
from app.models import Customer
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, login, make_company
from tests.test_whatsapp import HOOK, connect_whatsapp, meta_stub, wa_payload  # noqa: F401 (fixture)

ALL = ["client.requests", "client.whatsapp", "client.ai_chat", "client.history", "client.exclusive_packages",
       "client.reports", "vendor.requests", "vendor.quotes", "vendor.history"]


def switch_on(client, owner, company_id, **extra):
    body = {"enabled": True, "max_clients": 3, "max_vendors": 2, "max_users_per_partner": 2, "features": ALL, **extra}
    r = client.put(f"/api/system/companies/{company_id}/b2b", headers=owner, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def add_partner(client, admin, **extra):
    body = {"kind": "client", "name": "Oman Oil Co", "features": ["client.requests", "client.whatsapp"], **extra}
    return client.post("/api/partners", headers=admin, json=body)


def add_login(client, admin, partner_id, email="hr@oil.example", name="HR Manager"):
    r = client.post(f"/api/partners/{partner_id}/logins", headers=admin, json={"email": email, "full_name": name})
    assert r.status_code == 201, r.text
    body = r.json()
    return body, login(client, email, body["password"])


@pytest.fixture
def b2b(client, owner):
    company, admin = make_company(client, owner)
    switch_on(client, owner, company["id"])
    return company, admin


# --- Owner controls -----------------------------------------------------------------------------------

def test_off_until_the_owner_switches_it_on(client, owner, company_a):
    company, admin = company_a
    assert client.get("/api/partners", headers=admin).status_code == 403
    assert add_partner(client, admin).status_code == 403
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["company"]["b2b_enabled"] is False and me["partner"] is None
    settings = client.get("/api/partners/settings", headers=admin).json()["settings"]
    assert settings["enabled"] is False and settings["max_clients"] == 0
    switch_on(client, owner, company["id"])
    assert client.get("/api/auth/me", headers=admin).json()["company"]["b2b_enabled"] is True
    assert client.get("/api/partners", headers=admin).status_code == 200


def test_only_the_owner_changes_limits_and_features(client, owner, b2b):
    company, admin = b2b
    url = f"/api/system/companies/{company['id']}/b2b"
    assert client.put(url, headers=admin, json={"enabled": True, "max_clients": 999}).status_code == 403
    assert client.get(url, headers=admin).status_code == 403
    assert client.put(url, headers=owner, json={"enabled": True, "features": ["client.teleport"]}).status_code == 422
    assert client.put(url, headers=owner, json={"enabled": True, "max_clients": -1}).status_code == 422
    assert client.put(url, headers=owner, json={"enabled": True, "hack": 1}).status_code == 422
    assert client.put("/api/system/companies/9999/b2b", headers=owner, json={"enabled": True}).status_code == 404


def test_account_limits_per_kind(client, owner, b2b):
    company, admin = b2b
    for i in range(3):
        assert add_partner(client, admin, name=f"Client {i}", features=[]).status_code == 201
    r = add_partner(client, admin, name="One too many", features=[])
    assert r.status_code == 409 and "3/3" in r.json()["detail"]
    for i in range(2):
        assert add_partner(client, admin, kind="vendor", name=f"Vendor {i}", features=["vendor.quotes"]).status_code == 201
    assert add_partner(client, admin, kind="vendor", name="Vendor 3", features=[]).status_code == 409
    usage = client.get("/api/partners", headers=admin).json()["usage"]
    assert usage == {"clients": 3, "vendors": 2}
    switch_on(client, owner, company["id"], max_clients=4)
    assert add_partner(client, admin, name="Now fits", features=[]).status_code == 201


def test_features_must_be_allowed_and_of_the_right_kind(client, owner, b2b):
    company, admin = b2b
    assert add_partner(client, admin, features=["vendor.quotes"]).status_code == 422
    assert add_partner(client, admin, features=["client.nope"]).status_code == 422
    switch_on(client, owner, company["id"], features=["client.requests"])
    assert add_partner(client, admin, features=["client.reports"]).status_code == 403
    r = add_partner(client, admin, features=["client.requests"])
    assert r.status_code == 201 and r.json()["active_features"] == ["client.requests"]


def test_owner_taking_a_feature_back_stops_it_at_once(client, owner, b2b):
    company, admin = b2b
    partner = add_partner(client, admin, features=["client.requests", "client.reports"]).json()
    _, portal = add_login(client, admin, partner["id"])
    assert client.get("/api/partner/home", headers=portal).json()["features"] == ["client.requests", "client.reports"]
    switch_on(client, owner, company["id"], features=["client.requests"])
    assert client.get("/api/partner/home", headers=portal).json()["features"] == ["client.requests"]
    listed = client.get("/api/partners", headers=admin).json()["partners"][0]
    assert listed["features"] == ["client.requests", "client.reports"]  # the company's choice is kept
    assert listed["active_features"] == ["client.requests"]
    # Saving again keeps a feature taken back, but a new one must be allowed.
    r = client.patch(f"/api/partners/{partner['id']}", headers=admin,
                     json={"features": ["client.requests", "client.reports"]})
    assert r.status_code == 200
    r = client.patch(f"/api/partners/{partner['id']}", headers=admin, json={"features": ["client.history"]})
    assert r.status_code == 403
    # Switching business accounts off closes the portal.
    switch_on(client, owner, company["id"], enabled=False)
    assert client.get("/api/partner/home", headers=portal).status_code == 403


# --- Isolation ----------------------------------------------------------------------------------------

def test_companies_never_see_each_others_accounts(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="a@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    switch_on(client, owner, a["id"])
    switch_on(client, owner, b["id"])
    pa = add_partner(client, admin_a).json()
    login_a, _ = add_login(client, admin_a, pa["id"])
    assert client.get("/api/partners", headers=admin_b).json()["partners"] == []
    pid, uid = pa["id"], login_a["login"]["id"]
    assert client.patch(f"/api/partners/{pid}", headers=admin_b, json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/partners/{pid}", headers=admin_b).status_code == 404
    assert client.post(f"/api/partners/{pid}/logins", headers=admin_b,
                       json={"email": "x@x.example", "full_name": "X"}).status_code == 404
    assert client.patch(f"/api/partners/{pid}/logins/{uid}", headers=admin_b, json={"new_password": True}).status_code == 404
    # Company B's account can't take over a login of company A through its own account either.
    pb = add_partner(client, admin_b).json()
    assert client.patch(f"/api/partners/{pb['id']}/logins/{uid}", headers=admin_b,
                        json={"new_password": True}).status_code == 404
    # The same WhatsApp number may be a client of both companies.
    assert client.patch(f"/api/partners/{pa['id']}", headers=admin_a, json={"whatsapp_numbers": ["+968 9123 4567"]}).status_code == 200
    assert client.patch(f"/api/partners/{pb['id']}", headers=admin_b, json={"whatsapp_numbers": ["96891234567"]}).status_code == 200


def test_business_logins_never_reach_staff_areas(client, owner, b2b):
    company, admin = b2b
    partner = add_partner(client, admin).json()
    _, portal = add_login(client, admin, partner["id"])
    staff_areas = ["/api/conversations", "/api/customers", "/api/customers/export.csv", "/api/tickets",
                   "/api/exports/tickets.csv", "/api/packages", "/api/users", "/api/team", "/api/company",
                   "/api/company/whatsapp", "/api/company/branding", "/api/company/plan", "/api/dashboard",
                   "/api/dashboard/analytics", "/api/training", "/api/training/knowledge", "/api/activity",
                   "/api/partners", "/api/partners/settings"]
    for url in staff_areas:
        assert client.get(url, headers=admin).status_code == 200, url  # a real staff area …
        assert client.get(url, headers=portal).status_code == 403, url  # … closed to business logins
    assert client.get("/api/system/companies", headers=portal).status_code == 403
    r = client.post("/api/media", headers=portal, json={"content_type": "image/png", "data_base64": "iVBORw0KGgo="})
    assert r.status_code == 403
    me = client.get("/api/auth/me", headers=portal).json()
    assert me["role"] == "partner" and me["permissions"] == []
    assert me["partner"] == {"id": partner["id"], "name": "Oman Oil Co", "kind": "client"}
    home = client.get("/api/partner/home", headers=portal).json()
    assert home["partner_name"] == "Oman Oil Co" and home["company_name"] == company["name"]
    # Staff can't use the portal.
    assert client.get("/api/partner/home", headers=admin).status_code == 403
    assert client.get("/api/partner/home", headers=owner).status_code == 403


def test_business_logins_are_not_staff_seats(client, owner):
    company, admin = make_company(client, owner, max_users=1)
    switch_on(client, owner, company["id"])
    partner = add_partner(client, admin).json()
    login_info, _ = add_login(client, admin, partner["id"])
    users = client.get("/api/users", headers=admin).json()
    assert [u["role"] for u in users["users"]] == ["company_admin"] and users["used"] == 1
    assert [u["role"] for u in client.get("/api/team", headers=admin).json()] == ["company_admin"]
    uid = login_info["login"]["id"]
    # The staff and owner team pages can't edit or promote a business login.
    assert client.patch(f"/api/users/{uid}", headers=admin, json={"role": "company_admin"}).status_code == 404
    assert client.delete(f"/api/users/{uid}", headers=admin).status_code == 404
    assert client.patch(f"/api/system/users/{uid}", headers=owner, json={"role": "company_admin"}).status_code == 404
    owner_list = client.get(f"/api/system/companies/{company['id']}/users", headers=owner).json()
    assert [u["id"] for u in owner_list["users"]] != [] and uid not in [u["id"] for u in owner_list["users"]]


def test_support_staff_need_the_permission(client, owner, b2b):
    _, admin = b2b
    r = client.post("/api/users", headers=admin, json={"email": "s@bluesky.com", "full_name": "Support",
                                                      "password": "Support123!", "role": "support"})
    assert r.status_code == 201
    support = login(client, "s@bluesky.com", "Support123!")
    assert client.get("/api/partners", headers=support).status_code == 403
    assert add_partner(client, support).status_code == 403
    client.patch(f"/api/users/{r.json()['id']}", headers=admin, json={"permissions": ["partners.manage"]})
    assert client.get("/api/partners", headers=support).status_code == 200


# --- Logins -------------------------------------------------------------------------------------------

def test_logins_limit_password_reset_and_pause(client, owner, b2b):
    _, admin = b2b
    partner = add_partner(client, admin).json()
    first, portal = add_login(client, admin, partner["id"])
    assert len(first["password"]) >= 16
    add_login(client, admin, partner["id"], email="travel@oil.example")
    r = client.post(f"/api/partners/{partner['id']}/logins", headers=admin, json={"email": "c@oil.example", "full_name": "C"})
    assert r.status_code == 409
    # Same email as a staff account of this company is refused.
    r = client.post(f"/api/partners/{partner['id']}/logins", headers=admin, json={"email": "admin@bluesky.com", "full_name": "X"})
    assert r.status_code == 409
    uid = first["login"]["id"]
    r = client.patch(f"/api/partners/{partner['id']}/logins/{uid}", headers=admin, json={"new_password": True})
    new_password = r.json()["password"]
    assert new_password and new_password != first["password"]
    assert client.get("/api/partner/home", headers=portal).status_code == 401  # old session ended
    portal = login(client, "hr@oil.example", new_password)
    # Pausing the whole account ends its sessions and blocks new logins.
    client.patch(f"/api/partners/{partner['id']}", headers=admin, json={"is_active": False})
    assert client.get("/api/partner/home", headers=portal).status_code in (401, 403)
    r = client.post("/api/auth/login", json={"email": "hr@oil.example", "password": new_password})
    assert r.status_code == 403 and "paused" in r.json()["detail"]
    client.patch(f"/api/partners/{partner['id']}", headers=admin, json={"is_active": True})
    assert client.get("/api/partner/home", headers=login(client, "hr@oil.example", new_password)).status_code == 200
    # Deleting the account deletes its logins.
    assert client.delete(f"/api/partners/{partner['id']}", headers=admin).status_code == 204
    assert client.post("/api/auth/login", json={"email": "hr@oil.example", "password": new_password}).status_code == 401


# --- WhatsApp numbers ---------------------------------------------------------------------------------

def test_whatsapp_numbers_are_checked_and_unique(client, b2b):
    _, admin = b2b
    r = add_partner(client, admin, whatsapp_numbers=["+968 9123 4567", "0096891234567", "٩٦٨٩٢٢٢٣٣٣٤"])
    assert r.status_code == 201 and r.json()["whatsapp_numbers"] == ["96891234567", "96892223334"]
    r = add_partner(client, admin, name="Other Co", whatsapp_numbers=["+96891234567"])
    assert r.status_code == 409 and "Oman Oil Co" in r.json()["detail"]
    assert add_partner(client, admin, name="Bad", whatsapp_numbers=["hello"]).status_code == 422
    vendor = add_partner(client, admin, kind="vendor", name="Vendor", features=[]).json()
    r = client.patch(f"/api/partners/{vendor['id']}", headers=admin, json={"whatsapp_numbers": ["+96899999999"]})
    assert r.status_code == 422


def test_whatsapp_messages_from_a_linked_number_are_known(client, b2b, scripted):
    company, admin = b2b
    connect_whatsapp(client, admin)
    set_whatsapp_sender(FakeWhatsApp())
    scripted([LLMResponse("Hello!"), LLMResponse("Hello again!"), LLMResponse("Hi")])
    # A customer wrote before the number was linked …
    client.post(HOOK, json=wa_payload("PNID-A", "96891234567", "Hi", "wamid.1"))
    partner = add_partner(client, admin, whatsapp_numbers=["+968 9123 4567"]).json()

    def partner_of(wa_id):
        with SessionLocal() as db:
            return db.scalar(select(Customer.partner_id).where(Customer.whatsapp_id == wa_id))

    assert partner_of("96891234567") == partner["id"]  # … and is linked when the number is added
    client.post(HOOK, json=wa_payload("PNID-A", "96855555555", "Hi", "wamid.2"))
    assert partner_of("96855555555") is None
    client.patch(f"/api/partners/{partner['id']}", headers=admin, json={"whatsapp_numbers": ["+96855555555"]})
    assert partner_of("96891234567") is None and partner_of("96855555555") == partner["id"]
    client.post(HOOK, json=wa_payload("PNID-A", "96855555555", "Again", "wamid.3"))
    assert partner_of("96855555555") == partner["id"]
    client.delete(f"/api/partners/{partner['id']}", headers=admin)
    assert partner_of("96855555555") is None
