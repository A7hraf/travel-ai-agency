"""What the platform owner controls and what an ordinary employee sees: the services a company may create,
editing the company's AI, and colleagues' details."""

from sqlalchemy import create_engine, text

from app import migrations
from app.ai.request_tools import PROMPT
from tests.conftest import login, make_company
from tests.test_library import switch

SERVICE = {"name_en": "Desert camp", "name_ar": "مخيم صحراوي", "pricing": "dynamic", "parts": ["activity"],
           "description_en": "A night in the desert.", "description_ar": "ليلة في الصحراء.", "fields": [], "steps": []}


def test_owner_limits_the_services_a_company_creates(client, owner):
    company, admin = make_company(client, owner)
    built_in = len(client.get("/api/services", headers=admin).json())
    r = client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_services": 2})
    assert r.status_code == 200 and r.json()["max_services"] == 2 and r.json()["own_services"] == 0
    first = client.post("/api/services", headers=admin, json=SERVICE)
    assert first.status_code == 201, first.text
    assert client.post("/api/services", headers=admin, json={**SERVICE, "name_en": "Wadi day"}).status_code == 201
    third = client.post("/api/services", headers=admin, json={**SERVICE, "name_en": "Dhow cruise"})
    assert third.status_code == 409 and "2 services of your own" in third.json()["detail"]
    # Built-in services don't count, and a switched-off service frees a place.
    assert len(client.get("/api/services", headers=admin).json()) == built_in + 2
    sid = first.json()["id"]
    assert client.put(f"/api/services/{sid}", headers=admin, json={**SERVICE, "is_active": False}).status_code == 200
    assert client.post("/api/services", headers=admin, json={**SERVICE, "name_en": "Dhow cruise"}).status_code == 201
    back = client.put(f"/api/services/{sid}", headers=admin, json={**SERVICE, "is_active": True})
    assert back.status_code == 409
    # 0 removes the company's own limit.
    client.patch(f"/api/system/companies/{company['id']}", headers=owner, json={"max_services": 0})
    assert client.put(f"/api/services/{sid}", headers=admin, json={**SERVICE, "is_active": True}).status_code == 200


def test_editing_the_ai_is_a_feature_the_owner_gives(client, owner):
    company, admin = make_company(client, owner, ai_training=False)
    assert client.get("/api/training/knowledge", headers=admin).status_code == 403
    assert client.post("/api/training", headers=admin, json={"question": "Q?", "answer": "A."}).status_code == 403
    # The platform owner can always edit it from the company page.
    assert client.get(f"/api/system/companies/{company['id']}/training", headers=owner).status_code == 200
    switch(client, owner, company["id"], ai_training=True)
    assert client.get("/api/training/knowledge", headers=admin).status_code == 200


def test_companies_from_before_keep_editing_their_ai(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, addons JSON)"))
        conn.execute(text("""INSERT INTO companies (id, name, addons) VALUES (1, 'Old', '{"members": {"on": true}}'),
                             (2, 'Off', '{"ai_training": {"on": false}}')"""))
    assert migrations._ai_training_is_new(engine)
    migrations._grant_ai_training(engine)
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT id, addons FROM companies")).all())
    assert '"ai_training": {"on": true}' in rows[1] and '"members"' in rows[1]
    assert '"ai_training": {"on": false}' in rows[2]  # a choice already made stays


def test_employees_see_only_the_names_of_colleagues(client, owner):
    _, admin = make_company(client, owner)
    r = client.post("/api/users", headers=admin, json={"email": "agent@bluesky.com", "full_name": "Agent", "password": "Agent-Pass-2026",
                                                       "role": "ticket_agent"})
    assert r.status_code == 201, r.text
    agent = login(client, "agent@bluesky.com", "Agent-Pass-2026")
    seen = client.get("/api/team", headers=agent).json()
    assert {u["full_name"] for u in seen} >= {"Agent"} and all(u["email"] == "" and u["permissions"] == [] for u in seen)
    full = client.get("/api/team", headers=admin).json()
    assert all(u["email"] for u in full)


def test_the_ai_offers_an_airport_transfer_with_flights():
    assert "airport transfer, offer it once" in PROMPT
