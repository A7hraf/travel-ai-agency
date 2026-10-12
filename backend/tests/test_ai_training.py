"""AI provider problems, the 'Test AI' check, company training answers, Arabic and Omani rials."""

import httpx
import pytest

from app.ai import llm as llm_module
from app.ai.llm import LLMError, LLMResponse, OpenAICompatibleClient, ToolCall, set_llm_client
from app.config import get_settings
from tests.conftest import future, login, make_company, make_package

CHAT = "/api/public/companies/{slug}/chats"


class FakeProvider:
    """Plays a list of (status, json, headers) answers and records the requests."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests: list[dict] = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.requests.append(json)
        status, body, extra = self.answers.pop(0)
        return httpx.Response(status, json=body, headers=extra or {}, request=httpx.Request("POST", url))


OK = (200, {"choices": [{"message": {"content": "Hello"}}]}, None)
TOOL = (200, {"choices": [{"message": {"content": None, "tool_calls": [
    {"id": "t1", "type": "function", "function": {"name": "functions.search_packages", "arguments": "{}"}}]}}]}, None)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(llm_module, "RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)


def test_retired_model_falls_back_to_the_next_one(monkeypatch):
    provider = FakeProvider([
        (404, {"error": {"message": "The model `llama-3.3-70b-versatile` has been decommissioned",
                         "code": "model_decommissioned"}}, None),
        OK,
    ])
    monkeypatch.setattr(llm_module.httpx, "post", provider)
    client = OpenAICompatibleClient("https://api.groq.com/openai/v1", " gsk_key\n", "llama-3.3-70b-versatile", 0.3,
                                    5, fallback_models=["openai/gpt-oss-120b"], reasoning_effort="low")
    assert client.chat([], []).content == "Hello"
    assert [r["model"] for r in provider.requests] == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert provider.requests[1]["reasoning_effort"] == "low"
    assert client.last_model == "openai/gpt-oss-120b"


def test_busy_provider_is_retried_with_retry_after(monkeypatch):
    provider = FakeProvider([(429, {"error": {"message": "Rate limit"}}, {"retry-after": "1"}), TOOL])
    monkeypatch.setattr(llm_module.httpx, "post", provider)
    client = OpenAICompatibleClient("http://x/v1", "k", "m", 0.3, 5)
    resp = client.chat([], [{"type": "function", "function": {"name": "search_packages"}}])
    assert resp.tool_calls[0].name == "search_packages"  # "functions." prefix removed
    assert len(provider.requests) == 2


def test_provider_error_message_is_kept(monkeypatch):
    provider = FakeProvider([(401, {"error": {"message": "Invalid API Key"}}, None)])
    monkeypatch.setattr(llm_module.httpx, "post", provider)
    client = OpenAICompatibleClient("http://x/v1", "bad", "openai/gpt-oss-120b", 0.3, 5)
    with pytest.raises(LLMError, match="401: Invalid API Key"):
        client.chat([], [])
    assert len(provider.requests) == 1  # a wrong key is not retried


def test_ai_check_reports_problem_and_success(client, owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "openai_compatible")

    class Broken:
        def chat(self, messages, tools):
            raise LLMError("openai/gpt-oss-120b -> 401: Invalid API Key")

    set_llm_client(Broken())
    r = client.post("/api/system/ai-check", headers=owner).json()
    assert r["ok"] is False and "Invalid API Key" in r["message"]

    class Works:
        def chat(self, messages, tools):
            return LLMResponse(None, [ToolCall("t", "search_packages", {"query": "beach"})])

    set_llm_client(Works())
    r = client.post("/api/system/ai-check", headers=owner).json()
    assert r["ok"] is True and r["uses_tools"] is True


def test_ai_check_needs_rights(client, company_a):
    _, admin = company_a
    assert client.post("/api/system/ai-check", headers=admin).status_code == 403
    assert client.post("/api/company/ai-check", headers=admin).status_code == 200


def test_training_answers_reach_the_ai_for_similar_questions(client, owner, scripted):
    company, admin = make_company(client, owner, name="Alpha Travel", admin_email="admin@alpha.com")
    other, other_admin = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    client.post("/api/training", headers=admin, json={
        "question": "هل يمكن الدفع بالتقسيط؟", "answer": "نعم، ادفع 30% الآن والباقي على دفعتين."})
    client.post("/api/training", headers=admin, json={
        "question": "Where is your office?", "answer": "Al Khuwair, Muscat."})
    client.post("/api/training", headers=other_admin, json={
        "question": "Where is your office?", "answer": "BETA SECRET OFFICE"})

    llm = scripted([LLMResponse("ok"), LLMResponse("ok")])
    slug = company["slug"]
    token = client.post(CHAT.format(slug=slug), json={}).json()["token"]
    client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": "ممكن الدفع بالتقسيط؟"})
    client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": "where is the office"})
    first, second = llm.calls[0][0]["content"], llm.calls[1][0]["content"]
    assert "ادفع 30%" in first and "Al Khuwair" not in first
    assert "Al Khuwair, Muscat." in second
    assert "BETA SECRET" not in first + second


def test_training_management_rights(client, company_a):
    _, admin = company_a
    r = client.post("/api/training", headers=admin, json={"question": "Visa?", "answer": "We help."})
    assert r.status_code == 201
    example_id = r.json()["id"]
    r = client.put(f"/api/training/{example_id}", headers=admin, json={"question": "Visa?", "answer": "Yes."})
    assert r.json()["answer"] == "Yes."
    client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "S", "password": "Password123", "role": "support"})
    support = login(client, "s@bluesky.com", "Password123")
    assert client.post("/api/training", headers=support, json={"question": "x?", "answer": "y"}).status_code == 403
    assert client.delete(f"/api/training/{example_id}", headers=admin).status_code == 204
    assert client.get("/api/training", headers=admin).json() == []


def test_omani_rial_prices_keep_three_decimals(client, company_a, scripted):
    company, admin = company_a
    assert company["currency"] == "OMR"
    pkg = make_package(client, admin, title="Salalah Khareef", price_per_person=125.5, child_price=85.25)
    assert pkg["currency"] == "OMR" and pkg["price_per_person"] == 125.5 and pkg["child_price"] == 85.25
    seen = {}

    def capture(messages):
        import json as _json
        seen["result"] = _json.loads(messages[-1]["content"])
        return LLMResponse("Booked.")

    llm = scripted([
        LLMResponse(None, [ToolCall("b", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 2, "children": 1,
            "lead_traveler_name": "Salim", "contact_phone": "+968 9000 1111"})]),
        capture,
    ])
    slug = company["slug"]
    token = client.post(CHAT.format(slug=slug), json={}).json()["token"]
    client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": "book"})
    assert seen["result"]["total_price"] == 336.25  # 2 x 125.500 + 85.250
    assert client.get("/api/tickets", headers=admin).json()[0]["total_price"] == 336.25
    assert "Omani rials" in llm.calls[0][0]["content"]


def test_arabic_customers_find_packages(client, company_a, scripted):
    company, admin = company_a
    make_package(client, admin, title="Salalah Khareef Weekend", destination="Salalah", country="Oman",
                 tags=["khareef", "صلالة", "خريف"])
    make_package(client, admin, title="Paris", destination="Paris", country="France", tags=["باريس"])
    seen = {}

    def capture(messages):
        import json as _json
        seen["titles"] = [r["title"] for r in _json.loads(messages[-1]["content"])["results"]]
        return LLMResponse("ok")

    scripted([LLMResponse(None, [ToolCall("s", "search_packages", {"query": "ابغى رحلة إلى صلاله في الخريف"})]),
              capture])
    slug = company["slug"]
    token = client.post(CHAT.format(slug=slug), json={}).json()["token"]
    client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": "صلالة"})
    assert seen["titles"] == ["Salalah Khareef Weekend"]


def test_arabic_welcome_message(client, company_a):
    company, _ = company_a
    r = client.post(CHAT.format(slug=company["slug"]), json={"lang": "ar"}).json()
    assert "أهلاً" in r["messages"][0]["content"]
    r = client.post(CHAT.format(slug=company["slug"]), json={"lang": "en"}).json()
    assert r["messages"][0]["content"].startswith("Hi!")


def test_ai_hourly_cap_protects_quota(client, company_a, scripted, monkeypatch):
    company, admin = company_a
    monkeypatch.setattr(get_settings(), "ai_max_replies_per_company_per_hour", 1)
    llm = scripted([LLMResponse("first answer"), LLMResponse("never")])
    slug = company["slug"]
    t1 = client.post(CHAT.format(slug=slug), json={}).json()["token"]
    t2 = client.post(CHAT.format(slug=slug), json={}).json()["token"]
    client.post(f"{CHAT.format(slug=slug)}/{t1}/messages", json={"content": "hi"})
    out = client.post(f"{CHAT.format(slug=slug)}/{t2}/messages", json={"content": "hi"}).json()
    assert len(llm.calls) == 1
    assert out["status"] == "human" and "consultant" in out["messages"][-1]["content"]
