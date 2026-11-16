"""Business trips after the first quotation: the client's changes go to the vendor as a brief, the payment plan
with dates (set by the vendor, tracked on every dashboard, with reminders), the client's rating, sharing the
client's name with a vendor only when the travel company chooses, and each party's figures."""

import json
from datetime import timedelta

from app.b2b import FEATURES
from app.database import SessionLocal
from app.services.b2b_flow import payment_reminders
from app.timeutil import local_today
from tests.conftest import make_company
from tests.test_partners import add_login, add_partner, switch_on
from tests.test_trip_requests import REQUEST, flight, hotel


def setup_trip(client, owner, *, share=False):
    company, admin = make_company(client, owner)
    switch_on(client, owner, company["id"], max_vendors=2, features=list(FEATURES))
    cl = add_partner(client, admin, name="Oman Oil Co", features=["client.requests", "client.reports", "client.payments"]).json()
    _, cl_h = add_login(client, admin, cl["id"], email="hr@oil.example")
    v = add_partner(client, admin, kind="vendor", name="Gulf Vendor",
                    features=["vendor.requests", "vendor.quotes", "vendor.payments", "vendor.quote_design", "vendor.history"]).json()
    _, v_h = add_login(client, admin, v["id"], email="ops@gulfvendor.example")
    rid = client.post("/api/partner/requests", headers=cl_h, json=REQUEST).json()["id"]
    client.post(f"/api/b2b/requests/{rid}/vendor", headers=admin, json={"vendor_id": v["id"], "brief": "2 pax", "share_client": share})
    client.post(f"/api/partner/jobs/{rid}/accept", headers=v_h)
    for body in (flight("WY 601", "400"), flight("EK 863", "450"), hotel("Hilton Creek", "300")):
        client.post(f"/api/partner/jobs/{rid}/options", headers=v_h, json=body)
    client.post(f"/api/partner/jobs/{rid}/submit", headers=v_h)
    staff = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()
    ids = {o["title"]: o["id"] for o in staff["options"]}
    client.put(f"/api/b2b/requests/{rid}/markup", headers=admin, json={"markup_percent": 20})
    client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": list(ids.values())})
    return dict(company=company, admin=admin, cl_h=cl_h, v_h=v_h, rid=rid, ids=ids, client=cl, vendor=v)


def test_client_changes_reach_the_vendor_as_a_brief(client, owner):
    s = setup_trip(client, owner)
    rid, cl_h, v_h, admin = s["rid"], s["cl_h"], s["v_h"], s["admin"]
    r = client.post(f"/api/partner/requests/{rid}/changes", headers=cl_h, json={"note": "Morning flights please, and a hotel near DIFC"})
    assert r.status_code == 200 and r.json()["status"] == "with_vendor"
    job = client.get(f"/api/partner/jobs/{rid}", headers=v_h).json()
    brief = job["messages"][-1]["text"]
    assert "Morning flights" in brief and "Oman Oil" not in json.dumps(job)
    assert [st["action"] for st in r.json()["steps"]][-1] == "changes_requested"
    assert "b2b_changes" in [n["kind"] for n in client.get("/api/notifications", headers=admin).json()["items"]]
    # Only while the client is choosing.
    assert client.post(f"/api/partner/requests/{rid}/changes", headers=cl_h, json={"note": "again"}).status_code == 409


def test_sharing_the_client_name_is_the_travel_companys_choice(client, owner):
    s = setup_trip(client, owner, share=True)
    job = client.get(f"/api/partner/jobs/{s['rid']}", headers=s["v_h"]).json()
    assert job["client_name"] == "Oman Oil Co" and "secret note" not in json.dumps(job)


