"""Business trip requests: client → travel company → vendor → client choice → approval → booking,
and above all what each party may and may not see."""

import json

import pytest

from app.ai.llm import LLMResponse, ToolCall
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, login, make_company
from tests.test_partners import ALL, add_login, add_partner, switch_on
from tests.test_whatsapp import HOOK, connect_whatsapp, meta_stub, wa_payload  # noqa: F401 (fixture)

REQUEST = {
    "purpose": "Board meeting", "origin": "Muscat", "destination": "Dubai", "depart_date": "2030-03-10",
    "return_date": "2030-03-12", "travellers": 2, "traveller_names": "Salim Al Harthy\nMaryam Al Lawati",
    "needs": ["flight", "hotel"], "budget": "900 OMR", "notes": "Client secret note: CEO travelling",
}


@pytest.fixture
def setup(client, owner):
    """A travel company with a client (and its login), two vendors (and their logins)."""
    company, admin = make_company(client, owner)
    switch_on(client, owner, company["id"], max_vendors=3)
    cl = add_partner(client, admin, name="Oman Oil Co", features=["client.requests", "client.whatsapp"]).json()
    _, client_login = add_login(client, admin, cl["id"], email="hr@oil.example")
    v1 = add_partner(client, admin, kind="vendor", name="Gulf Vendor", features=["vendor.requests", "vendor.quotes"]).json()
    _, v1_login = add_login(client, admin, v1["id"], email="ops@gulfvendor.example")
    v2 = add_partner(client, admin, kind="vendor", name="Other Vendor", features=["vendor.requests", "vendor.quotes"]).json()
    _, v2_login = add_login(client, admin, v2["id"], email="ops@othervendor.example")
    return dict(company=company, admin=admin, client=cl, client_login=client_login, v1=v1, v1_login=v1_login,
                v2=v2, v2_login=v2_login)


def flight(title, cost, **extra):
    return {"category": "flight", "title": title, "provider": "Oman Air", "cost_price": cost, **extra}


def hotel(title, cost, **extra):
    return {"category": "hotel", "title": title, "provider": "Hilton", "cost_price": cost, **extra}


