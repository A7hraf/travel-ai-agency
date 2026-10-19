"""Platform settings page (AI brain + shared WhatsApp app) and the My account endpoints."""

import httpx
import pytest
from sqlalchemy import text

from app import platform_settings as ps
from app.ai import llm as llm_module
from app.ai.llm import OpenAICompatibleClient, get_llm_client
from app.config import get_settings
from app.database import engine

from .conftest import login, make_company

URL = "/api/system/platform-settings"
SECRET_VALUES = ["gsk_secret_key_123", "app-secret-456", "EAAB-token-789"]


@pytest.fixture(autouse=True)
def fresh_cache():
    ps.invalidate()
    yield
    ps.invalidate()


def _all_secrets(owner_client, owner):
    owner_client.put(URL, headers=owner, json={
        "ai": {"llm_api_key": SECRET_VALUES[0]},
        "whatsapp": {"whatsapp_app_secret": SECRET_VALUES[1], "whatsapp_default_access_token": SECRET_VALUES[2]},
    })


def test_only_system_admin_can_read_and_write(client, owner, company_a):
    _, admin = company_a
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=admin).status_code == 403
    assert client.put(URL, headers=admin, json={"ai": {"llm_model": "x"}}).status_code == 403
    assert client.post(f"{URL}/ai-check", headers=admin).status_code == 403
    assert client.post(f"{URL}/whatsapp/verify-token", headers=admin).status_code == 403
    r = client.get(URL, headers=owner)
    assert r.status_code == 200
    body = r.json()
    assert body["webhook_path"] == "/api/webhooks/whatsapp"
    assert body["info"]["database"] in ("SQLite", "PostgreSQL")
    assert "sqlite:" not in r.text and "postgres" not in r.text.lower().replace("postgresql\"", "")
    assert body["info"]["companies"] == 1


def test_secrets_are_never_returned(client, owner):
    _all_secrets(client, owner)
    r = client.get(URL, headers=owner)
    for value in SECRET_VALUES:
        assert value not in r.text
    ai, wa = r.json()["ai"], r.json()["whatsapp"]
    assert ai["llm_api_key"]["saved"] is True and ai["llm_api_key"]["value"] is None
    assert wa["whatsapp_app_secret"]["saved"] is True and wa["whatsapp_app_secret"]["effective"] is None
    assert wa["whatsapp_default_access_token"]["source"] == "database"
    # The PUT answer does not contain them either.
    r = client.put(URL, headers=owner, json={"ai": {"llm_api_key": "another-key-000"}})
    assert "another-key-000" not in r.text
    # Encrypted in the database.
    with engine.connect() as conn:
        stored = [row[0] for row in conn.execute(text("SELECT secret_value FROM platform_settings"))]
    assert stored and all(v.startswith("enc:v1:") for v in stored)
    assert not any(secret in " ".join(stored) for secret in SECRET_VALUES)


