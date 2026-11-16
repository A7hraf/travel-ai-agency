"""Every built-in service, from the first details to the end of its workflow, the way the team works it; and a
request cancelled by the client and one by the team after the quotation was approved."""

import pytest

from tests.test_requests_flow import PHONE, services, wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)
from tests.test_workflow import IN_30, IN_35, quote_and_approve

ANSWERS = {
    "destination": "Georgia", "origin": "Muscat", "depart_date": IN_30, "return_date": IN_35, "adults": "2", "rooms": "1",
    "cabin": "Economy", "nationality": "Omani", "purpose": "Tourism", "preferred_times": "Mornings next week",
    "direction": "Arrival", "flight_number": "WY 101", "details": "Dinner booking for 4 on Friday",
    "full_name": "Omar Al Said", "phone": "+" + PHONE,
}
PART = {"flights": "flight", "hotel": "hotel", "visa": "visa", "airport_transfer": "transport"}
SERVICES = ["custom_trip", "flights", "hotel", "visa", "embassy", "airport_assist", "airport_transfer", "concierge"]


def drive(client, admin, base, key):
    """Works the request step by step as the team would; returns the step types it went through."""
    seen = []
    for _ in range(20):
        t = client.get(base, headers=admin).json()
        step = next((s for s in t["process"]["steps"] if s["state"] == "active"), None)
        if step is None:
            return t, seen
        seen.append(step["type"])
        if step["type"] == "quote":
            oid = client.post(f"{base}/options", headers=admin, json={
                "category": PART.get(key, "other"), "title": "Choice", "cost_price": "80", "price": "100"}).json()["options"][-1]["id"]
            assert client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]}).status_code == 200
            client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [oid]})
            client.post(f"{base}/send-final", headers=admin, json={})
            r = client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"})
        else:
            # Documents, payments made outside the system and appointments are passed by the admin here.
            r = client.post(f"{base}/workflow/done", headers=admin, json={"key": step["key"]})
        assert r.status_code == 200, (key, step, r.text)
    raise AssertionError(f"{key}: the workflow never ended ({seen})")


@pytest.mark.parametrize("key", SERVICES)
def test_each_service_runs_to_the_end(client, wa, key):  # noqa: F811
    _, admin, _ = wa
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)[key]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": ANSWERS, "summary": "Use case"})
    assert r.status_code == 201, r.text
    base = f"/api/tickets/{r.json()['id']}"
    t, seen = drive(client, admin, base, key)
    assert seen[0] == "intake" or "intake" not in seen
    assert t["status"] == "completed", (key, t["status"], seen)
    assert all(s["state"] in ("done", "skipped") for s in t["process"]["steps"]), key
    # Every step that ended says who ended it.
    assert all(s.get("by") for s in t["process"]["steps"] if s["state"] == "done"), key


@pytest.mark.parametrize("by,reason", [("client", "Found a cheaper offer"), ("team", "No availability on those dates")])
def test_cancelling_keeps_who_why_and_where(client, wa, by, reason):  # noqa: F811
    _, admin, _ = wa
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)["hotel"]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": ANSWERS, "summary": "Use case"})
    base = f"/api/tickets/{r.json()['id']}"
    quote_and_approve(client, admin, base, "hotel", "100")
    step = client.get(base, headers=admin).json()["current_step"]
    t = client.post(f"{base}/close", headers=admin, json={"by": by, "reason": reason}).json()
    assert t["status"] == "cancelled"
    info = t["process"]["cancel"]
    assert info["by"] == by and info["reason"] == reason and info["step"] == step["key"] != "review"
    # Closed means closed: no more steps until it is reopened.
    assert client.post(f"{base}/workflow/done", headers=admin, json={"key": step["key"]}).status_code == 409
