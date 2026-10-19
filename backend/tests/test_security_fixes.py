"""Fixes from the security audit: delegates, reused ids, login lockout, client IP, colleagues' chats."""

from starlette.requests import Request

from app.ai.llm import LLMResponse
from sqlalchemy import update

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.netutil import client_ip
from tests.conftest import login, make_company
from tests.test_branding import upload


def add_user(client, headers, email, role="support", permissions=None):
    body = {"email": email, "full_name": email.split("@")[0], "password": "Password123", "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    return client.post("/api/users", headers=headers, json=body)


def me_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def start_chat(client, slug, scripted):
    scripted([LLMResponse("hello")])
    token = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{token}/messages", json={"content": "hi"})


# 1. A delegate can't take over a colleague who has more permissions.
def test_delegate_cannot_manage_more_privileged_colleague(client, company_a):
    _, admin = company_a
    assert add_user(client, admin, "hr@bluesky.com", permissions=["users.manage", "tickets.view"]).status_code == 201
    assert add_user(client, admin, "ops@bluesky.com", role="ticket_agent",
                    permissions=["settings.manage", "tickets.view"]).status_code == 201
    assert add_user(client, admin, "junior@bluesky.com", permissions=["tickets.view"]).status_code == 201
    hr = login(client, "hr@bluesky.com", "Password123")
    ops_id = me_id(client, login(client, "ops@bluesky.com", "Password123"))
    junior_id = me_id(client, login(client, "junior@bluesky.com", "Password123"))

    for r in (client.patch(f"/api/users/{ops_id}", headers=hr, json={"password": "Hijacked123"}),
              client.patch(f"/api/users/{ops_id}", headers=hr, json={"email": "mine@bluesky.com"}),
              client.patch(f"/api/users/{ops_id}", headers=hr, json={"is_active": False}),
              client.delete(f"/api/users/{ops_id}", headers=hr)):
        assert r.status_code == 403
        assert r.json()["detail"] == "Only a company admin can manage an account with permissions you don't have"
    login(client, "ops@bluesky.com", "Password123")  # untouched

    # Colleagues with only permissions the delegate has can still be managed.
    assert client.patch(f"/api/users/{junior_id}", headers=hr, json={"password": "NewPass1234"}).status_code == 200
    assert client.delete(f"/api/users/{junior_id}", headers=hr).status_code == 204
    # The company admin can still manage everyone.
    assert client.patch(f"/api/users/{ops_id}", headers=admin, json={"password": "AdminSet123"}).status_code == 200


# 2. A deleted user's token must not log in as the next account that gets the same id.
def test_deleted_user_token_does_not_work_for_reused_id(client, owner):
    _, admin_a = make_company(client, owner)
    assert add_user(client, admin_a, "leaver@bluesky.com").status_code == 201
    leaver = login(client, "leaver@bluesky.com", "Password123")
    lid = me_id(client, leaver)
    assert client.delete(f"/api/users/{lid}", headers=admin_a).status_code == 204
    _, admin_b = make_company(client, owner, name="Other Co", admin_email="admin@other.com")
    if me_id(client, admin_b) != lid:
        # PostgreSQL never hands an id out twice; give the new admin the old id ourselves.
        with SessionLocal() as db:
            db.execute(update(User).where(User.email == "admin@other.com").values(id=lid))
            db.commit()
        admin_b = login(client, "admin@other.com", "AdminPass123!")
    assert client.get("/api/auth/me", headers=leaver).status_code == 401
    assert client.get("/api/auth/me", headers=admin_b).status_code == 200


# 3. Wrong guesses can't lock the real owner out.
def test_failed_logins_do_not_lock_out_the_right_password(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)  # so each attempt can come from another IP

    def attempt(password, ip):
        return client.post("/api/auth/login", json={"email": "owner@example.com", "password": password},
                           headers={"X-Forwarded-For": ip})

    for i in range(30):
        assert attempt("wrong", f"10.0.0.{i}").status_code == 401
    # The account is locked for wrong passwords, but the right one still works.
    r = attempt("wrong", "10.0.1.1")
    assert r.status_code == 429
    assert r.json()["detail"] == "Too many login attempts for this account, try again later"
    assert attempt("OwnerPass123!", "10.0.1.2").status_code == 200


def test_successful_logins_are_not_counted(client, company_a):
    for _ in range(12):  # more than the 10 per ip+email
        login(client, "admin@bluesky.com", "AdminPass123!")


# 4. The client IP comes from X-Forwarded-For only as far as TRUSTED_PROXY_HOPS allows.
def _request(xff=None, peer="10.0.0.1"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_client_ip_uses_trusted_proxy_hops(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    assert client_ip(_request("1.2.3.4")) == "10.0.0.1"
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    # The client wrote 1.2.3.4 itself; our one proxy appended the real address.
    assert client_ip(_request("1.2.3.4, 198.51.100.7")) == "198.51.100.7"
    assert client_ip(_request("198.51.100.7")) == "198.51.100.7"
    assert client_ip(_request()) == "10.0.0.1"
    monkeypatch.setattr(settings, "trusted_proxy_hops", 2)
    assert client_ip(_request("1.2.3.4, 198.51.100.7, 10.1.1.1")) == "198.51.100.7"


def test_forged_forwarded_for_does_not_bypass_login_limit(client, company_a):
    for i in range(10):
        client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "wrong"},
                    headers={"X-Forwarded-For": f"10.0.0.{i}"})
    r = client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "wrong"},
                    headers={"X-Forwarded-For": "10.0.0.99"})
    assert r.status_code == 429


