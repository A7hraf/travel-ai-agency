"""The platform owner limits each company's AI: internet searches per month, which keys live search may use,
and who may use a feature (everyone, company admins only, or a number of employees)."""

from app.ai import planner
from tests.conftest import login
from tests.test_ai_brain import custom_request, draft_reply, opt, switch
from tests.test_live_data import Providers, central_keys

from app.services import live_data


def features(client, owner, cid, **grants):
    r = client.put(f"/api/system/companies/{cid}/features", headers=owner, json=grants)
    assert r.status_code == 200, r.text
    return r.json()


def test_internet_searches_have_their_own_monthly_limit(client, owner, company_a, scripted, monkeypatch):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    features(client, owner, company["id"], web_search={"on": True, "limit": 1})
    monkeypatch.setattr(planner, "_web_search_tools", lambda: [{"type": "browser_search"}])
    t, _ = custom_request(client, company, admin, scripted)
    llm = scripted([draft_reply(opt("hotel", "Zuri", "Zuri", 900))])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert "Search the web" in llm.calls[-1][0]["content"]
    assert client.get("/api/live-data", headers=admin).json()["web"] == {"on": True, "used": 1, "limit": 1, "left": 0}
    # Used up: the next draft works without searching the internet, and the history says so.
    llm = scripted([draft_reply(opt("hotel", "Baraza", "Baraza", 900))])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert "Search the web" not in llm.calls[-1][0]["content"]
    events = client.get(f"/api/tickets/{t['id']}/events", headers=admin).json()
    assert "internet searches used up" in [e for e in events if e["action"] == "ai_drafted"][-1]["new_value"]
    # Switched off: never searches.
    features(client, owner, company["id"], web_search={"on": False})
    llm = scripted([draft_reply(opt("hotel", "Other", "O", 900))])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert "Search the web" not in llm.calls[-1][0]["content"]


def test_live_search_can_be_limited_to_the_companys_own_keys(client, owner, company_a, scripted, monkeypatch):
    company, admin = company_a
    p = Providers()
    monkeypatch.setattr(live_data, "http", p)
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner)
    features(client, owner, company["id"], live_search={"on": True, "levels": ["own_keys"]})
    assert client.get("/api/live-data", headers=admin).json()["providers"] == {}  # the central keys are not for it
    t, _ = custom_request(client, company, admin, scripted)
    scripted([draft_reply(opt("hotel", "Zuri", "Zuri", 900))])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert p.calls == []
    client.put(f"/api/system/companies/{company['id']}/live-data", headers=owner, json={"serpapi_key": "alpha-own-serp-key-999"})
    assert client.get("/api/live-data", headers=admin).json()["providers"] == {"serpapi": "company"}
    # A level that does not belong to live search is refused.
    bad = client.put(f"/api/system/companies/{company['id']}/features", headers=owner,
                     json={"live_search": {"on": True, "levels": ["finance"]}})
    assert bad.status_code == 422


def test_a_feature_for_company_admins_only(client, owner, company_a, scripted):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    features(client, owner, company["id"], trip_planner={"on": True, "admins_only": True})
    r = client.post("/api/users", headers=admin, json={"email": "agent@bluesky.com", "full_name": "Agent", "password": "Agent-Pass-2026",
                                                       "role": "ticket_agent", "permissions": ["tickets.view", "tickets.manage"]})
    assert r.status_code == 201, r.text
    agent = login(client, "agent@bluesky.com", "Agent-Pass-2026")
    t, _ = custom_request(client, company, admin, scripted)
    scripted([draft_reply(opt("hotel", "Zuri", "Zuri", 900))])
    assert client.post(f"/api/tickets/{t['id']}/ai-draft", headers=agent).status_code == 403
    assert client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).status_code == 200
    # The admin can't hand it to an employee either.
    assert client.put(f"/api/team/{r.json()['id']}/features", headers=admin, json={"features": ["trip_planner"]}).status_code == 422
    # A number of employees instead: the admin picks who.
    features(client, owner, company["id"], trip_planner={"on": True, "seats": 1})
    assert client.put(f"/api/team/{r.json()['id']}/features", headers=admin, json={"features": ["trip_planner"]}).status_code == 200
    scripted([draft_reply(opt("hotel", "Baraza", "Baraza", 900))])
    assert client.post(f"/api/tickets/{t['id']}/ai-draft", headers=agent).status_code == 200
