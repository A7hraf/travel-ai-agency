"""The customer's private trips page: getting in through WhatsApp, what they see, and feedback after trips."""

import json
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse, ToolCall
from app.database import SessionLocal
from app.models import Conversation, Customer, Ticket, TicketStatus, utcnow
from app.services.customer_portal import send_feedback_requests
from app.services.whatsapp import set_whatsapp_sender
from tests.conftest import FakeWhatsApp, make_company, make_package
from tests.test_ai_agent import say, start_chat
from tests.test_whatsapp import HOOK, connect_whatsapp, meta_stub, wa_payload  # noqa: F401 (fixture)

PHONE = "96891234567"


def me_url(slug, path=""):
    return f"/api/public/companies/{slug}/me{path}"


def hdr(token):
    return {"X-Customer-Token": token}


@pytest.fixture
def shop(client, company_a, scripted):
    """A company with WhatsApp, and a customer who wrote from +968 9123 4567."""
    company, admin = company_a
    connect_whatsapp(client, admin)
    wa = FakeWhatsApp()
    set_whatsapp_sender(wa)
    scripted([LLMResponse("Hello Omar!")])
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, "Hi", "wamid.1"))
    return company, admin, wa


def code_login(client, slug, wa, phone="+968 9123 4567"):
    assert client.post(me_url(slug, "/code"), json={"phone": phone}).status_code == 202
    code = re.match(r"(\d{6})", wa.sent[-1][2]).group(1)
    r = client.post(me_url(slug, "/verify"), json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def add_ticket(company_id, customer_phone=PHONE, days_ago=10, status=TicketStatus.CONFIRMED, package_id=None, ref="TRV-AAAA11"):
    with SessionLocal() as db:
        customer = db.scalar(select(Customer).where(Customer.company_id == company_id, Customer.whatsapp_id == customer_phone))
        t = Ticket(company_id=company_id, reference=ref, customer_id=customer.id, package_id=package_id,
                   package_title="Maldives Honeymoon", departure_date=(date.today() - timedelta(days=days_ago)).isoformat(),
                   adults=2, children=0, lead_traveler_name="Omar Al Said", total_price=Decimal("4000"), currency="OMR",
                   status=status)
        db.add(t)
        db.commit()
        return t.id


def test_code_login_and_what_the_customer_sees(client, shop):
    company, admin, wa = shop
    slug = company["slug"]
    token = code_login(client, slug, wa)
    assert wa.sent[-1][1] == PHONE  # the code goes only to the customer's own WhatsApp
    me = client.get(me_url(slug), headers=hdr(token)).json()
    assert me["phone"] == "+96891234567" and me["company_name"] == company["name"] and me["member"] is None
    chats = client.get(me_url(slug, "/chats"), headers=hdr(token)).json()
    assert [m["content"] for m in chats[0]["messages"]] == ["Hi", "Hello Omar!"]
    assert client.get(me_url(slug, "/trips"), headers=hdr(token)).json() == []


def test_codes_are_safe(client, shop, owner):
    company, admin, wa = shop
    slug = company["slug"]
    sent = len(wa.sent)
    # An unknown number gets the same answer, and nothing is sent.
    assert client.post(me_url(slug, "/code"), json={"phone": "+968 9999 9999"}).json() == {"sent": True}
    assert len(wa.sent) == sent
    assert client.post(me_url(slug, "/code"), json={"phone": "hello"}).status_code == 422
    # Five wrong tries burn the code.
    client.post(me_url(slug, "/code"), json={"phone": PHONE})
    code = re.match(r"(\d{6})", wa.sent[-1][2]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post(me_url(slug, "/verify"), json={"phone": PHONE, "code": wrong}).status_code == 400
    assert client.post(me_url(slug, "/verify"), json={"phone": PHONE, "code": code}).status_code == 400
    # A code is used once.
    token = code_login(client, slug, wa)
    code = re.match(r"(\d{6})", wa.sent[-1][2]).group(1)
    assert client.post(me_url(slug, "/verify"), json={"phone": PHONE, "code": code}).status_code == 400
    # The token works only here: not for another company, not as a staff login, and a staff token fails here.
    other, _ = make_company(client, owner, name="Other", admin_email="o@other.com")
    assert client.get(me_url(other["slug"]), headers=hdr(token)).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    staff_token = admin["Authorization"].split()[1]
    assert client.get(me_url(slug), headers=hdr(staff_token)).status_code == 401
    assert client.get(me_url(slug), headers=admin).status_code == 401
    # Signing out everywhere ends the session.
    assert client.post(me_url(slug, "/logout-everywhere"), headers=hdr(token)).status_code == 204
    assert client.get(me_url(slug), headers=hdr(token)).status_code == 401


def test_link_from_the_whatsapp_chat(client, shop, scripted):
    company, admin, wa = shop
    slug = company["slug"]
    llm = scripted([LLMResponse(None, [ToolCall("l", "send_my_trips_link", {})]), LLMResponse("Here is your link")])
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, "show me my trips", "wamid.2"))
    result = json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])
    assert f"/c/{slug}/me#k=" in result["link"]
    key = result["link"].split("#k=")[1]
    r = client.post(me_url(slug, "/link"), json={"key": key})
    assert r.status_code == 200
    assert client.get(me_url(slug), headers=hdr(r.json()["token"])).json()["phone"] == "+96891234567"
    assert client.post(me_url(slug, "/link"), json={"key": key}).status_code == 400  # one use
    # On the website chat the AI can't hand out links (nothing proves who is writing).
    llm = scripted([LLMResponse(None, [ToolCall("l", "send_my_trips_link", {})]), LLMResponse("ok")])
    say(client, slug, start_chat(client, slug), "my trips link please")
    assert "only on WhatsApp" in [m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"]


def test_trips_tracking_and_feedback(client, shop):
    company, admin, wa = shop
    slug = company["slug"]
    pkg = make_package(client, admin, duration_days=5)
    done = add_ticket(company["id"], days_ago=10, package_id=pkg["id"], ref="TRV-DONE11")
    add_ticket(company["id"], days_ago=-20, package_id=pkg["id"], ref="TRV-SOON22")
    add_ticket(company["id"], days_ago=2, package_id=pkg["id"], ref="TRV-NOW333")
    add_ticket(company["id"], days_ago=-5, status=TicketStatus.PENDING_PAYMENT, ref="TRV-PAY444")
    token = code_login(client, slug, wa)
    trips = {t["reference"]: t for t in client.get(me_url(slug, "/trips"), headers=hdr(token)).json()}
    assert {k: t["phase"] for k, t in trips.items()} == {
        "TRV-DONE11": "finished", "TRV-SOON22": "upcoming", "TRV-NOW333": "travelling", "TRV-PAY444": "booking"}
    assert trips["TRV-DONE11"]["can_rate"] and not trips["TRV-SOON22"]["can_rate"]
    assert "internal_notes" not in json.dumps(trips)
    soon = trips["TRV-SOON22"]["id"]
    assert client.post(me_url(slug, f"/trips/{soon}/feedback"), headers=hdr(token), json={"rating": 5}).status_code == 409
    assert client.post(me_url(slug, f"/trips/{done}/feedback"), headers=hdr(token), json={"rating": 9}).status_code == 422
    r = client.post(me_url(slug, f"/trips/{done}/feedback"), headers=hdr(token), json={"rating": 4, "comment": "Lovely villa"})
    assert next(t for t in r.json() if t["id"] == done)["rating"] == 4
    assert client.post(me_url(slug, f"/trips/{done}/feedback"), headers=hdr(token), json={"rating": 5}).status_code == 409
    staff = client.get("/api/feedback", headers=admin).json()
    assert staff["average"] == 4 and staff["count"] == 1 and staff["feedback"][0]["comment"] == "Lovely villa"


def test_customers_never_see_each_other(client, shop, scripted):
    company, admin, wa = shop
    slug = company["slug"]
    scripted([LLMResponse("Hi Sara")])
    client.post(HOOK, json=wa_payload("PNID-A", "96855555555", "Hello", "wamid.9", name="Sara"))
    other_ticket = add_ticket(company["id"], customer_phone="96855555555", ref="TRV-OTHER1")
    token = code_login(client, slug, wa)
    assert client.get(me_url(slug, "/trips"), headers=hdr(token)).json() == []
    assert all("Hi Sara" not in json.dumps(c) for c in client.get(me_url(slug, "/chats"), headers=hdr(token)).json())
    r = client.post(me_url(slug, f"/trips/{other_ticket}/feedback"), headers=hdr(token), json={"rating": 1})
    assert r.status_code == 404


def test_after_trip_message_and_feedback_in_the_chat(client, shop, scripted):
    company, admin, wa = shop
    add_ticket(company["id"], days_ago=3, ref="TRV-BACK11")  # no package: a one-day trip, ended 3 days ago
    sent = len(wa.sent)
    with SessionLocal() as db:
        assert send_feedback_requests(db, date.today()) == 1
        assert send_feedback_requests(db, date.today()) == 0  # asked once
    assert "How was your trip" in wa.sent[sent][2] and wa.sent[sent][1] == PHONE
    # The customer answers; the AI saves it.
    llm = scripted([LLMResponse(None, [ToolCall("f", "record_trip_feedback", {"reference": "TRV-BACK11", "rating": 5, "comment": "Perfect"})]),
                    LLMResponse("Thank you!")])
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, "5, it was perfect", "wamid.3"))
    assert "TRV-BACK11" in llm.calls[0][0]["content"] and "ask once how it was" in llm.calls[0][0]["content"]
    fb = client.get("/api/feedback", headers=admin).json()["feedback"][0]
    assert fb["rating"] == 5 and fb["source"] == "chat"
    # Next time the AI no longer asks.
    llm = scripted([LLMResponse("Anything else?")])
    client.post(HOOK, json=wa_payload("PNID-A", PHONE, "thanks", "wamid.4"))
    assert "TRV-BACK11" not in llm.calls[0][0]["content"]


def test_no_after_trip_message_outside_the_whatsapp_window(client, shop):
    company, admin, wa = shop
    add_ticket(company["id"], days_ago=3, ref="TRV-LATE11")
    with SessionLocal() as db:
        conv = db.scalar(select(Conversation).where(Conversation.company_id == company["id"]))
        conv.last_customer_message_at = utcnow() - timedelta(days=3)
        db.commit()
        assert send_feedback_requests(db, date.today()) == 0
