"""The request workspace: requests taken by staff, editing details, price/cost/profit, payments (deposit,
balance, receipts checked or refused), the client's documents, the trip plan, and the pipeline list."""

import re
from datetime import date, timedelta

from app.ai.llm import LLMResponse, MockTravelLLM, set_llm_client
from tests.test_request_files import JPEG, b64, hotel_request, media_payload
from tests.test_library import switch
from tests.test_requests_flow import PHONE, services, wa  # noqa: F401 (fixture)
from tests.test_whatsapp import HOOK, meta_stub  # noqa: F401 (fixture)

IN_20 = (date.today() + timedelta(days=20)).isoformat()
IN_26 = (date.today() + timedelta(days=26)).isoformat()


def test_staff_request_money_and_plan(client, wa, scripted, owner):
    company, admin, fake = wa
    switch(client, owner, company["id"], plan_writer=True)
    svc = services(client, admin)
    # A walk-in client: staff save what they know; the rest is added later.
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": svc["custom_trip"]["id"], "name": "Aisha Al Balushi", "phone": "+968 9222 3344",
        "answers": {"destination": "Georgia", "adults": "2"}, "summary": "Honeymoon, nature, 5 star"})
    assert r.status_code == 201, r.text
    t = r.json()
    base = f"/api/tickets/{t['id']}"
    assert t["stage"] == "quote" and t["created_by"] == "staff" and t["assigned_to"]["id"]
    assert t["lead_traveler_name"] == "Aisha Al Balushi" and t["contact_phone"] == "+96892223344"
    assert t["client_documents"]["items"][0]["key"] == "passport" and t["client_documents"]["missing"] == 1
    t = client.put(f"{base}/details", headers=admin, json={"answers": {"depart_date": IN_20, "return_date": IN_26,
                                                                       "children": "1 (age 6)"}}).json()
    assert t["departure_date"] == IN_20 and t["children"] == 1 and t["client_documents"]["items"][0]["need"] == 3
    assert client.post("/api/tickets", headers=admin, json={"service_id": svc["custom_trip"]["id"]}).status_code == 422

    # Choices with cost and price: the profit follows the client's choice, or the cost the team writes.
    h = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Rooms Kazbegi", "cost_price": "900", "price": "1150"}).json()["options"][0]
    f = [o for o in client.post(f"{base}/options", headers=admin, json={"category": "flight", "title": "Flydubai via DXB", "cost_price": "520", "price": "600"}).json()["options"] if o["category"] == "flight"][0]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [h["id"], f["id"]]})
    t = client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [h["id"], f["id"]]}).json()
    assert t["money"] | {} == t["money"] and t["money"]["choices_total"] == 1750 and t["money"]["cost"] == 1420
    assert t["money"]["profit"] == 330 and t["money"]["cost_from"] == "choices"
    t = client.post(f"{base}/send-final", headers=admin, json={"total": "1800"}).json()
    assert t["money"]["profit"] == 380 and t["money"]["margin_pct"] == 26.8
    t = client.put(f"{base}/money", headers=admin, json={"cost_price": "1500"}).json()
    assert t["money"]["cost"] == 1500 and t["money"]["profit"] == 300 and t["money"]["cost_from"] == "manual"
    assert client.put(f"{base}/money", headers=admin, json={"clear_cost": True}).json()["money"]["cost_from"] == "choices"

    # The trip plan: drafted by the AI (not saved), then saved by staff; dated from the departure.
    set_llm_client(MockTravelLLM())
    days = client.post(f"{base}/itinerary/ai-draft", headers=admin).json()["days"]
    assert len(days) == 7 and days[0]["title"].startswith("Arrival in Georgia") and "Rooms Kazbegi" in days[0]["details"]
    t = client.put(f"{base}/itinerary", headers=admin, json={"days": days[:2]}).json()
    assert [d["day"] for d in t["itinerary"]] == [1, 2] and t["itinerary"][1]["date"] == (date.today() + timedelta(days=21)).isoformat()
    assert client.put(f"{base}/itinerary", headers=admin, json={"days": [{"day": 0, "title": "x"}]}).status_code == 422


