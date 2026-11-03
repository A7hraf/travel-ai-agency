"""Second security review: platform settings (AI key and server address), My account password
checks, company view of the AI test, production start checks and public rate limits."""

import httpx
import pytest

from app import platform_settings as ps
from app.ai import llm as llm_module
from app.ai.llm import LLMError, OpenAICompatibleClient
from app.config import Settings, get_settings
from app.netutil import is_metadata_url

URL = "/api/system/platform-settings"


@pytest.fixture(autouse=True)
def fresh_cache():
    ps.invalidate()
    yield
    ps.invalidate()


@pytest.fixture
def calls(monkeypatch):
    """Every request the AI client sends (answered with a short reply)."""
    seen: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.append({"url": url, "auth": (headers or {}).get("Authorization")})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")
    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    return seen


# --- The saved API key only goes to its own server -------------------------------------------


def test_test_ai_never_sends_the_saved_key_to_a_typed_server(client, owner, calls):
    r = client.put(URL, headers=owner, json={"ai": {"llm_base_url": "https://api.groq.com/openai/v1",
                                                    "llm_api_key": "gsk_SAVED"}})
    assert r.status_code == 200, r.text
    r = client.post(f"{URL}/ai-check", headers=owner, json={"llm_base_url": "https://attacker.example/v1"})
    assert r.status_code == 400 and "API key" in r.json()["detail"]
    assert not calls
    # Same server (other path or model): the saved key is used.
    r = client.post(f"{URL}/ai-check", headers=owner, json={"llm_base_url": "https://api.groq.com/openai/v2/"})
    assert r.status_code == 200 and calls[-1]["auth"] == "Bearer gsk_SAVED"
    # Another server with a key typed on the form.
    r = client.post(f"{URL}/ai-check", headers=owner,
                    json={"llm_base_url": "https://other.example/v1", "llm_api_key": "typed"})
    assert r.status_code == 200 and calls[-1] == {"url": "https://other.example/v1/chat/completions",
                                                   "auth": "Bearer typed"}


def test_saving_another_server_needs_the_key_again(client, owner, calls, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_base_url", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(s, "llm_api_key", "gsk_FROM_RENDER")
    # The variable's key is not sent to a new server.
    r = client.put(URL, headers=owner, json={"ai": {"llm_base_url": "https://attacker.example/v1"}})
    assert r.status_code == 400
    assert llm_module.get_llm_client().base_url == "https://api.groq.com/openai/v1"
    # Same server, other things: fine.
    assert client.put(URL, headers=owner, json={"ai": {"llm_base_url": "https://api.groq.com/openai/v1",
                                                       "llm_model": "m2"}}).status_code == 200
    # A new server with its own key: fine, and that key is used.
    r = client.put(URL, headers=owner, json={"ai": {"llm_base_url": "https://new.example/v1", "llm_api_key": "k2"}})
    assert r.status_code == 200
    c = llm_module.get_llm_client()
    assert (c.base_url, c.api_key) == ("https://new.example/v1", "k2")
    # Removing the saved key would send the variable's key to the saved server: refused...
    assert client.put(URL, headers=owner, json={"ai": {"llm_api_key": ""}}).status_code == 400
    assert llm_module.get_llm_client().api_key == "k2"
    # ...unless the server goes back to the variable's server too.
    r = client.put(URL, headers=owner, json={"ai": {"llm_api_key": "", "llm_base_url": ""}})
    assert r.status_code == 200
    c = llm_module.get_llm_client()
    assert (c.base_url, c.api_key) == ("https://api.groq.com/openai/v1", "gsk_FROM_RENDER")
    # The saved key does not follow a new address either.
    client.put(URL, headers=owner, json={"ai": {"llm_api_key": "k3"}})
    assert client.put(URL, headers=owner, json={"ai": {"llm_base_url": "http://evil.example"}}).status_code == 400


def test_no_key_no_question(client, owner, calls, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    r = client.put(URL, headers=owner, json={"ai": {"llm_base_url": "http://ollama:11434/v1"}})
    assert r.status_code == 200, r.text


# --- Cloud metadata addresses ---------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data", "http://169.254.169.254.", "http://2852039166/",
    "http://0xa9.0xfe.0xa9.0xfe/", "http://[fd00:ec2::254]/", "http://[::ffff:169.254.169.254]/",
    "http://metadata.google.internal/computeMetadata/v1", "http://100.100.100.200/latest",
])
def test_metadata_addresses_are_refused(client, owner, calls, url):
    assert is_metadata_url(url)
    assert client.put(URL, headers=owner, json={"ai": {"llm_base_url": url, "llm_api_key": "k"}}).status_code == 422
    assert client.post(f"{URL}/ai-check", headers=owner,
                       json={"llm_base_url": url, "llm_api_key": "k"}).status_code == 422
    assert not calls


def test_local_and_private_servers_still_work():
    for url in ("http://localhost:11434/v1", "http://ollama:11434/v1", "http://10.0.0.5:8000/v1",
                "http://192.168.1.20/v1", "https://api.groq.com/openai/v1", "http://[::1]:11434/v1"):
        assert not is_metadata_url(url), url


def test_the_ai_client_refuses_a_metadata_address_from_the_environment(calls):
    client = OpenAICompatibleClient("http://169.254.169.254/latest", "k", "m", 0.3, 5)
    with pytest.raises(LLMError):
        client.chat([{"role": "user", "content": "hi"}], [])
    assert not calls


# --- Companies don't see the platform's AI server ---------------------------------------------


