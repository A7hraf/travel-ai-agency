"""The AI advisor: a chat on the company's own figures (never another company's), findings raised by the system,
and the platform owner's advisor."""

from datetime import timedelta

from sqlalchemy import select

from app.ai.llm import LLMResponse, MockTravelLLM, set_llm_client
from app.database import SessionLocal
from app.models import Company, Ticket, utcnow
from app.services.advisor import company_findings
from tests.conftest import login, make_company
from tests.test_library import dubai_request, switch
from tests.test_requests_flow import wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)


def test_company_advisor_and_findings(client, wa, scripted, owner):
    company, admin, fake = wa
    assert client.get("/api/advisor", headers=admin).status_code == 403
    switch(client, owner, company["id"], advisor=True)
    other, other_admin = make_company(client, owner, name="Secret Rival Travel", admin_email="admin@rival.com")
    switch(client, owner, other["id"], advisor=True)

    for i in range(3):
        dubai_request(client, admin, scripted, mid=f"wamid.adv{i}")
    set_llm_client(MockTravelLLM())
    r = client.post("/api/advisor", headers=admin, json={"text": "What should I do first today?"}).json()
    assert [m["role"] for m in r] == ["user", "assistant"] and "3 requests are waiting for your team" in r[1]["content"]

    llm = scripted([LLMResponse("Answer the 3 Dubai hotel requests first.")])
    r = client.post("/api/advisor", headers=admin, json={"text": "ما أولوياتي؟"}).json()
    assert r[1]["content"] == "Answer the 3 Dubai hotel requests first."
    sent = llm.calls[0]
    figures = [m["content"] for m in sent if m["role"] == "system" and m["content"].startswith("FIGURES")][0]
    assert "Blue Sky Travel" in figures and "Secret Rival" not in figures
    assert sent[-1] == {"role": "user", "content": "ما أولوياتي؟"}
    assert any(m["content"] == "What should I do first today?" for m in sent)  # the recent chat goes along
    assert len(client.get("/api/advisor", headers=admin).json()) == 4
    assert client.get("/api/advisor", headers=other_admin).json() == []

    # Requests waiting more than a day: a finding, raised once per week.
    with SessionLocal() as db:
        for t in db.scalars(select(Ticket).where(Ticket.company_id == company["id"])).all():
            t.last_client_at = utcnow() - timedelta(days=2)
        db.commit()
        c = db.get(Company, company["id"])
        assert company_findings(db, c) == 1
        assert company_findings(db, c) == 0
        db.commit()
    notes = [m for m in client.get("/api/advisor", headers=admin).json() if m["role"] == "note"]
    assert len(notes) == 1 and "waited more than a day" in notes[0]["content"]
    assert client.get("/api/advisor", headers=other_admin).json() == []

    # Each person's chat is their own: a colleague sees the shared findings, not the admin's questions.
    r = client.post("/api/users", headers=admin, json={"email": "analyst@bluesky.com", "full_name": "Analyst",
                                                       "password": "Analyst-Pass-2026", "role": "ticket_agent",
                                                       "permissions": ["reports.view", "tickets.view"]})
    assert r.status_code == 201, r.text
    analyst = login(client, "analyst@bluesky.com", "Analyst-Pass-2026")
    seen = client.get("/api/advisor", headers=analyst).json()
    assert [m["role"] for m in seen] == ["note"]
    client.post("/api/advisor", headers=analyst, json={"text": "How many requests this week?"})
    assert not any("How many requests" in m["content"] for m in client.get("/api/advisor", headers=admin).json())
    # Clearing clears only your own chat; the findings stay for everyone.
    assert client.delete("/api/advisor", headers=admin).status_code == 204
    assert [m["role"] for m in client.get("/api/advisor", headers=admin).json()] == ["note"]
    assert any("How many requests" in m["content"] for m in client.get("/api/advisor", headers=analyst).json())


def test_platform_advisor(client, owner, company_a):
    company, admin = company_a
    assert client.get("/api/system/advisor", headers=admin).status_code == 403
    set_llm_client(MockTravelLLM())
    r = client.post("/api/system/advisor", headers=owner, json={"text": "Which agencies need me?"}).json()
    assert r[1]["role"] == "assistant" and "Agencies:" in r[1]["content"] and "Blue Sky Travel" in r[1]["content"]
    found = client.post("/api/system/advisor/check", headers=owner).json()
    assert any(m["role"] == "note" and "no chats in 30 days" in m["content"] for m in found)
    again = client.post("/api/system/advisor/check", headers=owner).json()
    assert len([m for m in again if m["role"] == "note"]) == len([m for m in found if m["role"] == "note"])
    assert client.get("/api/advisor", headers=admin).status_code == 403  # the company's advisor is a separate feature
