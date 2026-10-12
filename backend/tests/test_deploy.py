"""Single-container hosting: database URLs, serving the website, retries on hosted AI."""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai import llm as llm_module
from app.ai.llm import OpenAICompatibleClient
from app.database import normalize_database_url
from app.main import mount_frontend


def test_hosted_postgres_urls_use_psycopg():
    assert normalize_database_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_website_is_served_next_to_the_api(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")

    application = FastAPI()

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_frontend(application, tmp_path)
    client = TestClient(application)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/unknown").status_code == 404  # API typos are not hidden by the SPA
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    for path in ("/", "/login", "/app/conversations/3", "/c/sunrise-travel"):
        assert client.get(path).text == "<html>app</html>"
    assert "nope" not in client.get("/../secret.txt").text
    assert "nope" not in client.get("/%2e%2e/secret.txt").text


def test_rate_limited_ai_request_is_retried_once(monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_DELAY_SECONDS", 0)
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(1)
        request = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "rate limit"}, request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello"}}]}, request=request)

    monkeypatch.setattr(llm_module.httpx, "post", post)
    client = OpenAICompatibleClient("http://llm/v1", "k", "m", 0.2, 5)
    assert client.chat([], []).content == "Hello"
    assert len(calls) == 2
