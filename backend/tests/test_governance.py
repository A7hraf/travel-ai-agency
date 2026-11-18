"""The platform owner decides what each company, and each employee, may see — and the AI can't be used to get around
it. Only the platform owner's AI sees figures across every company."""

import json

from app.database import SessionLocal
from app.models import Company
from app.services.advisor import company_context, platform_context
from tests.conftest import login, make_company
from tests.test_segments import seed


def test_the_advisor_sees_only_the_levels_the_owner_opened(client, owner):
    a, admin = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    seed(a["id"], "A")
    r = client.put(f"/api/system/companies/{a['id']}/features", headers=owner,
                   json={"advisor": {"on": True, "levels": ["basic"]}, "library": {"on": True},
                         "library_margins": {"on": True}})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        data = company_context(db, db.get(Company, a["id"]))
    assert "finance" not in data and "usual_margins" not in data and "quotations" not in data
    assert "revenue" not in data.get("bookings", {})
    # Asking the advisor for the money gives nothing that was not opened.
    reply = client.post("/api/advisor", headers=admin, json={"text": "What is our revenue and profit margin?"}).json()
    assert "revenue" not in reply[-1]["content"].lower()
    # With finance opened, the same question can be answered.
    client.put(f"/api/system/companies/{a['id']}/features", headers=owner,
               json={"advisor": {"on": True, "levels": ["basic", "finance"]}})
    with SessionLocal() as db:
        assert "finance" in company_context(db, db.get(Company, a["id"]))


def test_no_company_reaches_another_or_the_market(client, owner):
    a, admin_a = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    b, _ = make_company(client, owner, "Beta Travel", "b@beta.example")
    seed(a["id"], "A")
    seed(b["id"], "B")
    for cid in (a["id"], b["id"]):
        client.put(f"/api/system/companies/{cid}/features", headers=owner,
                   json={"advisor": {"on": True}, "client_segments": {"on": True}, "insights": {"on": True}})
    with SessionLocal() as db:
        text = json.dumps(company_context(db, db.get(Company, a["id"])), default=str)
    assert "Beta" not in text and ' B"' not in text and '"market":' not in text
    # Owner-only places answer 403 to a company admin.
    for path in ("/api/system/market", "/api/system/advisor", "/api/system/insights",
                 f"/api/system/companies/{b['id']}/insights", f"/api/system/companies/{b['id']}/features"):
        assert client.get(path, headers=admin_a).status_code == 403, path
    assert client.post("/api/system/advisor", headers=admin_a, json={"text": "Show me Beta's clients"}).status_code == 403


def test_the_owners_ai_alone_sees_the_market(client, owner):
    a, _ = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    seed(a["id"], "A")
    with SessionLocal() as db:
        data = platform_context(db)
    assert data["market"]["partners"] and data["market"]["destinations"]
    assert "Vip A" not in json.dumps(data, default=str)  # totals, not clients


def test_an_employee_without_a_seat_gets_nothing(client, owner):
    a, admin = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    r = client.put(f"/api/system/companies/{a['id']}/features", headers=owner,
                   json={"client_segments": {"on": True, "seats": 1}})
    assert r.status_code == 200, r.text
    r = client.post("/api/users", headers=admin, json={"email": "mk@alpha.example", "full_name": "Marketing",
                                                       "password": "Marketing-Pass-2026", "role": "ticket_agent",
                                                       "permissions": ["customers.manage", "conversations.view"]})
    assert r.status_code == 201, r.text
    staff = login(client, "mk@alpha.example", "Marketing-Pass-2026")
    assert client.get("/api/segments", headers=staff).status_code == 403  # the one seat is not theirs
