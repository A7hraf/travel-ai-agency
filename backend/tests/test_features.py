"""Features and AI capabilities given by the platform owner: limits per month or in total, the employees who may
use a feature, prices and analytics levels, and what the company sees."""

from tests.conftest import login
from tests.test_library import dubai_request, switch
from tests.test_requests_flow import wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)


def test_limits_seats_prices_and_levels(client, wa, scripted, owner):
    company, admin, fake = wa
    cid = company["id"]
    t, base = dubai_request(client, admin, scripted)
    assert client.post(f"{base}/ai-draft", headers=admin).status_code == 403
    state = switch(client, owner, cid, trip_planner={"on": True, "limit": 1, "period": "month", "price": "15"},
                   insights={"on": True, "levels": ["basic", "finance"]})
    assert state["grants"]["trip_planner"]["price"] in ("15", "15.000") and state["grants"]["insights"]["levels"] == ["basic", "finance"]
    from app.ai.llm import MockTravelLLM, set_llm_client
    set_llm_client(MockTravelLLM())
    assert client.post(f"{base}/ai-draft", headers=admin).status_code == 200
    r = client.post(f"{base}/ai-draft", headers=admin)
    assert r.status_code == 429 and "1 uses" in r.json()["detail"]
    mine = client.get("/api/features", headers=admin).json()
    assert mine["usage"]["trip_planner"] == 1 and set(mine["grants"]) - {"ai_training"} == {"trip_planner", "insights"}
    assert client.get(f"/api/system/companies/{cid}/features", headers=owner).json()["usage"]["trip_planner"] == 1
    assert client.put(f"/api/system/companies/{cid}/features", headers=owner, json={"nope": {"on": True}}).status_code == 422
    assert client.put(f"/api/system/companies/{cid}/features", headers=admin, json={"advisor": {"on": True}}).status_code == 403

    # One employee only: the admin picks who (here an agent), the others can't use it.
    switch(client, owner, cid, advisor={"on": True, "seats": 1})
    assert client.get("/api/advisor", headers=admin).status_code == 403
    assert "advisor" not in client.get("/api/auth/me", headers=admin).json()["company"]["addons"]
    agent = client.post("/api/users", headers=admin, json={"email": "agent@bluesky.com", "full_name": "Agent One",
                                                           "password": "Agent-Pass-123!", "role": "ticket_agent"})
    assert agent.status_code == 201, agent.text
    aid = agent.json()["id"]
    me_id = client.get("/api/auth/me", headers=admin).json()["id"]
    assert client.put(f"/api/team/{aid}/features", headers=admin, json={"features": ["advisor"]}).status_code == 200
    assert client.put(f"/api/team/{me_id}/features", headers=admin, json={"features": ["advisor"]}).status_code == 409
    assert client.put(f"/api/team/{aid}/features", headers=admin, json={"features": ["trip_planner"]}).status_code == 422
    agent_h = login(client, "agent@bluesky.com", "Agent-Pass-123!")
    assert "advisor" in client.get("/api/auth/me", headers=agent_h).json()["company"]["addons"]
    assert "seats" not in client.get("/api/features", headers=agent_h).json()
    assert client.get("/api/features", headers=admin).json()["seats"]["advisor"] == [aid]
    # Fewer seats later: the extra holders lose it. Off: nobody has it.
    switch(client, owner, cid, advisor={"on": True, "seats": None})
    assert client.get("/api/advisor", headers=admin).status_code != 403
    switch(client, owner, cid, advisor={"on": False})
    assert client.get("/api/advisor", headers=agent_h).status_code == 403
