"""The supplier library: switched on per company (with its parts), saved suppliers suggested for the request's
place, saving a choice, the AI drafting from the library first, spending figures and the usual margin."""

from datetime import date, timedelta

from app.ai.llm import LLMResponse, MockTravelLLM, ToolCall, set_llm_client
from tests.conftest import make_company
from tests.test_requests_flow import services, wa, wa_say  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)


def switch(client, owner, company_id, **on):
    path = f"/api/system/companies/{company_id}/addons"
    current = client.get(path, headers=owner).json()["addons"]
    assert client.put(path, headers=owner, json={**current, **on}).status_code == 200


def dubai_request(client, admin, scripted, mid="wamid.l1"):
    sid = services(client, admin)["hotel"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "Hotel in Dubai", "answers": {
        "destination": "Dubai", "depart_date": (date.today() + timedelta(days=20)).isoformat(),
        "return_date": (date.today() + timedelta(days=23)).isoformat(), "adults": "2", "rooms": "1", "full_name": "Omar"}})
    wa_say(client, "a hotel in Dubai", mid, [LLMResponse(None, [card]), LLMResponse("Sent")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    return t, f"/api/tickets/{t['id']}"


def test_library_switch_suggestions_and_figures(client, wa, scripted, owner):
    company, admin, fake = wa
    assert client.get("/api/library", headers=admin).status_code == 403
    switch(client, owner, company["id"], library=True)
    hotel = {"category": "hotel", "name": "Atlantis The Palm", "place": "Dubai, UAE", "stars": 5,
             "usual_cost": "700", "usual_price": "900", "preferred": True, "description": "Beach resort with waterpark"}
    bad = client.post("/api/library", headers=admin, json={**hotel, "image_url": "https://example.com/a.jpg"})
    assert bad.status_code == 422
    s = client.post("/api/library", headers=admin, json=hotel).json()
    client.post("/api/library", headers=admin, json={"category": "hotel", "name": "Shangri-La Muscat", "place": "Muscat", "stars": 5})
    client.post("/api/library", headers=admin, json={"category": "flight", "name": "Oman Air"})  # anywhere
    assert [x["name"] for x in client.get("/api/library?q=dubai", headers=admin).json()] == ["Atlantis The Palm"]

    t, base = dubai_request(client, admin, scripted)
    sug = client.get(f"{base}/library", headers=admin).json()
    assert [x["name"] for x in sug["hotel"]] == ["Atlantis The Palm"]  # Muscat's hotel is not suggested for Dubai
    r = client.post(f"{base}/options/from-library", headers=admin, json={"supplier_id": s["id"]}).json()
    opt = r["options"][0]
    assert opt["supplier_id"] == s["id"] and opt["price"] == 900 and opt["cost_price"] == 700
    # A choice typed by hand can be saved to the library.
    r = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Jumeirah Beach Hotel", "price": "800", "cost_price": "650"}).json()
    typed = [o for o in r["options"] if o["title"] == "Jumeirah Beach Hotel"][0]
    r = client.post(f"{base}/options/{typed['id']}/save-to-library", headers=admin).json()
    assert [o for o in r["options"] if o["id"] == typed["id"]][0]["supplier_id"]
    assert {x["name"] for x in client.get("/api/library?category=hotel", headers=admin).json()} >= {"Jumeirah Beach Hotel"}
    # Another company can't use this supplier.
    other, other_admin = make_company(client, owner, name="Other Co", admin_email="admin@other.com")
    switch(client, owner, other["id"], library=True)
    assert client.put(f"/api/library/{s['id']}", headers=other_admin, json=hotel).status_code == 404

    # Paid: the figures and the usual margin (parts switched on separately).
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [opt["id"]]})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [opt["id"]]})
    client.post(f"{base}/send-final", headers=admin, json={})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"})
    client.patch(base, headers=admin, json={"status": "in_progress", "payment_reference": "TRX-9"})
    client.patch(base, headers=admin, json={"status": "paid"})
    assert client.get("/api/library/stats", headers=admin).status_code == 403
    switch(client, owner, company["id"], library_analytics=True, library_margins=True)
    st = client.get("/api/library/stats", headers=admin).json()
    assert st["suppliers"][0] == {**st["suppliers"][0], "name": "Atlantis The Palm", "bookings": 1, "cost": 700.0,
                                  "revenue": 900.0, "margin": 200.0, "in_library": True}
    assert st["hotel_stars"] == {"5": 1} and st["by_part"]["hotel"]["margin"] == 200.0
    assert client.get("/api/library/margins", headers=admin).json() == {"hotel": {"margin_pct": 28.6, "samples": 1}}
    assert [x for x in client.get("/api/library", headers=admin).json() if x["id"] == s["id"]][0]["bookings"] == 1


def test_ai_draft_uses_the_library_first(client, wa, scripted, owner):
    company, admin, fake = wa
    switch(client, owner, company["id"], library=True, trip_planner=True)
    client.post("/api/library", headers=admin, json={"category": "hotel", "name": "Atlantis The Palm", "place": "Dubai",
                                                      "usual_price": "900", "preferred": True})
    t, base = dubai_request(client, admin, scripted, mid="wamid.l2")
    set_llm_client(MockTravelLLM())
    r = client.post(f"{base}/ai-draft", headers=admin)
    assert r.status_code == 200, r.text
    first = [o for o in r.json()["options"] if o["category"] == "hotel"][0]
    assert first["title"] == "Atlantis The Palm" and first["added_by"] == "ai" and first["price"] is None
    assert first["estimate_price"] == 900 and "library" in first["ai_reason"]