def test_full_journey_and_what_each_party_sees(client, setup):
    s = setup
    admin, cl_h, v1_h = s["admin"], s["client_login"], s["v1_login"]
    r = client.post("/api/partner/requests", headers=cl_h, json=REQUEST)
    assert r.status_code == 201, r.text
    rid, ref = r.json()["id"], r.json()["reference"]
    assert ref.startswith("BR-") and r.json()["status"] == "new"

    # Staff forward it to the vendor with a brief.
    r = client.post(f"/api/b2b/requests/{rid}/vendor", headers=admin, json={"vendor_id": s["v1"]["id"], "brief": "2 pax business class"})
    assert r.json()["status"] == "with_vendor"

    # The vendor sees the job, but not who the client is, its notes, budget or the traveller names.
    job = client.get(f"/api/partner/jobs/{rid}", headers=v1_h).json()
    blob = json.dumps(job)
    for secret in ("Oman Oil", "secret note", "900 OMR", "Salim", "Maryam", "hr@oil"):
        assert secret not in blob, secret
    assert job["brief"] == "2 pax business class" and job["traveller_names"] is None and job["purpose"] is None
    assert "Board meeting" not in blob
    assert job["destination"] == "Dubai" and job["travellers"] == 2
    assert client.get("/api/partner/jobs", headers=s["v2_login"]).json() == []
    assert client.get(f"/api/partner/jobs/{rid}", headers=s["v2_login"]).status_code == 404

    # The vendor proposes options with its own prices, then submits.
    for body in (flight("WY 601 Business", "400"), flight("EK 863 Business", "450"), hotel("Hilton Creek", "300")):
        assert client.post(f"/api/partner/jobs/{rid}/options", headers=v1_h, json=body).status_code == 200
    r = client.post(f"/api/partner/jobs/{rid}/options", headers=v1_h, json={"category": "food", "title": "Dinner", "cost_price": 1})
    assert r.status_code == 422  # the request did not ask for food
    assert client.post(f"/api/partner/jobs/{rid}/submit", headers=v1_h).json()["status"] == "options_ready"

    # Staff set a 20 % margin and send the choices; one option gets its own price.
    staff = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()
    assert staff["client_name"] == "Oman Oil Co" and staff["vendor_name"] == "Gulf Vendor"
    client.put(f"/api/b2b/requests/{rid}/markup", headers=admin, json={"markup_percent": 20})
    ids = {o["title"]: o["id"] for o in staff["options"]}
    hotel_opt = next(o for o in staff["options"] if o["category"] == "hotel")
    client.put(f"/api/b2b/requests/{rid}/options/{hotel_opt['id']}", headers=admin,
               json={**hotel("Hilton Creek", "300"), "price": "390"})
    r = client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": list(ids.values())})
    assert r.json()["status"] == "with_client"

    # The client sees its prices, never the vendor, the costs or the margin.
    mine = client.get(f"/api/partner/requests/{rid}", headers=cl_h).json()
    blob = json.dumps(mine)
    for secret in ("Gulf Vendor", "cost_price", "markup", "vendor", "2 pax business class"):
        assert secret not in blob, secret
    prices = {o["title"]: o["price"] for o in mine["options"]}
    assert prices == {"WY 601 Business": "480.000", "EK 863 Business": "540.000", "Hilton Creek": "390.000"}

    # One choice per part.
    r = client.post(f"/api/partner/requests/{rid}/choose", headers=cl_h, json={"option_ids": [ids["WY 601 Business"]]})
    assert r.status_code == 422
    r = client.post(f"/api/partner/requests/{rid}/choose", headers=cl_h,
                    json={"option_ids": [ids["WY 601 Business"], ids["EK 863 Business"], ids["Hilton Creek"]]})
    assert r.status_code == 422
    r = client.post(f"/api/partner/requests/{rid}/choose", headers=cl_h,
                    json={"option_ids": [ids["WY 601 Business"], ids["Hilton Creek"]]})
    assert r.json()["status"] == "chosen" and r.json()["total_price"] == "870.000"

    # Before approval the vendor still has no names and no choice.
    job = client.get(f"/api/partner/jobs/{rid}", headers=v1_h).json()
    assert job["traveller_names"] is None and not any(o["chosen"] for o in job["options"])

    r = client.post(f"/api/b2b/requests/{rid}/approve", headers=admin).json()
    assert r["status"] == "approved" and r["total_price"] == "870.000" and r["total_cost"] == "700.000"
    job = client.get(f"/api/partner/jobs/{rid}", headers=v1_h).json()
    assert job["traveller_names"] == REQUEST["traveller_names"] and job["total_cost"] == "700.000"
    assert {o["title"] for o in job["options"] if o["chosen"]} == {"WY 601 Business", "Hilton Creek"}
    assert "Oman Oil" not in json.dumps(job)

    # The client can't cancel any more; the vendor books.
    assert client.post(f"/api/partner/requests/{rid}/cancel", headers=cl_h, json={}).status_code == 409
    r = client.post(f"/api/partner/jobs/{rid}/booked", headers=v1_h, json={"booking_reference": "PNR XK7Q2M / HIL-9921"})
    assert r.json()["status"] == "booked"
    mine = client.get(f"/api/partner/requests/{rid}", headers=cl_h).json()
    assert mine["booking_reference"] == "PNR XK7Q2M / HIL-9921"
    assert [st["action"] for st in mine["steps"]] == ["created", "sent_to_client", "chosen", "approved", "booked"]
    assert client.post(f"/api/b2b/requests/{rid}/complete", headers=admin).json()["status"] == "completed"
    staff = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()
    assert [e["action"] for e in staff["events"]][:3] == ["created", "assigned", "accepted"]