def test_payments_deposit_balance_and_refused_receipt(client, wa, scripted):
    company, admin, fake = wa
    tid, ref, base = hotel_request(client, admin, scripted)  # approved: 900 to pay
    # The client sends a receipt on WhatsApp: a payment to check.
    fake.media["R1"] = (JPEG, "image/jpeg")
    scripted([LLMResponse("Thanks, we will check it.")])
    client.post(HOOK, json=media_payload("R1", "wamid.pay1"))
    t = client.get(base, headers=admin).json()
    assert t["status"] == "in_progress" and t["money"]["pending_proofs"] == 1
    proof = t["payment_list"][0]
    assert proof["status"] == "pending" and proof["created_by"] == "client" and proof["file_id"]
    # Refused: the client is told why, the request waits for payment again.
    t = client.post(f"{base}/payments/{proof['id']}/reject", headers=admin, json={"note": "The amount is not visible"}).json()
    assert t["status"] == "pending_payment" and "amount is not visible" in fake.sent[-1][2]
    assert client.post(f"{base}/payments/{proof['id']}/approve", headers=admin, json={"amount": "100"}).status_code == 409

    # A new receipt for the deposit, approved with its amount; then the balance in cash at the office.
    fake.media["R2"] = (JPEG, "image/jpeg")
    scripted([LLMResponse("Thanks")])
    client.post(HOOK, json=media_payload("R2", "wamid.pay2"))
    pending = [p for p in client.get(base, headers=admin).json()["payment_list"] if p["status"] == "pending"][0]
    t = client.post(f"{base}/payments/{pending['id']}/approve", headers=admin, json={"amount": "400", "reference": "TRX-55"}).json()
    assert t["status"] == "in_progress" and t["money"]["paid"] == 400 and t["money"]["balance"] == 500
    t = client.post(f"{base}/payments", headers=admin, json={"amount": "500", "method": "cash", "reference": "RCPT-9"}).json()
    assert t["status"] == "paid" and t["money"]["balance"] == 0 and t["payment_reference"] == "RCPT-9"
    assert t["stage"] == "booking" and any("received" in m[2].lower() or "استلام" in m[2] for m in fake.sent[-2:])
    hist = [e["action"] for e in client.get(f"{base}/events", headers=admin).json()]
    assert {"payment_rejected", "payment_approved", "payment_added"} <= set(hist)


def test_client_documents_sorted(client, wa, scripted):
    company, admin, fake = wa
    sid = services(client, admin)["visa"]["id"]
    card = {"service_id": sid, "summary": "Schengen visa", "answers": {
        "destination": "France", "nationality": "Omani", "depart_date": IN_20, "adults": "2", "full_name": "Omar"}}
    from app.ai.llm import ToolCall
    from tests.test_requests_flow import wa_say
    wa_say(client, "visa please", "wamid.v1", [LLMResponse(None, [ToolCall("c", "create_request", card)]), LLMResponse("Sent")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    base = f"/api/tickets/{t['id']}"
    docs = client.get(base, headers=admin).json()["client_documents"]
    assert [i["key"] for i in docs["items"]] == ["passport", "photo", "bank_statement", "booking"]
    assert docs["items"][0]["need"] == 2 and docs["missing"] == 3
    # A photo captioned "passport" is filed as a passport; one without a caption waits to be sorted.
    fake.media["P1"] = (JPEG, "image/jpeg")
    llm = scripted([LLMResponse("Got it")])
    client.post(HOOK, json=media_payload("P1", "wamid.d1", caption="my passport"))
    assert "as: Passport copy" in llm.calls[0][-1]["content"] and "Still missing" in llm.calls[0][-1]["content"]
    fake.media["P2"] = (JPEG, "image/jpeg")
    scripted([LLMResponse("Got it")])
    client.post(HOOK, json=media_payload("P2", "wamid.d2"))
    t = client.get(base, headers=admin).json()
    assert t["client_documents"]["items"][0]["have"] == 1 and len(t["client_documents"]["unsorted"]) == 1
    fid = t["client_documents"]["unsorted"][0]
    t = client.patch(f"{base}/files/{fid}", headers=admin, json={"kind": "client_file", "requirement": "passport"}).json()
    assert t["client_documents"]["items"][0]["done"] and t["client_documents"]["unsorted"] == []
    assert client.patch(f"{base}/files/{fid}", headers=admin, json={"kind": "client_file", "requirement": "nope"}).status_code == 422
    assert client.patch(f"{base}/files/{fid}", headers=admin, json={"kind": "document"}).status_code == 422


def test_pipeline_list_and_summary(client, wa, scripted):
    company, admin, fake = wa
    hotel_request(client, admin, scripted)  # payment stage
    svc = services(client, admin)
    for i, dest in enumerate(["Baku", "Bali", "Cairo"]):
        client.post("/api/tickets", headers=admin, json={"service_id": svc["custom_trip"]["id"], "name": f"Client {i}",
                                                         "answers": {"destination": dest, "depart_date": (date.today() + timedelta(days=40 - i)).isoformat()}})
    r = client.get("/api/tickets?stage=quote&limit=2", headers=admin)
    assert r.headers["x-total-count"] == "3" and len(r.json()) == 2
    assert [t["destination"] for t in client.get("/api/tickets?stage=quote&sort=departure", headers=admin).json()] == ["Cairo", "Bali", "Baku"]
    assert [t["destination"] for t in client.get("/api/tickets?q=bali", headers=admin).json()] == ["Bali"]
    assert len(client.get("/api/tickets?stage=payment", headers=admin).json()) == 1
    assert len(client.get("/api/tickets?assigned=none", headers=admin).json()) == 1  # the AI's request
    s = client.get("/api/tickets/summary", headers=admin).json()
    assert s["stages"]["quote"] == 3 and s["stages"]["payment"] == 1 and s["to_collect"] == 900
    assert s["unassigned"] == 1 and s["currency"] == "OMR"
    assert re.match(r"^\d", str(s["pipeline_value"]))