def test_dockerfiles_do_not_trust_every_proxy():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for dockerfile in (root / "Dockerfile", root / "backend" / "Dockerfile"):
        cmd = [line for line in dockerfile.read_text().splitlines() if line.startswith("CMD")][0]
        assert "forwarded-allow-ips" not in cmd and "--proxy-headers" not in cmd
    assert "TRUSTED_PROXY_HOPS" in (root / "render.yaml").read_text()


# 5. Handing back, closing or answering a colleague's chat needs force (or a takeover).
def test_colleagues_conversation_needs_force(client, company_a, scripted):
    company, admin = company_a
    assert add_user(client, admin, "s1@bluesky.com").status_code == 201
    assert add_user(client, admin, "s2@bluesky.com").status_code == 201
    s1 = login(client, "s1@bluesky.com", "Password123")
    s2 = login(client, "s2@bluesky.com", "Password123")
    start_chat(client, company["slug"], scripted)
    cid = client.get("/api/conversations", headers=admin).json()[0]["id"]
    assert client.post(f"/api/conversations/{cid}/takeover", headers=s1).status_code == 200

    for path in ("release", "close"):
        r = client.post(f"/api/conversations/{cid}/{path}", headers=s2)
        assert r.status_code == 409
        assert r.json()["detail"] == "s1 is already handling this conversation"
    r = client.post(f"/api/conversations/{cid}/messages", headers=s2, json={"content": "x"})
    assert r.status_code == 409
    conv = client.get(f"/api/conversations/{cid}", headers=admin).json()
    assert conv["status"] == "human" and conv["assigned_to"]["full_name"] == "s1"

    # The one handling it can still answer; others can force after confirming.
    assert client.post(f"/api/conversations/{cid}/messages", headers=s1, json={"content": "hi"}).status_code == 201
    assert client.post(f"/api/conversations/{cid}/release?force=true", headers=s2).json()["status"] == "ai"
    assert client.post(f"/api/conversations/{cid}/takeover", headers=s1).status_code == 200
    assert client.post(f"/api/conversations/{cid}/close?force=true", headers=admin).json()["status"] == "closed"


# 6. Your own password is changed on the account page, which asks for the current one.
def test_patch_self_cannot_change_own_password(client, company_a):
    _, admin = company_a
    my = me_id(client, admin)
    r = client.patch(f"/api/users/{my}", headers=admin, json={"password": "NewPass1234"})
    assert r.status_code == 400
    login(client, "admin@bluesky.com", "AdminPass123!")
    # Other changes to yourself still work.
    assert client.patch(f"/api/users/{my}", headers=admin, json={"full_name": "Boss"}).status_code == 200


# 7. % and _ are searched literally.
def test_conversation_search_escapes_wildcards(client, company_a, scripted):
    company, admin = company_a
    start_chat(client, company["slug"], scripted)
    assert len(client.get("/api/conversations", headers=admin).json()) == 1
    assert client.get("/api/conversations?q=_", headers=admin).json() == []
    assert client.get("/api/conversations?q=%25", headers=admin).json() == []


# 8 + 9. Suspending a company hides its images and logs its staff out for good.
def test_suspended_company_media_hidden_and_sessions_revoked(client, owner):
    company, admin = make_company(client, owner)
    url = upload(client, admin).json()["url"]
    assert client.get(url).status_code == 200
    assert client.patch(f"/api/system/companies/{company['id']}", headers=owner,
                        json={"status": "suspended"}).status_code == 200
    assert client.get(url).status_code == 404
    assert client.get("/api/auth/me", headers=admin).status_code == 403  # says why while suspended
    assert client.patch(f"/api/system/companies/{company['id']}", headers=owner,
                        json={"status": "active"}).status_code == 200
    assert client.get(url).status_code == 200
    assert client.get("/api/auth/me", headers=admin).status_code == 401
    fresh = login(client, "admin@bluesky.com", "AdminPass123!")
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_platform_owner_assigns_a_shared_whatsapp_number(client, owner):
    from tests.conftest import make_company

    a, _ = make_company(client, owner, name="Alpha", admin_email="a@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta", admin_email="b@beta.com")
    r = client.patch(f"/api/system/companies/{a['id']}", headers=owner, json={"whatsapp_phone_number_id": "1234567"})
    assert r.status_code == 200 and r.json()["whatsapp_phone_number_id"] == "1234567"
    assert r.json()["whatsapp_connected"] is True
    # Never two companies on one number, and a company admin can't use this owner endpoint.
    r = client.patch(f"/api/system/companies/{b['id']}", headers=owner, json={"whatsapp_phone_number_id": "1234567"})
    assert r.status_code == 409
    assert client.patch(f"/api/system/companies/{b['id']}", headers=admin_b,
                        json={"whatsapp_phone_number_id": "999"}).status_code == 403
    assert client.patch(f"/api/system/companies/{a['id']}", headers=owner,
                        json={"whatsapp_phone_number_id": "12ab"}).status_code == 422
    r = client.patch(f"/api/system/companies/{a['id']}", headers=owner, json={"whatsapp_phone_number_id": ""})
    assert r.json()["whatsapp_phone_number_id"] is None