def test_two_threads_never_mix(client, setup):
    s = setup
    rid = client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).json()["id"]
    client.post(f"/api/b2b/requests/{rid}/vendor", headers=s["admin"], json={"vendor_id": s["v1"]["id"]})
    client.post(f"/api/partner/requests/{rid}/messages", headers=s["client_login"], json={"text": "Window seats please"})
    client.post(f"/api/partner/jobs/{rid}/messages", headers=s["v1_login"], json={"text": "Fares rise tomorrow"})
    client.post(f"/api/b2b/requests/{rid}/messages", headers=s["admin"], json={"thread": "vendor", "text": "Hold 2 seats"})
    assert client.post(f"/api/b2b/requests/{rid}/messages", headers=s["admin"], json={"text": "No thread"}).status_code == 422
    mine = [m["text"] for m in client.get(f"/api/partner/requests/{rid}", headers=s["client_login"]).json()["messages"]]
    job = [m["text"] for m in client.get(f"/api/partner/jobs/{rid}", headers=s["v1_login"]).json()["messages"]]
    staff = [m["text"] for m in client.get(f"/api/b2b/requests/{rid}", headers=s["admin"]).json()["messages"]]
    assert mine == ["Window seats please"]
    assert job == ["Fares rise tomorrow", "Hold 2 seats"]
    assert staff == ["Window seats please", "Fares rise tomorrow", "Hold 2 seats"]


def test_other_clients_vendors_and_companies_see_nothing(client, owner, setup):
    s = setup
    rid = client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).json()["id"]
    other = add_partner(client, s["admin"], name="Other Client", features=["client.requests"]).json()
    _, other_h = add_login(client, s["admin"], other["id"], email="x@other.example")
    assert client.get("/api/partner/requests", headers=other_h).json() == []
    for method, url in (("get", f"/api/partner/requests/{rid}"), ("post", f"/api/partner/requests/{rid}/cancel"),
                        ("post", f"/api/partner/requests/{rid}/messages")):
        r = getattr(client, method)(url, headers=other_h, **({"json": {"text": "hi"}} if method == "post" else {}))
        assert r.status_code == 404, url
    # A vendor login can't use the client portal and the other way round.
    assert client.get("/api/partner/requests", headers=s["v1_login"]).status_code == 403
    assert client.get("/api/partner/jobs", headers=s["client_login"]).status_code == 403
    # Another travel company.
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    switch_on(client, owner, b["id"])
    assert client.get("/api/b2b/requests", headers=admin_b).json() == []
    assert client.get(f"/api/b2b/requests/{rid}", headers=admin_b).status_code == 404
    assert client.post(f"/api/b2b/requests/{rid}/approve", headers=admin_b).status_code == 404
    # Company B can't forward its request to company A's vendor, nor create one for A's client.
    rb = client.post("/api/b2b/requests", headers=admin_b, json={**REQUEST, "client_id": s["client"]["id"]})
    assert rb.status_code == 404
    # Logins of the client and the vendor never reach the staff side.
    for h in (s["client_login"], s["v1_login"]):
        assert client.get("/api/b2b/requests", headers=h).status_code == 403
        assert client.get(f"/api/b2b/requests/{rid}", headers=h).status_code == 403


def test_vendor_decline_and_reassign(client, setup):
    s = setup
    rid = client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).json()["id"]
    client.post(f"/api/b2b/requests/{rid}/vendor", headers=s["admin"], json={"vendor_id": s["v1"]["id"]})
    client.post(f"/api/partner/jobs/{rid}/options", headers=s["v1_login"], json=flight("WY 601", "400"))
    assert client.post(f"/api/partner/jobs/{rid}/decline", headers=s["v1_login"], json={"reason": "No seats"}).status_code == 204
    assert client.get(f"/api/partner/jobs/{rid}", headers=s["v1_login"]).status_code == 404
    staff = client.get(f"/api/b2b/requests/{rid}", headers=s["admin"]).json()
    assert staff["vendor_id"] is None and staff["status"] == "options_ready" and len(staff["options"]) == 1
    # The next vendor never sees the first vendor's options or prices.
    client.post(f"/api/b2b/requests/{rid}/vendor", headers=s["admin"], json={"vendor_id": s["v2"]["id"]})
    job = client.get(f"/api/partner/jobs/{rid}", headers=s["v2_login"]).json()
    assert job["options"] == [] and "400" not in json.dumps(job)
    v2_opt = client.post(f"/api/partner/jobs/{rid}/options", headers=s["v2_login"], json=flight("EK 863", "380")).json()["options"][0]
    # A vendor can't delete an option that isn't its own.
    first = staff["options"][0]["id"]
    assert client.delete(f"/api/partner/jobs/{rid}/options/{first}", headers=s["v2_login"]).status_code == 404
    assert client.delete(f"/api/partner/jobs/{rid}/options/{v2_opt['id']}", headers=s["v2_login"]).status_code == 200