def test_payment_plan_on_every_dashboard_with_reminders(client, owner):
    s = setup_trip(client, owner)
    rid, cl_h, v_h, admin, ids = s["rid"], s["cl_h"], s["v_h"], s["admin"], s["ids"]
    today = local_today()
    plan = {"steps": [{"label": "Deposit", "percent": 40, "due_date": (today + timedelta(days=2)).isoformat()},
                      {"label": "Balance", "percent": 60, "due_date": (today + timedelta(days=20)).isoformat()}]}
    assert client.put(f"/api/partner/jobs/{rid}/payment-plan", headers=v_h,
                      json={"steps": [{"label": "All", "percent": 90}]}).status_code == 422  # must be 100%
    assert client.put(f"/api/partner/jobs/{rid}/payment-plan", headers=v_h, json=plan).status_code == 200
    client.post(f"/api/partner/requests/{rid}/choose", headers=cl_h, json={"option_ids": [ids["WY 601"], ids["Hilton Creek"]]})
    client.post(f"/api/b2b/requests/{rid}/approve", headers=admin)
    # Each side sees its own amounts: the client 40% of 840, the vendor 40% of 700.
    mine = client.get(f"/api/partner/requests/{rid}", headers=cl_h).json()["payment_plan"]
    job = client.get(f"/api/partner/jobs/{rid}", headers=v_h).json()["payment_plan"]
    staff = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()["payment_plan"]
    assert mine[0]["amount"] == "336.000" and mine[0]["vendor_amount"] is None
    assert job[0]["amount"] == "280.000" and staff[0]["vendor_amount"] == "280.000" and staff[0]["amount"] == "336.000"
    # A reminder before the deposit date: in the client's thread, and the admins hear; once in a while.
    with SessionLocal() as db:
        assert payment_reminders(db, today) == 1
        assert payment_reminders(db, today) == 0
    mine = client.get(f"/api/partner/requests/{rid}", headers=cl_h).json()
    assert "Deposit" in mine["messages"][-1]["text"] and "336.000" in mine["messages"][-1]["text"]
    kinds = [n["kind"] for n in client.get("/api/notifications", headers=admin).json()["items"]]
    assert "b2b_payment_due" in kinds
    # The travel company writes the payments down; the plan can't change after that.
    step = staff[0]["id"]
    r = client.post(f"/api/b2b/requests/{rid}/payments/{step}", headers=admin, json={"side": "client", "reference": "TRX-1"}).json()
    assert r["payment_plan"][0]["paid"] is True and r["payment_plan"][0]["vendor_paid"] is False
    client.post(f"/api/b2b/requests/{rid}/payments/{step}", headers=admin, json={"side": "vendor"})
    assert client.get(f"/api/partner/jobs/{rid}", headers=v_h).json()["payment_plan"][0]["paid"] is True
    assert client.put(f"/api/b2b/requests/{rid}/payment-plan", headers=admin, json=plan).status_code == 409
    # A client can't write payments; another vendor can't see this plan.
    assert client.post(f"/api/b2b/requests/{rid}/payments/{step}", headers=cl_h, json={"side": "client"}).status_code == 403


def test_rating_figures_and_vendor_quotation_design(client, owner):
    s = setup_trip(client, owner)
    rid, cl_h, v_h, admin, ids = s["rid"], s["cl_h"], s["v_h"], s["admin"], s["ids"]
    design = {"intro": "Gulf Vendor offer", "terms": "Non-refundable after ticketing", "valid_days": 3, "payment_terms": "40/60"}
    assert client.put("/api/partner/quote-settings", headers=v_h, json=design).status_code == 200
    assert client.get(f"/api/b2b/requests/{rid}", headers=admin).json()["vendor_quote"]["terms"] == "Non-refundable after ticketing"
    assert client.get("/api/partner/quote-settings", headers=cl_h).status_code == 403
    client.post(f"/api/partner/requests/{rid}/choose", headers=cl_h, json={"option_ids": [ids["WY 601"], ids["Hilton Creek"]]})
    assert client.post(f"/api/partner/requests/{rid}/rating", headers=cl_h, json={"rating": 5}).status_code == 409  # not booked yet
    client.post(f"/api/b2b/requests/{rid}/approve", headers=admin)
    client.post(f"/api/partner/jobs/{rid}/booked", headers=v_h, json={"booking_reference": "PNR1"})
    assert client.post(f"/api/partner/requests/{rid}/rating", headers=cl_h, json={"rating": 5, "comment": "Smooth"}).json()["client_rating"] == 5
    stats = client.get("/api/b2b/stats", headers=admin).json()
    assert stats["booked"] == 1 and stats["sales"] == 840 and stats["earned"] == 140
    assert stats["clients"][0]["name"] == "Oman Oil Co" and stats["vendors"][0]["rating"] == 5
    assert stats["best_rated_vendor"]["name"] == "Gulf Vendor" and stats["trips"][0]["margin"] == 140
    mine = client.get("/api/partner/stats", headers=cl_h).json()
    assert mine["kind"] == "client" and mine["amount"] == 840 and mine["by_status"] == {"booked": 1}
    job = client.get("/api/partner/stats", headers=v_h).json()
    assert job["amount"] == 700 and job["rating"] == 5 and "Oman Oil" not in json.dumps(job)
    # Another company sees none of it.
    _, other = make_company(client, owner, name="Other Travel", admin_email="admin@other.com")
    assert client.get(f"/api/b2b/requests/{rid}", headers=other).status_code in (403, 404)
