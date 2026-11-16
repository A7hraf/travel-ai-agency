"""Running the team: how long each step takes (late requests), notifications, team performance, and each
employee's plan with reminders sent for them."""

from datetime import date, timedelta

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import Ticket, utcnow
from app.services.notifications import late_steps
from tests.test_library import switch
from tests.test_requests_flow import PHONE, services, wa, wa_say  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

IN_30 = (date.today() + timedelta(days=30)).isoformat()


def ai_request(client, admin, scripted, key="hotel", mid="wamid.t1"):
    sid = services(client, admin)[key]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "Hotel", "answers": {
        "destination": "Dubai", "depart_date": IN_30, "return_date": IN_30, "adults": "2", "rooms": "1", "full_name": "Omar"}})
    wa_say(client, "hotel in Dubai", mid, [LLMResponse(None, [card]), LLMResponse("ok")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    return t, f"/api/tickets/{t['id']}"


def make_agent(client, admin, email="agent@bluesky.com", permissions=None):
    body = {"email": email, "full_name": "Agent Huda", "password": "AgentPass123!", "role": "ticket_agent"}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post("/api/users", headers=admin, json=body)
    assert r.status_code == 201, r.text
    token = client.post("/api/auth/login", json={"email": email, "password": "AgentPass123!"}).json()["access_token"]
    return r.json(), {"Authorization": f"Bearer {token}"}


def age_step(ticket_id, hours):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        t.workflow = [dict(s, started_at=(utcnow() - timedelta(hours=hours)).isoformat()) if s.get("state") == "active" else s
                      for s in t.workflow]
        db.commit()


def kinds(client, h):
    return [n["kind"] for n in client.get("/api/notifications", headers=h).json()["items"]]


def test_late_requests_and_expected_times(client, wa, scripted):
    company, admin, _ = wa
    t, base = ai_request(client, admin, scripted)
    assert t["delay"]["waiting_on"] == "team" and t["delay"]["late"] is False and t["delay"]["limit"] == 4
    age_step(t["id"], 6)
    t = client.get(base, headers=admin).json()
    assert t["delay"]["late"] is True and t["delay"]["hours"] >= 6
    assert [r["id"] for r in client.get("/api/tickets?late=true", headers=admin).json()] == [t["id"]]
    assert client.get("/api/tickets/summary", headers=admin).json()["late"] == 1
    # The owner gives the review more time: no longer late.
    sla = client.put("/api/tickets/sla", headers=admin, json={"hours": {"review": 8}}).json()
    assert sla["hours"]["review"] == 8 and sla["defaults"]["review"] == 4
    assert client.get(base, headers=admin).json()["delay"]["late"] is False
    assert client.put("/api/tickets/sla", headers=admin, json={"hours": {"nope": 3}}).status_code == 422
    assert client.put("/api/tickets/sla", headers=admin, json={"hours": {"review": 0}}).status_code == 422
    _, agent = make_agent(client, admin)
    assert client.put("/api/tickets/sla", headers=agent, json={"hours": {"review": 1}}).status_code == 403
    # A step waiting for the client is not the team's delay.
    oid = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Atlantis", "price": "900"}).json()["options"][0]["id"]
    t = client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]}).json()
    assert t["delay"]["waiting_on"] == "client"