def test_db_value_overrides_env_and_is_used_by_the_llm_client(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")
    monkeypatch.setattr(get_settings(), "llm_base_url", "http://env-server/v1")
    monkeypatch.setattr(get_settings(), "llm_model", "env-model")
    env_client = get_llm_client()
    assert isinstance(env_client, OpenAICompatibleClient) and env_client.base_url == "http://env-server/v1"

    r = client.put(URL, headers=owner, json={"ai": {
        "llm_base_url": "https://api.groq.com/openai/v1/", "llm_model": "db-model",
        "llm_fallback_models": " backup-1 ,, backup-2 ", "llm_api_key": "db-key",
    }})
    assert r.status_code == 200, r.text
    ai = r.json()["ai"]
    assert ai["llm_model"]["value"] == "db-model" and ai["llm_model"]["env_value"] == "env-model"
    assert ai["llm_model"]["updated_by"] == "owner@example.com" and ai["llm_model"]["updated_at"]
    assert ai["llm_fallback_models"]["value"] == "backup-1, backup-2"

    c = get_llm_client()
    assert c.base_url == "https://api.groq.com/openai/v1"
    assert c.models == ["db-model", "backup-1", "backup-2"]
    assert c.api_key == "db-key"

    # The health check ("Test AI") uses them too.
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, model=json["model"], auth=headers.get("Authorization"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    r = client.post("/api/system/ai-check", headers=owner).json()
    assert r["ok"] is True and r["model"] == "db-model" and r["server"] == "api.groq.com"
    assert seen == {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "db-model",
                    "auth": "Bearer db-key"}

    # Unsaved values from the form can be tested before saving; blank ones use the saved values.
    r = client.post(f"{URL}/ai-check", headers=owner,
                    json={"llm_base_url": "http://other-server/v1", "llm_model": "", "llm_api_key": ""}).json()
    assert r["ok"] is True and r["server"] == "other-server" and r["model"] == "db-model"
    assert seen["auth"] == "Bearer db-key"
    assert get_llm_client().base_url == "https://api.groq.com/openai/v1"  # nothing saved by the test


def test_clearing_a_value_falls_back_to_env(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")
    monkeypatch.setattr(get_settings(), "llm_model", "env-model")
    client.put(URL, headers=owner, json={"ai": {"llm_model": "db-model", "llm_api_key": "db-key"}})
    assert get_llm_client().model == "db-model"
    r = client.put(URL, headers=owner, json={"ai": {"llm_model": "", "llm_api_key": None}})
    ai = r.json()["ai"]
    assert ai["llm_model"]["source"] == "environment" and ai["llm_model"]["effective"] == "env-model"
    assert ai["llm_api_key"]["saved"] is False
    assert get_llm_client().model == "env-model"
    assert get_llm_client().api_key == get_settings().llm_api_key.strip()
    # Fields not sent are left alone.
    client.put(URL, headers=owner, json={"ai": {"llm_model": "db-model"}})
    client.put(URL, headers=owner, json={"ai": {"llm_base_url": "http://x.example/v1"}})
    assert get_llm_client().model == "db-model"


def test_demo_mode_can_be_switched_from_the_page(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")
    client.put(URL, headers=owner, json={"ai": {"llm_provider": "mock"}})
    assert isinstance(get_llm_client(), llm_module.MockTravelLLM)
    r = client.post("/api/system/ai-check", headers=owner).json()
    assert r["ok"] is False and r["provider"] == "mock"


def test_whatsapp_values_and_verify_token(client, owner, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_verify_token", "env-verify-token")
    monkeypatch.setattr(s, "whatsapp_default_access_token", "env-token")
    monkeypatch.setattr(s, "whatsapp_share_default_token", True)
    assert ps.effective_verify_token() == "env-verify-token"
    assert ps.effective_shared_access_token() == "env-token"
    r = client.put(URL, headers=owner, json={"whatsapp": {
        "whatsapp_app_secret": "app-secret-1", "whatsapp_default_access_token": "db-token",
        "whatsapp_api_version": "v22.0", "whatsapp_share_default_token": False,
    }})
    assert r.status_code == 200, r.text
    assert ps.effective_whatsapp_app_secret() == "app-secret-1"
    assert ps.effective_default_access_token() == "db-token"
    assert ps.effective_api_version() == "v22.0"
    assert ps.effective_share_default_token() is False
    assert ps.effective_shared_access_token() is None
    wa = r.json()["whatsapp"]
    assert wa["whatsapp_verify_token"]["effective"] == "env-verify-token"  # visible to the owner (to copy)

    token = client.post(f"{URL}/whatsapp/verify-token", headers=owner).json()["whatsapp_verify_token"]
    assert len(token) >= 16 and ps.effective_verify_token() == token
    # Clearing the share toggle falls back to the environment.
    client.put(URL, headers=owner, json={"whatsapp": {"whatsapp_share_default_token": None}})
    assert ps.effective_share_default_token() is True


def test_invalid_values_are_rejected(client, owner):
    for body in (
        {"ai": {"llm_base_url": "ftp://server"}},
        {"ai": {"llm_provider": "openai"}},
        {"ai": {"llm_reasoning_effort": "max"}},
        {"whatsapp": {"whatsapp_api_version": "21"}},
        {"whatsapp": {"whatsapp_verify_token": "short"}},
        {"whatsapp": {"whatsapp_verify_token": "has spaces in it"}},
    ):
        assert client.put(URL, headers=owner, json=body).status_code == 422, body


# --- My account -----------------------------------------------------------------------


def test_profile_name_and_email(client, owner, company_a):
    company, admin = company_a
    r = client.post("/api/users", headers=admin, json={
        "email": "agent@bluesky.com", "full_name": "Agent", "password": "AgentPass123!", "role": "support"})
    assert r.status_code == 201, r.text
    agent = login(client, "agent@bluesky.com", "AgentPass123!")
    perms_before = client.get("/api/auth/me", headers=agent).json()["permissions"]

    # Name: no password needed. Role and permissions cannot be changed here.
    r = client.patch("/api/auth/profile", headers=agent, json={
        "full_name": "  Agent Smith ", "role": "company_admin", "permissions": ["users.manage"]})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["full_name"] == "Agent Smith" and me["role"] == "support" and me["permissions"] == perms_before
    assert client.patch("/api/auth/profile", headers=agent, json={"full_name": "   "}).status_code in (400, 422)

    # Email: the current password is required.
    r = client.patch("/api/auth/profile", headers=agent, json={"email": "new@bluesky.com"})
    assert r.status_code == 400 and "current password" in r.json()["detail"]
    r = client.patch("/api/auth/profile", headers=agent, json={"email": "new@bluesky.com", "current_password": "nope"})
    assert r.status_code == 400
    # Unique within the company.
    r = client.patch("/api/auth/profile", headers=agent,
                     json={"email": "ADMIN@bluesky.com", "current_password": "AgentPass123!"})
    assert r.status_code == 409
    r = client.patch("/api/auth/profile", headers=agent,
                     json={"email": "New@BlueSky.com", "current_password": "AgentPass123!"})
    assert r.status_code == 200 and r.json()["email"] == "new@bluesky.com"
    login(client, "new@bluesky.com", "AgentPass123!")
    # Same email as an account in another company is fine (unique per company only).
    _, other_admin = make_company(client, owner, name="Other Co", admin_email="boss@other.com")
    r = client.patch("/api/auth/profile", headers=other_admin,
                     json={"email": "new@bluesky.com", "current_password": "AdminPass123!"})
    assert r.status_code == 200, r.text


def test_owner_profile_email_unique_on_platform(client, owner, company_a):
    # The owner may use an email that a company account also uses.
    r = client.patch("/api/auth/profile", headers=owner,
                     json={"email": "admin@bluesky.com", "current_password": "OwnerPass123!", "full_name": "Boss"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "system_admin" and r.json()["company"] is None


def test_log_out_other_devices(client, owner):
    other_device = login(client, "owner@example.com", "OwnerPass123!")
    r = client.post("/api/auth/logout-others", headers=owner)
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=other_device).status_code == 401
    assert client.get("/api/auth/me", headers=owner).status_code == 401
    assert client.post("/api/auth/logout-others").status_code == 401
