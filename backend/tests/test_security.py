"""Security behaviour: headers, hidden internals, tokens, encryption at rest, webhook protection."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from tests.conftest import login

BACKEND = Path(__file__).resolve().parents[1]


def test_security_headers_and_no_caching_of_api(client, company_a):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_health_reveals_nothing_internal(client):
    body = client.get("/api/health").json()
    assert set(body) == {"status", "demo"}


def test_forged_and_expired_tokens_are_rejected(client, company_a):
    _, admin = company_a
    me = client.get("/api/auth/me", headers=admin).json()
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"sub": str(me["id"]), "iat": int(now.timestamp()), "exp": now + timedelta(hours=1)},
                        "not-the-server-secret-but-long-enough-0000", algorithm="HS256")
    expired = jwt.encode({"sub": str(me["id"]), "iat": int(now.timestamp()) - 7200,
                          "exp": now - timedelta(hours=1)}, get_settings().secret_key, algorithm="HS256")
    unsigned = jwt.encode({"sub": str(me["id"]), "iat": int(now.timestamp()), "exp": now + timedelta(hours=1)},
                          None, algorithm="none")
    for token in (forged, expired, unsigned, "garbage"):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_login_does_not_reveal_which_emails_exist(client, company_a):
    unknown = client.post("/api/auth/login", json={"email": "nobody@x.com", "password": "Password123"})
    wrong = client.post("/api/auth/login", json={"email": "admin@bluesky.com", "password": "Password123"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_whatsapp_secrets_are_encrypted_in_the_database(client, company_a):
    _, admin = company_a
    client.patch("/api/company", headers=admin, json={
        "whatsapp_access_token": "EAAG-very-secret", "whatsapp_app_secret": "app-secret-123"})
    with engine.connect() as conn:
        token, secret = conn.execute(text("SELECT whatsapp_access_token, whatsapp_app_secret FROM companies")).one()
    assert token.startswith("enc:v1:") and "EAAG" not in token
    assert secret.startswith("enc:v1:") and "app-secret" not in secret
    body = client.get("/api/company", headers=admin).text
    assert "EAAG" not in body and "app-secret" not in body
    assert client.get("/api/company", headers=admin).json()["whatsapp_app_secret_set"] is True


def test_webhook_details_only_for_settings_managers(client, company_a):
    _, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "S", "password": "Password123", "role": "support"})
    support = login(client, "s@bluesky.com", "Password123")
    seen_by_support = client.get("/api/company", headers=support).json()
    assert seen_by_support["whatsapp_verify_token"] is None and seen_by_support["whatsapp_webhook_path"] is None
    seen_by_admin = client.get("/api/company", headers=admin).json()
    assert seen_by_admin["whatsapp_verify_token"] and seen_by_admin["whatsapp_webhook_path"].startswith("/api/")


def test_production_rejects_unsigned_whatsapp_webhooks(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "")
    assert client.post("/api/webhooks/whatsapp", json={"entry": []}).status_code == 503


def test_company_webhook_requires_its_own_verify_token(client, company_a):
    _, admin = company_a
    settings = client.get("/api/company", headers=admin).json()
    path = settings["whatsapp_webhook_path"]
    ok = client.get(path, params={"hub.mode": "subscribe", "hub.verify_token": settings["whatsapp_verify_token"],
                                  "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    for token in ("wrong", get_settings().whatsapp_verify_token, "ـــ"):
        r = client.get(path, params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "1"})
        assert r.status_code == 403
    assert client.get("/api/webhooks/whatsapp/c/unknown-key").status_code == 404


def test_company_webhook_checks_the_company_app_secret(client, company_a):
    _, admin = company_a
    client.patch("/api/company", headers=admin, json={"whatsapp_app_secret": "company-secret"})
    path = client.get("/api/company", headers=admin).json()["whatsapp_webhook_path"]
    r = client.post(path, content=b'{"entry": []}', headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 403
    r = client.post(path, content=b'{"entry": []}', headers={"X-Hub-Signature-256": "sha256=\u00e9".encode("latin-1")})
    assert r.status_code == 403


def test_demo_logins_are_never_listed_in_production(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "seed_demo_data", True)
    assert len(client.get("/api/auth/demo-accounts").json()) >= 3
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert client.get("/api/auth/demo-accounts").json() == []


def _run_production_app(code: str, **env) -> subprocess.CompletedProcess:
    full_env = {
        **os.environ,
        "ENVIRONMENT": "production",
        "DATABASE_URL": f"sqlite:///{BACKEND}/.prod-check.db",
        "SECRET_KEY": "x" * 40,
        "SYSTEM_ADMIN_PASSWORD": "A-real-password-123",
        "SEED_DEMO_DATA": "false",
        "LLM_PROVIDER": "mock",
        "BCRYPT_ROUNDS": "4",
        **env,
    }
    try:
        return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=full_env, capture_output=True,
                              text=True, timeout=60)
    finally:
        (BACKEND / ".prod-check.db").unlink(missing_ok=True)


def test_production_hides_api_docs_and_sets_hsts():
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "with TestClient(app) as c:\n"
        "    print(c.get('/docs').status_code, c.get('/openapi.json').status_code,\n"
        "          c.get('/api/health').headers.get('Strict-Transport-Security'))\n"
    )
    result = _run_production_app(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[-3:] == ["404", "404", "max-age=31536000"]


def test_production_refuses_default_admin_password():
    code = "from fastapi.testclient import TestClient\nfrom app.main import app\nTestClient(app).__enter__()\n"
    result = _run_production_app(code, SYSTEM_ADMIN_PASSWORD="ChangeMe123!")
    assert result.returncode != 0
    assert "SYSTEM_ADMIN_PASSWORD" in result.stderr


def test_production_replaces_public_demo_passwords():
    code = (
        "from fastapi.testclient import TestClient\n"
        "from sqlalchemy import select\n"
        "from app.main import app\n"
        "from app.database import SessionLocal\n"
        "from app.models import User\n"
        "from app.security import hash_password, verify_password\n"
        "from app.seed import protect_demo_accounts\n"
        "with TestClient(app) as c:\n"
        "    db = SessionLocal()\n"
        "    u = db.scalar(select(User).where(User.email == 'admin@sunrise-travel.example'))\n"
        "    print('seeded-random', not verify_password('Admin123!', u.password_hash))\n"
        "    u.password_hash = hash_password('Admin123!'); db.commit()\n"
        "    protect_demo_accounts(db)\n"
        "    db.refresh(u)\n"
        "    print('rotated', not verify_password('Admin123!', u.password_hash))\n"
        "    print(c.post('/api/auth/login', json={'email': u.email, 'password': 'Admin123!'}).status_code)\n"
    )
    result = _run_production_app(code, SEED_DEMO_DATA="true")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()[-3:]
    assert lines == ["seeded-random True", "rotated True", "401"]
