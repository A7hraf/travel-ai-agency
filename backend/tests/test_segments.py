"""Learning from the data: client groups for a company (granted by the platform owner, with levels) and the market
for the platform owner only. Nobody reaches another company's clients or the cross-company figures."""

import json
from datetime import date, timedelta
from decimal import Decimal

from app.database import SessionLocal
from app.models import Customer, Ticket, TicketStatus as T, TripOption
from tests.conftest import make_company

TODAY = date.today()


def _ago(days: int):
    from datetime import datetime, timezone
    return datetime.now(timezone.utc) - timedelta(days=days)


def seed(company_id: int, tag: str) -> dict[str, int]:
    """Clients with a history: a VIP, one travelling soon, one lost after a quotation, one quiet for a year."""
    ids = {}
    with SessionLocal() as db:
        def client(name, created=400):
            c = Customer(company_id=company_id, name=f"{name} {tag}", phone="+96899000000", whatsapp_id=f"9689{abs(hash(name + tag)) % 10**7}",
                         created_at=_ago(created))
            db.add(c)
            db.flush()
            ids[name] = c.id
            return c

        def trip(c, status, created, depart, price="500", dest="Tbilisi", provider=None, reason=None):
            t = Ticket(company_id=company_id, customer_id=c.id, reference=f"R{abs(hash((c.id, created, depart))) % 10**8}",
                       package_title="Trip", lead_traveler_name=c.name, contact_phone="+96899000000", destination=dest,
                       departure_date=depart.isoformat(), adults=2, total_price=Decimal(price), currency="OMR", status=status,
                       created_at=_ago(created), cancel_info={"reason": reason} if reason else None)
            db.add(t)
            db.flush()
            if provider:
                db.add(TripOption(company_id=company_id, ticket_id=t.id, category="hotel", title="Room", provider=provider,
                                  price=Decimal(price), cost_price=Decimal(price) * Decimal("0.8"), added_by="staff", chosen=True))
            return t

        vip = client("Vip")
        for n in range(3):
            trip(vip, T.COMPLETED, 100 + n * 100, TODAY - timedelta(days=90 + n * 100), "4000", provider="Rooms Hotels")
        soon = client("Soon")
        trip(soon, T.CONFIRMED, 20, TODAY + timedelta(days=10), "800", dest="Baku", provider="Rooms Hotels")
        lost = client("Lost")
        trip(lost, T.REJECTED, 30, TODAY + timedelta(days=60), "900", reason="too expensive")
        quiet = client("Quiet", created=900)
        trip(quiet, T.COMPLETED, 500, TODAY - timedelta(days=470), "300")
        db.commit()
    return ids


def grant(client, owner, company_id, levels=None, broadcasts=True):
    body = {"client_segments": {"on": True, "levels": levels or []}}
    if broadcasts:
        body["broadcasts"] = {"on": True}
    r = client.put(f"/api/system/companies/{company_id}/features", headers=owner, json=body)
    assert r.status_code == 200, r.text


def groups(data) -> dict[str, list[str]]:
    return {s["key"]: [c["name"] for c in s["clients"]] for s in data["segments"]}


def test_client_groups_need_the_feature_and_stay_in_the_company(client, owner):
    a, ha = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    b, hb = make_company(client, owner, "Beta Travel", "b@beta.example")
    seed(a["id"], "A")
    seed(b["id"], "B")
    assert client.get("/api/segments", headers=ha).status_code == 403  # not granted yet
    grant(client, owner, a["id"])
    r = client.get("/api/segments", headers=ha)
    assert r.status_code == 200, r.text
    g = groups(r.json())
    assert "Vip A" in g["vip"] and "Soon A" in g["upcoming"] and "Lost A" in g["lost_quote"]
    assert "Quiet A" in g["dormant"]
    assert all(not name.endswith(" B") for names in g.values() for name in names)  # never the other company's clients
    lost = next(c for s in r.json()["segments"] if s["key"] == "lost_quote" for c in s["clients"])
    assert lost["why"] == "too expensive"
    assert client.get("/api/segments", headers=hb).status_code == 403


def test_levels_limit_what_a_company_gets(client, owner):
    a, ha = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    seed(a["id"], "A")
    grant(client, owner, a["id"], levels=["segments"])
    data = client.get("/api/segments", headers=ha).json()
    assert "due_again" not in groups(data) and data["can_target"] is False
    # No targeting level: no message to a group.
    r = client.post("/api/broadcasts/preview", headers=ha, json={"segment": "vip"})
    assert r.status_code == 403
    grant(client, owner, a["id"], levels=["segments", "targeting"])
    r = client.post("/api/broadcasts/preview", headers=ha, json={"segment": "vip"})
    assert r.status_code == 200 and r.json()["count"] == 1, r.text
    assert client.post("/api/broadcasts/preview", headers=ha, json={"segment": "nonsense"}).status_code == 422
    # A level that belongs to another feature is refused.
    bad = client.put(f"/api/system/companies/{a['id']}/features", headers=owner,
                     json={"client_segments": {"on": True, "levels": ["finance"]}})
    assert bad.status_code == 422


def test_the_market_is_for_the_platform_owner_only_and_has_no_client_details(client, owner):
    a, ha = make_company(client, owner, "Alpha Travel", "a@alpha.example")
    b, _ = make_company(client, owner, "Beta Travel", "b@beta.example")
    seed(a["id"], "A")
    seed(b["id"], "B")
    grant(client, owner, a["id"])
    assert client.get("/api/system/market", headers=ha).status_code == 403
    r = client.get("/api/system/market", headers=owner)
    assert r.status_code == 200, r.text
    data = r.json()
    rooms = next(p for p in data["partners"] if p["provider"] == "Rooms Hotels")
    assert rooms["companies"] == 2 and "negotiate" in rooms["why"]
    assert data["destinations"][0]["destination"] == "Tbilisi"
    assert any(x["reason"] == "too expensive" for x in data["lost_reasons"])
    text = json.dumps(data)
    assert "Vip A" not in text and "+96899000000" not in text  # totals only