def test_notifications_reach_the_right_people(client, wa, scripted, owner):
    company, admin, _ = wa
    agent_user, agent = make_agent(client, admin)
    t, base = ai_request(client, admin, scripted)
    assert kinds(client, admin) == ["new_request"] and kinds(client, agent) == []  # the agent doesn't assign requests
    n = client.get("/api/notifications", headers=admin).json()
    assert n["unread"] == 1 and n["items"][0]["params"]["ref"] == t["reference"] and n["items"][0]["ticket_id"] == t["id"]
    client.patch(base, headers=admin, json={"assigned_to_id": agent_user["id"]})
    assert kinds(client, agent) == ["assigned"]
    # The client answers in the chat: the assignee hears it, not the admin.
    q = client.post(f"{base}/ask", headers=agent, json={"note": "Which area?"}).json()["questions"][0]
    ans = ToolCall("a", "answer_team_question", {"reference": t["reference"], "question_id": q["id"], "answer": "Marina"})
    wa_say(client, "Marina", "wamid.t2", [LLMResponse(None, [ans]), LLMResponse("Thanks")], scripted)
    assert kinds(client, agent)[0] == "client_answered" and "client_answered" not in kinds(client, admin)
    # An employee changes the price or the payment reference: the admins are told.
    client.put(f"{base}/money", headers=agent, json={"total_price": "900"})
    client.put(f"{base}/money", headers=agent, json={"total_price": "850"})
    client.patch(base, headers=agent, json={"payment_reference": "TRX-1"})
    admin_items = client.get("/api/notifications", headers=admin).json()["items"]
    price = next(x for x in admin_items if x["kind"] == "price_changed")
    assert price["params"]["old"].startswith("900") and price["params"]["new"].startswith("850") and price["params"]["by"] == "Agent Huda"
    assert "reference_changed" in [x["kind"] for x in admin_items] and "price_changed" not in kinds(client, agent)
    # Read: one, then all.
    client.post("/api/notifications/read", headers=admin, json={"ids": [price["id"]]})
    assert client.get("/api/notifications", headers=admin).json()["unread"] == len(admin_items) - 1
    client.post("/api/notifications/read", headers=admin, json={})
    assert client.get("/api/notifications", headers=admin).json()["unread"] == 0
    # A late step is told once to the assignee.
    age_step(t["id"], 30)
    with SessionLocal() as db:
        assert late_steps(db) == 1
        assert late_steps(db) == 0
    assert kinds(client, agent)[0] == "step_late"


def test_team_performance(client, wa, scripted):
    company, admin, _ = wa
    agent_user, agent = make_agent(client, admin)
    t, base = ai_request(client, admin, scripted)
    client.patch(base, headers=admin, json={"assigned_to_id": agent_user["id"]})
    age_step(t["id"], 10)
    client.post(f"{base}/workflow/done", headers=agent, json={"key": "review"})
    assert client.get("/api/tickets/team", headers=agent).status_code == 403
    team = client.get("/api/tickets/team?days=30", headers=admin).json()
    row = next(p for p in team["people"] if p["id"] == agent_user["id"])
    assert row["open"] == 1 and row["steps_done"] == 1 and row["avg_step_hours"] >= 10
    assert team["unassigned"] == {"open": 0, "late": 0}


def test_my_plan_and_reminders(client, wa, scripted, owner):
    company, admin, fake = wa
    t, base = ai_request(client, admin, scripted, key="flights", mid="wamid.t3")
    assert client.get("/api/tickets/plan", headers=admin).status_code == 403
    switch(client, owner, company["id"], daily_brief=True)
    plan = client.get("/api/tickets/plan?period=today", headers=admin).json()
    assert plan["all_requests"] is True and {"unassigned"} <= {i["kind"] for i in plan["items"]}
    # Approved, now waiting for the client's passports for two days: a reminder can be sent from the plan.
    client.put(f"{base}/details", headers=admin, json={"answers": {"origin": "Muscat", "cabin": "Economy"}})
    oid = client.post(f"{base}/options", headers=admin, json={"category": "flight", "title": "WY 101", "price": "300"}).json()["options"][0]["id"]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [oid]})
    client.post(f"{base}/send-final", headers=admin, json={})
    t = client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"}).json()
    assert t["current_step"]["type"] == "documents"
    age_step(t["id"], 50)
    item = next(i for i in client.get("/api/tickets/plan", headers=admin).json()["items"] if i["kind"] == "remind_client")
    assert item["can_remind"] is True and item["ticket_id"] == t["id"]
    sent = len(fake.sent)
    assert client.post(f"{base}/remind", headers=admin).status_code == 200
    assert len(fake.sent) == sent + 1 and "Passport copy" in fake.sent[-1][2]
    assert client.post(f"{base}/remind", headers=admin).status_code == 429
    # The team's own step can't be "reminded".
    client.post(f"{base}/workflow/done", headers=admin, json={"key": "documents"})
    client.post(f"{base}/payments", headers=admin, json={"amount": "300", "reference": "X1"})
    assert client.post(f"{base}/remind", headers=admin).status_code == 409