def test_company_ai_check_and_test_chat_hide_the_ai_server(client, owner, company_a, monkeypatch):
    _, admin = company_a
    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")
    client.put(URL, headers=owner, json={"ai": {"llm_base_url": "http://10.0.0.5:11434/v1", "llm_api_key": "k",
                                                "llm_model": "secret-model"}})

    def down(url, **_):
        raise httpx.ConnectError("Connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_module.httpx, "post", down)
    from app.ai.health import check_ai, for_company

    owner_view = check_ai()
    assert owner_view["server"] == "10.0.0.5:11434" and owner_view["model"] == "secret-model"
    company_view = for_company(owner_view)
    assert company_view["ok"] is False and "10.0.0.5" not in str(company_view)
    assert "secret-model" not in str(company_view)
    # "Try your AI": the error no longer contains the server address.
    r = client.post("/api/training/try", headers=admin, json={"message": "hi"}).json()
    assert r["ok"] is False and "10.0.0.5" not in r["error"]


# --- My account: the current password can't be guessed with an open session -------------------


def test_wrong_current_passwords_are_limited(client, company_a):
    _, admin = company_a
    for i in range(10):
        r = client.patch("/api/auth/profile", headers=admin,
                         json={"email": "x@bluesky.com", "current_password": f"guess-{i}"})
        assert r.status_code == 400
    r = client.post("/api/auth/change-password", headers=admin,
                    json={"current_password": "AdminPass123!", "new_password": "NewPass123!x"})
    assert r.status_code == 429  # even the right password waits: the guesser may have found it
    r = client.patch("/api/auth/profile", headers=admin, json={"email": "x@bluesky.com"})
    assert r.status_code == 429
    # The name can still be changed (no password involved).
    assert client.patch("/api/auth/profile", headers=admin, json={"full_name": "Amira"}).status_code == 200


def test_an_empty_password_field_is_not_a_guess(client, company_a):
    _, admin = company_a
    for _ in range(12):
        assert client.patch("/api/auth/profile", headers=admin, json={"email": "x@bluesky.com"}).status_code == 400
    r = client.patch("/api/auth/profile", headers=admin,
                     json={"email": "x@bluesky.com", "current_password": "AdminPass123!"})
    assert r.status_code == 200, r.text


# --- Production start checks ----------------------------------------------------------------


@pytest.fixture
def prod(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "secret_key", "k" * 40)
    monkeypatch.setattr(main.settings, "system_admin_password", "A-real-password-1")
    monkeypatch.setattr(main.settings, "whatsapp_allow_unsigned", False)
    return main


def test_example_secret_key_is_refused(prod, monkeypatch):
    prod.check_production_settings()
    for value in ("replace-with-a-long-random-string", prod.DEFAULT_SECRET_KEY, "short"):
        monkeypatch.setattr(prod.settings, "secret_key", value)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            prod.check_production_settings()


def test_unsigned_webhooks_are_refused_in_production(prod, monkeypatch):
    monkeypatch.setattr(prod.settings, "whatsapp_allow_unsigned", True)
    with pytest.raises(RuntimeError, match="WHATSAPP_ALLOW_UNSIGNED"):
        prod.check_production_settings()


def test_environment_name_is_not_case_sensitive(monkeypatch):
    for value in ("Production", " PRODUCTION ", "production"):
        monkeypatch.setenv("ENVIRONMENT", value)
        assert Settings().environment == "production"


# --- Public pages are rate limited --------------------------------------------------------------


def test_public_reads_are_rate_limited(client, company_a):
    from app.routers.public import POLLS_PER_CHAT_PER_MINUTE, PUBLIC_READS_PER_IP_PER_MINUTE

    company, _ = company_a
    base = f"/api/public/companies/{company['slug']}"
    codes = [client.get(base if i % 2 else f"{base}/packages").status_code
             for i in range(PUBLIC_READS_PER_IP_PER_MINUTE)]
    assert set(codes) == {200}
    assert client.get(base).status_code == 429

    token = client.post(f"{base}/chats", json={}).json()["token"]
    polls = [client.get(f"{base}/chats/{token}/messages").status_code for _ in range(POLLS_PER_CHAT_PER_MINUTE)]
    assert set(polls) == {200}
    assert client.get(f"{base}/chats/{token}/messages").status_code == 429
    # Unknown chat links are just "not found".
    assert client.get(f"{base}/chats/nope/messages").status_code == 404


# --- AI training texts: invisible characters are removed ----------------------------------------


def test_control_characters_are_removed_from_ai_texts(client, company_a):
    _, admin = company_a
    r = client.post("/api/training", headers=admin, json={"question": "Visa\x00 for Turkey?",
                                                          "answer": "e-Visa\u202e online\r\nin 2 days"})
    assert r.status_code == 201, r.text
    assert r.json()["question"] == "Visa for Turkey?" and r.json()["answer"] == "e-Visa online\nin 2 days"
    r = client.post("/api/training/import", headers=admin,
                    json={"text": "Hello\x00 there\t\u2066answer\u2069", "preview": True})
    assert r.status_code == 200 and r.json()["rows"][0] == {"line": 1, "question": "Hello there", "answer": "answer"}
    r = client.patch("/api/training/knowledge", headers=admin,
                     json={"knowledge_base": "Office\x07 hours:\n9-5", "ai_instructions": "Be kind\x1b[0m"})
    assert r.json()["knowledge_base"] == "Office hours:\n9-5" and r.json()["ai_instructions"] == "Be kind[0m"
