"""System admin, company admins, roles, permissions, account limits and tenant isolation."""

from tests.conftest import login, make_company, make_package


def test_system_admin_creates_company_with_admin(client, owner):
    company, admin = make_company(client, owner, name="Blue Sky Travel")
    assert company["slug"] == "blue-sky-travel"
    assert company["user_count"] == 1
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["role"] == "company_admin"
    assert me["company"]["slug"] == "blue-sky-travel"
    assert "users.manage" in me["permissions"]


def test_company_admin_cannot_use_system_area(client, company_a):
    _, admin = company_a
    assert client.get("/api/system/companies", headers=admin).status_code == 403


def test_system_admin_cannot_use_company_area(client, owner):
    assert client.get("/api/packages", headers=owner).status_code == 403


def test_account_limit_set_by_system_admin(client, owner):
    company, admin = make_company(client, owner, max_users=2)
    new_user = {"email": "s1@bluesky.com", "full_name": "S One", "password": "Password123", "role": "support"}
    assert client.post("/api/users", headers=admin, json=new_user).status_code == 201

    r = client.post("/api/users", headers=admin, json={**new_user, "email": "s2@bluesky.com"})
    assert r.status_code == 409
    assert "limit" in r.json()["detail"].lower()

    r = client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_users": 3})
    assert r.json()["max_users"] == 3
    assert client.post("/api/users", headers=admin, json={**new_user, "email": "s2@bluesky.com"}).status_code == 201

    listing = client.get("/api/users", headers=admin).json()
    assert listing["used"] == 3 and listing["max_users"] == 3


def test_roles_and_custom_permissions(client, company_a):
    _, admin = company_a
    r = client.post("/api/users", headers=admin, json={
        "email": "support@bluesky.com", "full_name": "Sam", "password": "Password123", "role": "support"})
    support_id = r.json()["id"]
    assert "packages.manage" not in r.json()["permissions"]
    support = login(client, "support@bluesky.com", "Password123")

    assert client.get("/api/packages", headers=support).status_code == 200
    assert client.get("/api/users", headers=support).status_code == 403
    pkg = {"title": "Dubai", "destination": "Dubai", "country": "UAE", "duration_days": 4, "price_per_person": 900}
    assert client.post("/api/packages", headers=support, json=pkg).status_code == 403

    # The company admin grants an extra permission to this one employee.
    perms = r.json()["permissions"] + ["packages.manage", "not.a.permission"]
    r = client.patch(f"/api/users/{support_id}", headers=admin, json={"permissions": perms})
    assert "packages.manage" in r.json()["permissions"]
    assert "not.a.permission" not in r.json()["permissions"]
    assert client.post("/api/packages", headers=support, json=pkg).status_code == 201

    # Changing the role resets to that role's defaults.
    r = client.patch(f"/api/users/{support_id}", headers=admin, json={"role": "ticket_agent"})
    assert "tickets.manage" in r.json()["permissions"]
    assert "packages.manage" not in r.json()["permissions"]


def test_disable_and_delete_accounts(client, company_a):
    _, admin = company_a
    r = client.post("/api/users", headers=admin, json={
        "email": "t@bluesky.com", "full_name": "Tia", "password": "Password123", "role": "ticket_agent"})
    uid = r.json()["id"]
    agent = login(client, "t@bluesky.com", "Password123")

    client.patch(f"/api/users/{uid}", headers=admin, json={"is_active": False})
    assert client.get("/api/auth/me", headers=agent).status_code == 401
    r = client.post("/api/auth/login", json={"email": "t@bluesky.com", "password": "Password123"})
    assert r.status_code == 403

    assert client.delete(f"/api/users/{uid}", headers=admin).status_code == 204
    assert client.get("/api/users", headers=admin).json()["used"] == 1


def test_admin_cannot_lock_company_out(client, company_a):
    _, admin = company_a
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.delete(f"/api/users/{me['id']}", headers=admin).status_code == 400
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"role": "support"}).status_code == 400
    assert client.patch(f"/api/users/{me['id']}", headers=admin, json={"is_active": False}).status_code == 400


def test_tenant_isolation(client, owner):
    _, admin_a = make_company(client, owner, name="Company A", admin_email="a@a.com")
    _, admin_b = make_company(client, owner, name="Company B", admin_email="b@b.com")
    pkg_a = make_package(client, admin_a)

    assert client.get(f"/api/packages/{pkg_a['id']}", headers=admin_b).status_code == 404
    assert client.get("/api/packages", headers=admin_b).json() == []
    assert client.put(f"/api/packages/{pkg_a['id']}", headers=admin_b, json={
        "title": "Hacked", "destination": "x", "country": "x", "duration_days": 1, "price_per_person": 1,
    }).status_code == 404

    users_a = client.get("/api/users", headers=admin_a).json()["users"]
    assert client.patch(f"/api/users/{users_a[0]['id']}", headers=admin_b, json={"full_name": "x"}).status_code == 404


def test_suspended_company_is_locked(client, owner):
    company, admin = make_company(client, owner)
    client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"status": "suspended"})
    assert client.get("/api/auth/me", headers=admin).status_code == 403
    r = client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "AdminPass123!"})
    assert r.status_code == 403
    assert client.get(f"/api/public/companies/{company['slug']}").status_code == 404


def test_system_admin_manages_company_users(client, owner):
    company, admin = make_company(client, owner)
    users = client.get(f"/api/system/companies/{company['id']}/users", headers=owner).json()
    admin_id = users["users"][0]["id"]
    r = client.patch(f"/api/system/users/{admin_id}", headers=owner, json={"password": "BrandNew123!"})
    assert r.status_code == 200
    login(client, "admin@bluesky.com", "BrandNew123!")

    r = client.post(f"/api/system/companies/{company['id']}/users", headers=owner, json={
        "email": "second@bluesky.com", "full_name": "Second Admin", "password": "Password123", "role": "company_admin"})
    assert r.status_code == 201


def test_delete_company_removes_everything(client, owner):
    company, admin = make_company(client, owner)
    make_package(client, admin)
    assert client.delete(f"/api/system/companies/{company['id']}", headers=owner).status_code == 204
    assert client.get("/api/system/companies", headers=owner).json() == []
    r = client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "AdminPass123!"})
    assert r.status_code == 401


def test_change_password_logs_out_other_sessions(client, company_a):
    _, admin = company_a
    other_device = login(client, "admin@bluesky.com", "AdminPass123!")
    r = client.post("/api/auth/change-password", headers=admin,
                    json={"current_password": "wrong", "new_password": "Whatever123"})
    assert r.status_code == 400
    r = client.post("/api/auth/change-password", headers=admin,
                    json={"current_password": "AdminPass123!", "new_password": "Whatever123"})
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=admin).status_code == 401
    assert client.get("/api/auth/me", headers=other_device).status_code == 401
    login(client, "admin@bluesky.com", "Whatever123")


def test_password_reset_by_admin_ends_the_employee_sessions(client, company_a):
    _, admin = company_a
    r = client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "S", "password": "Password123", "role": "support"})
    employee = login(client, "s@bluesky.com", "Password123")
    client.patch(f"/api/users/{r.json()['id']}", headers=admin, json={"password": "NewPassword123"})
    assert client.get("/api/auth/me", headers=employee).status_code == 401
    login(client, "s@bluesky.com", "NewPassword123")


def test_login_attempts_are_limited(client, company_a):
    codes = [client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "nope"}).status_code
             for _ in range(12)]
    assert codes[0] == 401
    assert codes[-1] == 429