def test_rules_and_features(client, owner, setup):
    s = setup
    admin = s["admin"]
    rid = client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).json()["id"]
    # Staff can add options themselves (no vendor); at most 3 per part go to the client.
    ids = []
    for i in range(4):
        r = client.post(f"/api/b2b/requests/{rid}/options", headers=admin, json=flight(f"Flight {i}", "100"))
        ids.append(r.json()["options"][-1]["id"])
    assert client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": ids}).status_code == 422
    no_price = client.post(f"/api/b2b/requests/{rid}/options", headers=admin,
                           json={"category": "hotel", "title": "Hotel X"}).json()["options"]
    hid = next(o["id"] for o in no_price if o["title"] == "Hotel X")
    assert client.post(f"/api/b2b/requests/{rid}/send", headers=admin, json={"option_ids": [hid]}).status_code == 422
    assert client.post(f"/api/b2b/requests/{rid}/approve", headers=admin).status_code == 409  # nothing chosen
    # Bad request data.
    bad = {**REQUEST, "return_date": "2030-03-01"}
    assert client.post("/api/partner/requests", headers=s["client_login"], json=bad).status_code == 422
    assert client.post("/api/partner/requests", headers=s["client_login"], json={**REQUEST, "needs": ["spa"]}).status_code == 422
    # Features: a client without "requests" can't create; a vendor without "quotes" can't propose.
    client.patch(f"/api/partners/{s['client']['id']}", headers=admin, json={"features": ["client.whatsapp"]})
    assert client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).status_code == 403
    assert client.get("/api/partner/requests", headers=s["client_login"]).status_code == 403
    client.patch(f"/api/partners/{s['client']['id']}", headers=admin, json={"features": ["client.history"]})
    assert client.get("/api/partner/requests", headers=s["client_login"]).status_code == 200  # read only
    assert client.post("/api/partner/requests", headers=s["client_login"], json=REQUEST).status_code == 403
    client.patch(f"/api/partners/{s['v1']['id']}", headers=admin, json={"features": ["vendor.requests"]})
    client.post(f"/api/b2b/requests/{rid}/vendor", headers=admin, json={"vendor_id": s["v1"]["id"]})
    r = client.post(f"/api/partner/jobs/{rid}/options", headers=s["v1_login"], json=flight("X", "1"))
    assert r.status_code == 403
    # A vendor without "requests" can't be chosen.
    client.patch(f"/api/partners/{s['v2']['id']}", headers=admin, json={"features": []})
    assert client.post(f"/api/b2b/requests/{rid}/vendor", headers=admin, json={"vendor_id": s["v2"]["id"]}).status_code == 409
    # Staff need the permission.
    r = client.post("/api/users", headers=admin, json={"email": "s@bluesky.com", "full_name": "S", "password": "Support123!", "role": "support"})
    support = login(client, "s@bluesky.com", "Support123!")
    assert client.get("/api/b2b/requests", headers=support).status_code == 403
    client.patch(f"/api/users/{r.json()['id']}", headers=admin, json={"permissions": ["requests.manage"]})
    assert client.get("/api/b2b/requests", headers=support).status_code == 200
    # A client with requests can't be deleted (its history is kept); pausing works.
    assert client.delete(f"/api/partners/{s['client']['id']}", headers=admin).status_code == 409


