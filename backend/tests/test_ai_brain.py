"""The AI brain: custom trips for individual travellers, AI-drafted options that learn, and insights."""

import json

import pytest

from app.ai import planner
from app.ai.llm import LLMError, LLMResponse, ToolCall
from app.platform_settings import LLMConfig
from tests.conftest import make_company
from tests.test_ai_agent import say, start_chat


def switch(client, owner, company_id, **addons):
    r = client.put(f"/api/system/companies/{company_id}/addons", headers=owner, json=addons)
    assert r.status_code == 200, r.text


CUSTOM = {"destination": "Zanzibar", "origin": "Muscat", "travellers": 2, "needs": ["flight", "hotel"],
          "depart_date": "2030-02-10", "return_date": "2030-02-17", "traveller_names": "Huda Al Balushi\nAli Al Balushi",
          "budget": "1500 OMR", "notes": "Beach, quiet, honeymoon"}


def draft_reply(*items):
    return LLMResponse(json.dumps({"options": list(items)}))


def opt(category, title, provider, estimate=None, reason="fits"):
    return {"category": category, "title": title, "provider": provider, "details": "d", "estimate_price": estimate, "reason": reason}


@pytest.fixture
def planner_on(client, owner, company_a):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True, insights=True)
    return company, admin


def custom_request(client, company, scripted):
    """An individual traveller asks the AI for a tailor-made trip on the website."""
    llm = scripted([LLMResponse(None, [ToolCall("c", "request_custom_trip", CUSTOM)]), LLMResponse("Sent to our team!")])
    token = start_chat(client, company["slug"], name="Huda")
    say(client, company["slug"], token, "Plan me a honeymoon in Zanzibar")
    return llm, token


