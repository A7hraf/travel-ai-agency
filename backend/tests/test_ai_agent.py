"""The AI agent: tool calls, booking up to payment, handover to employees, failures."""

import json

import httpx

from app.ai import llm as llm_module
from app.ai.agent import _repair
from app.ai.llm import LLMError, LLMResponse, OpenAICompatibleClient, ToolCall
from tests.conftest import future, make_company, make_package

CHAT = "/api/public/companies/{slug}/chats"


def start_chat(client, slug, **body):
    r = client.post(CHAT.format(slug=slug), json=body)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def say(client, slug, token, text):
    r = client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": text})
    assert r.status_code == 200, r.text
    return r.json()


def tool_result(messages, index=-1) -> dict:
    assert messages[index]["role"] == "tool"
    return json.loads(messages[index]["content"])


def test_ai_books_until_payment_then_hands_over(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    make_package(client, admin, title="Dubai City Break", destination="Dubai", country="UAE", tags=["city"],
                 price_per_person=800, child_price=None)
    slug = company["slug"]
    seen = {}

    def recommend(messages):
        result = tool_result(messages)
        assert [r["title"] for r in result["results"]] == ["Maldives Honeymoon"]
        return LLMResponse(f"I recommend Maldives Honeymoon at {result['results'][0]['price_per_person']} USD.")

    def confirm(messages):
        result = tool_result(messages)
        seen["ref"] = result["ticket_reference"]
        assert result["total_price"] == 5000  # 2 adults x 2000 + 1 child x 1000, computed by the server
        return LLMResponse(f"Booked! Your reference is {result['ticket_reference']}. A consultant will call you.")

    llm = scripted([
        LLMResponse(None, [ToolCall("c1", "search_packages", {"query": "Maldives honeymoon"})]),
        recommend,
        LLMResponse(None, [ToolCall("c2", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 2, "children": 1,
            "lead_traveler_name": "Ali Hassan", "contact_phone": "+971500000000",
            # a price sent by the model is ignored
            "total_price": 1,
        })]),
        confirm,
    ])

    token = start_chat(client, slug)
    out = say(client, slug, token, "Honeymoon in the Maldives please")
    assert out["status"] == "ai"
    assert [m["sender"] for m in out["messages"]] == ["customer", "ai"]
    assert "Maldives Honeymoon" in out["messages"][-1]["content"]

    out = say(client, slug, token, f"Yes, book {future(30)}, 2 adults 1 child, Ali Hassan +971500000000")
    assert out["status"] == "human"
    assert seen["ref"] in out["messages"][-1]["content"]

    # The second turn saw the first turn's tool call and result, in a valid order.
    roles = [m["role"] for m in llm.calls[2]]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert "Blue Sky Travel" in llm.calls[0][0]["content"]

    tickets = client.get("/api/tickets", headers=admin).json()
    assert len(tickets) == 1
    t = tickets[0]
    assert t["reference"] == seen["ref"]
    assert t["status"] == "pending_payment"
    assert t["total_price"] == 5000
    assert t["adults"] == 2 and t["children"] == 1
    assert t["customer"]["name"] == "Ali Hassan"

    conv = client.get("/api/conversations", headers=admin).json()[0]
    assert conv["status"] == "human"
    assert seen["ref"] in conv["handover_reason"]

    # While a human is in charge the AI stays quiet.
    calls_before = len(llm.calls)
    out = say(client, slug, token, "When will you call me?")
    assert [m["sender"] for m in out["messages"]] == ["customer"]
    assert len(llm.calls) == calls_before

    # An employee answers from the dashboard; the customer's chat receives it.
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=admin,
                    json={"content": "Hi Ali, here is the payment link."})
    assert r.status_code == 201
    polled = client.get(f"{CHAT.format(slug=slug)}/{token}/messages", params={"after_id": 0}).json()
    assert polled["messages"][-1] == {**polled["messages"][-1], "sender": "agent",
                                      "content": "Hi Ali, here is the payment link."}
    # Tool calls and internal events are never shown to the customer.
    assert {m["sender"] for m in polled["messages"]} <= {"customer", "ai", "agent"}

    # Hand back to the AI: it answers again.
    client.post(f"/api/conversations/{conv['id']}/release", headers=admin)
    scripted([LLMResponse("Anything else I can help with?")])
    out = say(client, slug, token, "Thanks!")
    assert out["messages"][-1]["content"] == "Anything else I can help with?"


def test_tools_cannot_touch_other_companies(client, owner, scripted):
    company_a, admin_a = make_company(client, owner, name="Company A", admin_email="a@a.com")
    _, admin_b = make_company(client, owner, name="Company B", admin_email="b@b.com")
    other_pkg = make_package(client, admin_b, title="Secret B Trip")
    seen = {}

    def check(messages):
        seen["details"] = tool_result(messages, -2)
        seen["booking"] = tool_result(messages, -1)
        return LLMResponse("Sorry, that trip is not available.")

    scripted([
        LLMResponse(None, [
            ToolCall("x1", "get_package_details", {"package_id": other_pkg["id"]}),
            ToolCall("x2", "create_booking_ticket", {
                "package_id": other_pkg["id"], "departure_date": future(30), "adults": 1,
                "lead_traveler_name": "Eve", "contact_phone": "1"}),
        ]),
        check,
    ])
    token = start_chat(client, company_a["slug"])
    say(client, company_a["slug"], token, "Book the secret B trip")
    assert "error" in seen["details"] and "error" in seen["booking"]
    assert client.get("/api/tickets", headers=admin_b).json() == []