def test_whatsapp_request_choice_and_updates(client, setup, scripted):
    s = setup
    connect_whatsapp(client, s["admin"])
    client.patch(f"/api/partners/{s['client']['id']}", headers=s["admin"], json={"whatsapp_numbers": ["+96891234567"]})
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    create = ToolCall("c1", "create_business_trip_request", {
        "destination": "Dubai", "travellers": 1, "needs": ["flight"], "depart_date": "2030-05-01",
        "traveller_names": "Salim Al Harthy"})
    llm = scripted([LLMResponse(None, [create]), LLMResponse("Sent! Your reference is above.")])
    client.post(HOOK, json=wa_payload("PNID-A", "96891234567", "Flight to Dubai for Salim on 1 May", "wamid.1"))
    assert "Oman Oil Co" in llm.calls[0][0]["content"] and "BUSINESS CLIENT" in llm.calls[0][0]["content"]
    rows = client.get("/api/b2b/requests", headers=s["admin"]).json()
    assert len(rows) == 1 and rows[0]["source"] == "whatsapp" and rows[0]["client_name"] == "Oman Oil Co"
    rid = rows[0]["id"]
    # Staff send two flight options: the client gets them, numbered, in the same WhatsApp chat.
    for body in (flight("WY 601", "200", price="240"), flight("EK 863", "220", price="260")):
        client.post(f"/api/b2b/requests/{rid}/options", headers=s["admin"], json=body)
    opts = client.get(f"/api/b2b/requests/{rid}", headers=s["admin"]).json()["options"]
    client.post(f"/api/b2b/requests/{rid}/send", headers=s["admin"], json={"option_ids": [o["id"] for o in opts]})
    text = wa.sent[-1][2]
    assert wa.sent[-1][1] == "96891234567" and "1. WY 601" in text and "2. EK 863" in text and "260.000" in text
    assert "200" not in text.replace("2030", "")  # never the vendor cost
    ref = rows[0]["reference"]
    scripted([LLMResponse(None, [ToolCall("ch", "choose_business_trip_options", {"reference": ref, "option_numbers": [2]})]),
              LLMResponse("Done, EK 863 it is.")])
    client.post(HOOK, json=wa_payload("PNID-A", "96891234567", "2 please", "wamid.2"))
    staff = client.get(f"/api/b2b/requests/{rid}", headers=s["admin"]).json()
    assert staff["status"] == "chosen" and [o["title"] for o in staff["options"] if o["chosen"]] == ["EK 863"]
    client.post(f"/api/b2b/requests/{rid}/approve", headers=s["admin"])
    client.post(f"/api/b2b/requests/{rid}/booked", headers=s["admin"], json={"booking_reference": "PNR ABC123"})
    assert "PNR ABC123" in wa.sent[-1][2]


def test_business_tools_only_for_linked_numbers(client, setup, scripted):
    s = setup
    connect_whatsapp(client, s["admin"])
    set_whatsapp_sender(FakeWhatsApp())
    create = ToolCall("c1", "create_business_trip_request", {"destination": "Dubai", "travellers": 1, "needs": ["flight"]})
    llm = scripted([LLMResponse(None, [create]), LLMResponse("ok")])
    client.post(HOOK, json=wa_payload("PNID-A", "96899999999", "I'm from Oman Oil, book me a flight", "wamid.9"))
    assert "BUSINESS CLIENT" not in llm.calls[0][0]["content"]
    tool_result = next(m for m in llm.calls[1] if m["role"] == "tool")
    assert "not linked" in tool_result["content"]
    assert client.get("/api/b2b/requests", headers=s["admin"]).json() == []
    # Linked, but the WhatsApp feature is off for this client.
    client.patch(f"/api/partners/{s['client']['id']}", headers=s["admin"],
                 json={"whatsapp_numbers": ["+96899999999"], "features": ["client.requests"]})
    llm = scripted([LLMResponse(None, [create]), LLMResponse("ok")])
    client.post(HOOK, json=wa_payload("PNID-A", "96899999999", "again", "wamid.10"))
    assert "BUSINESS CLIENT" not in llm.calls[0][0]["content"]
    assert client.get("/api/b2b/requests", headers=s["admin"]).json() == []