def test_everything_is_off_until_the_owner_switches_it_on(client, owner, company_a, scripted):
    company, admin = company_a
    llm = scripted([LLMResponse(None, [ToolCall("c", "request_custom_trip", CUSTOM)]), LLMResponse("ok")])
    say(client, company["slug"], start_chat(client, company["slug"]), "custom trip please")
    assert "CUSTOM TRIPS" not in llm.calls[0][0]["content"]
    assert "not available" in [m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"]
    assert client.get("/api/b2b/requests", headers=admin).status_code == 403
    assert client.get("/api/insights", headers=admin).status_code == 403
    assert client.get("/api/system/insights", headers=admin).status_code == 403


def test_custom_trip_drafted_by_ai_chosen_by_the_traveller(client, planner_on, scripted):
    company, admin = planner_on
    llm, token = custom_request(client, company, scripted)
    assert "CUSTOM TRIPS" in llm.calls[0][0]["content"]
    rows = client.get("/api/b2b/requests?kind=individual", headers=admin).json()
    assert len(rows) == 1 and rows[0]["kind"] == "individual" and rows[0]["reference"].startswith("CT-")
    assert rows[0]["client_name"] == "Huda" and client.get("/api/b2b/requests?kind=business", headers=admin).json() == []
    rid = rows[0]["id"]

    # The AI drafts: wrong parts, extra options and bad prices are dropped; at most 3 per part.
    llm = scripted([draft_reply(
        opt("flight", "Oman Air via Dar es Salaam", "Oman Air", 640), opt("flight", "Qatar Airways via Doha", "Qatar Airways", 590),
        opt("flight", "Emirates via Dubai", "Emirates", 700), opt("flight", "Fourth flight", "flydubai", 400),
        opt("hotel", "Baraza Resort", "Baraza", "abc"), opt("spa", "Spa day", "Spa", 50), {"nonsense": True})])
    trip = client.post(f"/api/b2b/requests/{rid}/ai-draft", headers=admin).json()
    assert [(o["category"], o["added_by"]) for o in trip["options"]] == [("flight", "ai")] * 3 + [("hotel", "ai")]
    assert trip["options"][0]["estimate_price"] == "640.000" and trip["options"][3]["estimate_price"] is None
    assert trip["options"][0]["ai_reason"] == "fits" and trip["status"] == "options_ready"
    # The planner never sees the traveller names; it gets the needs and preferences only.
    sent = llm.calls[0][1]["content"]
    assert "Huda" not in sent and "Ali Al Balushi" not in sent and "Zanzibar" in sent and "honeymoon" in sent
    # An AI estimate is never sent to the client: staff must set the real price.
    ids = [o["id"] for o in trip["options"]]
    r = client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": [ids[0], ids[3]]})
    assert r.status_code == 422
    for i in (0, 3):
        o = trip["options"][i]
        client.put(f"/api/b2b/requests/{rid}/options/{o['id']}", headers=admin, json={
            "category": o["category"], "title": o["title"], "provider": o["provider"], "price": "700" if i == 0 else "900"})
    r = client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": [ids[0], ids[3]]})
    assert r.json()["status"] == "with_client"
    # The traveller gets the numbered options in their chat and answers there.
    conv = client.get("/api/conversations", headers=admin).json()[0]
    detail = client.get(f"/api/conversations/{conv['id']}", headers=admin).json()
    assert "1. Oman Air via Dar es Salaam" in detail["messages"][-1]["content"]
    ref = rows[0]["reference"]
    scripted([LLMResponse(None, [ToolCall("ch", "choose_custom_trip_options", {"reference": ref, "option_numbers": [1, 2]})]),
              LLMResponse("Great choice!")])
    say(client, company["slug"], token, "1 and 2 please")
    trip = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()
    assert trip["status"] == "chosen" and trip["total_price"] == "1600.000"

    # Learning: the next draft is told what this agency's clients choose and what staff drop.
    scripted([LLMResponse(None, [ToolCall("c", "request_custom_trip", {**CUSTOM, "destination": "Bali"})]), LLMResponse("ok")])
    say(client, company["slug"], token, "And another one to Bali")
    rid2 = next(r["id"] for r in client.get("/api/b2b/requests", headers=admin).json() if r["id"] != rid)
    llm = scripted([draft_reply(opt("flight", "Oman Air via Muscat", "Oman Air", 500))])
    client.post(f"/api/b2b/requests/{rid2}/ai-draft", headers=admin)
    system = llm.calls[0][0]["content"]
    assert "usually choose Oman Air (chosen 1 of 1 times sent)" in system and "Baraza" in system
    stats = planner.learned_stats(__import__("app.database", fromlist=["SessionLocal"]).SessionLocal(), company["id"])
    qatar = next(r for r in stats["flight"] if r["provider"] == "Qatar Airways")
    assert qatar["suggested"] == 1 and qatar["removed"] == 1 and qatar["chosen"] == 0


def test_planner_failures_and_web_search(client, planner_on, scripted, monkeypatch):
    company, admin = planner_on
    custom_request(client, company, scripted)
    rid = client.get("/api/b2b/requests", headers=admin).json()[0]["id"]
    scripted([LLMResponse("Sorry, I can't help with that.")])
    assert client.post(f"/api/b2b/requests/{rid}/ai-draft", headers=admin).status_code == 502
    # With web search: if the search call fails, the planner retries without it.
    monkeypatch.setattr(planner, "_web_search_tools", lambda: [{"type": "browser_search"}])
    llm = scripted([LLMError("search unavailable"), draft_reply(opt("hotel", "Zuri Zanzibar", "Zuri", 1200))])
    trip = client.post(f"/api/b2b/requests/{rid}/ai-draft", headers=admin).json()
    assert [o["title"] for o in trip["options"]] == ["Zuri Zanzibar"] and len(llm.calls) == 2
    assert "web search" not in trip["events"][-1]["detail"]
    # Web search is offered only on Groq's gpt-oss models.
    monkeypatch.undo()
    groq = LLMConfig("openai", "https://api.groq.com/openai/v1", "k", "openai/gpt-oss-120b", [], "")
    monkeypatch.setattr(planner, "llm_config", lambda: groq)
    assert planner._web_search_tools() == [{"type": "browser_search"}]
    monkeypatch.setattr(planner, "llm_config", lambda: LLMConfig("openai", "https://api.openai.com/v1", "k", "gpt-4o", [], ""))
    assert planner._web_search_tools() == []


def test_company_insights_and_report(client, planner_on, scripted):
    company, admin = planner_on
    scripted([LLMResponse(None, [ToolCall("s", "search_packages", {"query": "Maldives honeymoon"})]), LLMResponse("Here you go")])
    say(client, company["slug"], start_chat(client, company["slug"]), "Maldives honeymoon")
    data = client.get("/api/insights", headers=admin).json()
    m = data["metrics"]
    assert m["chats"]["total"] == 1 and m["bookings"]["total"] == 0 and data["report"] is None
    assert ["maldives", 1] in m["customers_searched_for"] and ["honeymoon", 1] in m["customers_searched_for"]
    llm = scripted([LLMResponse("## Summary\n- One chat about the Maldives, no bookings yet. Add a Maldives package.")])
    r = client.post("/api/insights/report", headers=admin, json={"language": "ar"})
    assert r.status_code == 200 and r.json()["language"] == "ar" and "Maldives" in r.json()["content"]
    assert "Arabic" in llm.calls[0][0]["content"] and json.loads(llm.calls[0][1]["content"])["chats"]["total"] == 1
    assert client.get("/api/insights", headers=admin).json()["report"]["id"] == r.json()["id"]
    scripted([LLMResponse("short")])
    assert client.post("/api/insights/report", headers=admin, json={}).status_code == 502


def test_owner_sees_totals_never_customers_words(client, owner, planner_on, scripted):
    company, admin = planner_on
    other, _ = make_company(client, owner, name="Quiet Travel", admin_email="q@quiet.com")
    scripted([LLMResponse(None, [ToolCall("s", "search_packages", {"query": "secret island"})]), LLMResponse("ok")])
    say(client, company["slug"], start_chat(client, company["slug"]), "secret island")
    data = client.get("/api/system/insights", headers=owner).json()["metrics"]
    rows = {r["name"]: r for r in data["companies"]}
    assert rows[company["name"]]["chats_30d"] == 1 and rows["Quiet Travel"]["chats_30d"] == 0
    assert any("at risk" in tip for tip in rows["Quiet Travel"]["opportunities"])
    assert data["totals"]["addon_use"]["insights"] == 1
    assert "secret island" not in json.dumps(data)
    one = client.get(f"/api/system/companies/{company['id']}/insights", headers=owner).json()["metrics"]
    assert "customers_searched_for" not in one and "low_ratings" not in one and one["chats"]["total"] == 1
    llm = scripted([LLMResponse("## Platform health\n- Two agencies, one active this month. Call Quiet Travel.")])
    r = client.post("/api/system/insights/report", headers=owner, json={"language": "en"})
    assert r.status_code == 200 and "secret island" not in llm.calls[0][1]["content"]
    assert client.get("/api/system/insights", headers=owner).json()["report"]["id"] == r.json()["id"]
    # A company never sees another's figures, nor the owner's report.
    assert client.get(f"/api/system/companies/{other['id']}/insights", headers=admin).status_code == 403
    assert client.post("/api/system/insights/report", headers=admin, json={}).status_code == 403