def test_booking_validation_errors_go_back_to_the_model(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, seats_available=2)
    results = []

    def collect(messages):
        results.append(tool_result(messages))
        return LLMResponse("Let me fix that.")

    base = {"package_id": pkg["id"], "lead_traveler_name": "Ali", "contact_phone": "+1"}
    scripted([
        LLMResponse(None, [ToolCall("a", "create_booking_ticket", {**base, "departure_date": future(31), "adults": 1})]),
        collect,
        LLMResponse(None, [ToolCall("b", "create_booking_ticket", {**base, "departure_date": future(30), "adults": 3})]),
        collect,
    ])
    token = start_chat(client, company["slug"])
    say(client, company["slug"], token, "book wrong date")
    say(client, company["slug"], token, "book too many people")
    assert results[0]["error"] == "This date is not available."
    assert results[0]["available_dates"] == [future(30), future(60)]
    assert "seats" in results[1]["error"]
    assert client.get("/api/tickets", headers=admin).json() == []


def test_model_failure_hands_over_with_a_polite_reply(client, company_a, scripted):
    company, admin = company_a
    scripted([LLMError("connection refused")])
    token = start_chat(client, company["slug"])
    out = say(client, company["slug"], token, "Hello?")
    assert out["status"] == "human"
    assert "consultant" in out["messages"][-1]["content"]
    conv = client.get("/api/conversations", headers=admin).json()[0]
    assert "AI unavailable" in conv["handover_reason"]


def test_failure_after_booking_keeps_the_ticket(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin)
    scripted([
        LLMResponse(None, [ToolCall("b", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 1,
            "lead_traveler_name": "Ali", "contact_phone": "+1"})]),
        LLMError("timeout"),
    ])
    token = start_chat(client, company["slug"])
    out = say(client, company["slug"], token, "book it")
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    assert ticket["reference"] in out["messages"][-1]["content"]


def test_mock_brain_searches_catalog(client, company_a):
    company, admin = company_a
    make_package(client, admin)
    token = start_chat(client, company["slug"])
    out = say(client, company["slug"], token, "Any beach trips in the Maldives?")
    assert "Maldives Honeymoon" in out["messages"][-1]["content"]


def test_web_chat_rejects_bad_token_and_rate_limits(client, company_a):
    company, _ = company_a
    slug = company["slug"]
    assert client.post(f"{CHAT.format(slug=slug)}/nope/messages", json={"content": "hi"}).status_code == 404
    token = start_chat(client, slug)
    codes = [client.post(f"{CHAT.format(slug=slug)}/{token}/messages", json={"content": "hi"}).status_code
             for _ in range(14)]
    assert 429 in codes


def test_history_repair_drops_broken_tool_sequences():
    history = [
        {"role": "assistant", "content": "welcome"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},  # result missing
        {"role": "user", "content": "hello?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "2"}]},
        {"role": "tool", "tool_call_id": "2", "content": "{}"},
        {"role": "assistant", "content": "done"},
    ]
    assert [m["role"] for m in _repair(history)] == ["user", "user", "assistant", "tool", "assistant"]


def _fake_post(message):
    def post(url, json=None, headers=None, timeout=None):
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"choices": [{"message": message}]}, request=request)
    return post


def test_openai_compatible_client_parsing(monkeypatch):
    tools = [{"type": "function", "function": {"name": "search_packages", "parameters": {}}}]
    client = OpenAICompatibleClient("http://llm/v1", "key", "travel-agent", 0.2, 5)

    monkeypatch.setattr(llm_module.httpx, "post", _fake_post({
        "content": "", "tool_calls": [{"id": "t1", "function": {"name": "search_packages",
                                                               "arguments": "{\"query\": \"Bali\"}"}}]}))
    resp = client.chat([], tools)
    assert resp.tool_calls[0].name == "search_packages" and resp.tool_calls[0].arguments == {"query": "Bali"}

    # Small models sometimes print the tool call as JSON text.
    monkeypatch.setattr(llm_module.httpx, "post", _fake_post({
        "content": "```json\n{\"name\": \"search_packages\", \"arguments\": {\"query\": \"Egypt\"}}\n```"}))
    resp = client.chat([], tools)
    assert resp.tool_calls[0].arguments == {"query": "Egypt"}

    # Reasoning models: hidden thinking is removed.
    monkeypatch.setattr(llm_module.httpx, "post", _fake_post({"content": "<think>hmm</think>Hello!"}))
    assert client.chat([], tools).content == "Hello!"


def test_openai_compatible_client_errors(monkeypatch):
    def broken(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm_module.httpx, "post", broken)
    client = OpenAICompatibleClient("http://llm/v1", "", "m", 0.2, 5)
    try:
        client.chat([], [])
    except LLMError:
        pass
    else:
        raise AssertionError("expected LLMError")


def test_prompt_contains_company_knowledge(client, company_a, scripted):
    company, admin = company_a
    client.patch("/api/company", headers=admin, json={
        "ai_agent_name": "Layla", "knowledge_base": "Deposit is 25%.", "ai_instructions": "Always greet with Salam."})
    llm = scripted([LLMResponse("Salam!")])
    token = start_chat(client, company["slug"], name="Omar", phone="+20100")
    say(client, company["slug"], token, "hi")
    system = llm.calls[0][0]["content"]
    assert "You are Layla" in system
    assert "Deposit is 25%." in system
    assert "Always greet with Salam." in system
    assert "+20100" in system
