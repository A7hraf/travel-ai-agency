"""After the client approves: payment proof (WhatsApp photo or trips page), the booking checklist, sending the
travel documents, finding a website request by its ID and the client's WhatsApp number, and file privacy."""

import base64
import re
from datetime import date, timedelta

from app.ai.llm import LLMResponse, ToolCall
from tests.conftest import make_company
from tests.test_ai_agent import say, start_chat
from tests.test_customer_portal import hdr, me_url
from tests.test_requests_flow import PHONE, services, wa, wa_say  # noqa: F401 (fixture)
from tests.test_whatsapp import HOOK, meta_stub, wa_payload  # noqa: F401 (fixture)

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PDF = b"%PDF-1.4\n" + b"1" * 300


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def media_payload(media_id, mid, kind="image", caption=None, filename=None):
    p = wa_payload("PNID-A", PHONE, "", mid)
    body = {"id": media_id, "mime_type": "image/jpeg" if kind == "image" else "application/pdf"}
    if caption:
        body["caption"] = caption
    if filename:
        body["filename"] = filename
    p["entry"][0]["changes"][0]["value"]["messages"][0].update({"type": kind, kind: body})
    del p["entry"][0]["changes"][0]["value"]["messages"][0]["text"]
    return p


def hotel_request(client, admin, scripted):
    """A hotel request made in the WhatsApp chat, quoted, chosen and approved: waiting for payment."""
    sid = services(client, admin)["hotel"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "Hotel in Dubai", "answers": {
        "destination": "Dubai", "depart_date": (date.today() + timedelta(days=20)).isoformat(),
        "return_date": (date.today() + timedelta(days=23)).isoformat(), "adults": "2", "rooms": "1", "full_name": "Omar"}})
    wa_say(client, "a hotel in Dubai", "wamid.r1", [LLMResponse(None, [card]), LLMResponse("Sent")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    base = f"/api/tickets/{t['id']}"
    oid = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Atlantis", "price": "900"}).json()["options"][0]["id"]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [oid]})
    client.post(f"{base}/send-final", headers=admin, json={})
    r = client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"}).json()
    assert r["status"] == "pending_payment"
    return t["id"], t["reference"], base


def test_payment_proof_photo_on_whatsapp(client, wa, scripted):
    company, admin, fake = wa
    # No open request yet: the photo is not kept, and the AI is told so.
    fake.media["M0"] = (JPEG, "image/jpeg")
    llm = scripted([LLMResponse("What is it for?")])
    client.post(HOOK, json=media_payload("M0", "wamid.p0"))
    assert "not kept" in llm.calls[0][-1]["content"]

    tid, ref, base = hotel_request(client, admin, scripted)
    assert any("photo or PDF" in m[2] for m in fake.sent)  # the payment message asks for the receipt
    fake.media["M1"] = (JPEG, "image/jpeg")
    llm = scripted([LLMResponse("Thank you! Our team will check it.")])
    client.post(HOOK, json=media_payload("M1", "wamid.p1", caption="paid today"))
    note = llm.calls[0][-1]["content"]
    assert f"payment proof of request {ref}" in note and "paid today" in note
    t = client.get(base, headers=admin).json()
    assert t["status"] == "in_progress"
    proof = t["request_files"][0]
    assert proof["kind"] == "payment_proof" and proof["uploaded_by"] == "client" and proof["name"].endswith(".jpg")
    r = client.get(f"{base}/files/{proof['id']}", headers=admin)
    assert r.status_code == 200 and r.content == JPEG and "attachment" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "private, no-store"
    # Meta's retry of the same message keeps only one copy; a file that can't be downloaded is not kept.
    client.post(HOOK, json=media_payload("M1", "wamid.p1"))
    llm = scripted([LLMResponse("Please send again")])
    client.post(HOOK, json=media_payload("MISSING", "wamid.p2"))
    assert "could not be received" in llm.calls[0][-1]["content"]
    assert len(client.get(base, headers=admin).json()["request_files"]) == 1
    # Lists stay light: no files there.
    assert client.get("/api/tickets", headers=admin).json()[0]["request_files"] == []
    actions = [e["action"] for e in client.get(f"{base}/events", headers=admin).json()]
    assert "payment_proof" in actions


def test_checklist_documents_and_the_client_page(client, wa, scripted, owner):
    company, admin, fake = wa
    tid, ref, base = hotel_request(client, admin, scripted)
    assert client.post(f"{base}/checklist", headers=admin, json={"step": "book", "done": True}).status_code == 409  # not paid yet
    client.patch(base, headers=admin, json={"status": "in_progress", "payment_reference": "TRX-1"})
    assert client.patch(base, headers=admin, json={"status": "paid"}).json()["status"] == "paid"
    t = client.get(base, headers=admin).json()
    assert [s["key"] for s in t["booking_steps"]] == ["book", "voucher"] and not any(s["done"] for s in t["booking_steps"])
    assert client.post(f"{base}/send-documents", headers=admin, json={}).status_code == 409  # steps first
    assert client.post(f"{base}/checklist", headers=admin, json={"step": "nope", "done": True}).status_code == 404
    for step in ("book", "voucher"):
        t = client.post(f"{base}/checklist", headers=admin, json={"step": step, "done": True}).json()
    assert all(s["done"] and s["by"] for s in t["booking_steps"])
    # Files: only real photos and PDFs, kept private.
    bad = client.post(f"{base}/files", headers=admin, json={"name": "x.pdf", "content_type": "application/pdf", "data_base64": b64(b"<html>")})
    assert bad.status_code == 415
    assert client.post(f"{base}/files", headers=admin, json={"content_type": "text/html", "data_base64": b64(b"x")}).status_code == 415
    r = client.post(f"{base}/files", headers=admin, json={"name": "../../Voucher Atlantis", "content_type": "application/pdf",
                                                            "data_base64": b64(PDF)})
    assert r.status_code == 201
    doc = r.json()["request_files"][0]
    assert doc["name"] == "Voucher Atlantis.pdf" and doc["sent_at"] is None
    extra = client.post(f"{base}/files", headers=admin, json={"name": "draft", "content_type": "image/jpeg", "data_base64": b64(JPEG)}).json()
    draft_id = extra["request_files"][-1]["id"]
    assert client.delete(f"{base}/files/{draft_id}", headers=admin).status_code == 200
    # Send: the client gets the message and the file on WhatsApp; the request is confirmed.
    r = client.post(f"{base}/send-documents", headers=admin, json={"note": "Check-in from 3 pm"}).json()
    assert r["status"] == "confirmed" and r["notice"] is None and r["request_files"][0]["sent_at"]
    assert fake.files == [(PHONE, "Voucher Atlantis.pdf", "application/pdf", f"{ref} · Voucher Atlantis.pdf")]
    assert "fully booked" in fake.sent[-1][2] and "Check-in from 3 pm" in fake.sent[-1][2]
    assert client.delete(f"{base}/files/{doc['id']}", headers=admin).status_code == 409  # already sent
    assert client.post(f"{base}/send-documents", headers=admin, json={}).status_code == 409  # nothing new
    # The client's private page shows the steps and the sent document, and only they can open it.
    slug = client.get("/api/auth/me", headers=admin).json()["company"]["slug"]
    client.post(me_url(slug, "/code"), json={"phone": "+" + PHONE, "reference": ref})
    code = re.match(r"(\d{6})", fake.sent[-1][2]).group(1)
    token = client.post(me_url(slug, "/verify"), json={"phone": "+" + PHONE, "code": code}).json()["token"]
    trip = client.get(me_url(slug, "/trips"), headers=hdr(token)).json()[0]
    assert trip["service_en"] == "Hotel booking" and all(c["done"] for c in trip["checklist"])
    assert [f["name"] for f in trip["files"]] == ["Voucher Atlantis.pdf"] and "cost_price" not in str(trip)
    got = client.get(me_url(slug, f"/files/{trip['files'][0]['key']}"), headers=hdr(token))
    assert got.status_code == 200 and got.content == PDF
    assert client.get(me_url(slug, f"/files/{trip['files'][0]['key']}")).status_code == 401
    # Another company's staff and another client can't open it.
    other_company, other_admin = make_company(client, owner, name="Other Co", admin_email="admin@other.com")
    other_slug = client.get("/api/auth/me", headers=other_admin).json()["company"]["slug"]
    assert client.get(f"{base}/files/{doc['id']}", headers=other_admin).status_code == 404
    assert client.get(me_url(other_slug, f"/files/{trip['files'][0]['key']}"), headers=hdr(token)).status_code == 401


def test_request_id_and_phone_find_a_website_request(client, wa, scripted):
    company, admin, fake = wa
    slug = client.get("/api/auth/me", headers=admin).json()["company"]["slug"]
    sid = services(client, admin)["visa"]["id"]
    # A request made in the website chat, with the WhatsApp number the client gave.
    token = start_chat(client, slug)
    card = ToolCall("c", "create_request", {"service_id": sid, "summary": "Schengen visa", "answers": {
        "destination": "France", "nationality": "Omani", "depart_date": (date.today() + timedelta(days=30)).isoformat(),
        "adults": "1", "full_name": "Salim", "phone": "+968 9555 1212"}})
    scripted([LLMResponse(None, [card]), LLMResponse("Done")])
    say(client, slug, token, "Visa for France please, my WhatsApp is +968 9555 1212")
    web = [t for t in client.get("/api/tickets", headers=admin).json() if (t["contact_phone"] or "").endswith("1212")]
    assert len(web) == 1
    ref = web[0]["reference"]
    sent_before = len(fake.sent)
    # A wrong number, or a wrong ID: nothing is sent (same answer).
    assert client.post(me_url(slug, "/code"), json={"phone": "+968 9555 0000", "reference": ref}).json() == {"sent": True}
    assert client.post(me_url(slug, "/code"), json={"phone": "+968 9555 1212", "reference": "TRV-NOPE00"}).json() == {"sent": True}
    assert len(fake.sent) == sent_before
    # The right pair: the code goes to that WhatsApp number; after it, the request is on the client's page.
    client.post(me_url(slug, "/code"), json={"phone": "+968 9555 1212", "reference": ref.lower()})
    assert fake.sent[-1][1] == "96895551212"
    code = re.match(r"(\d{6})", fake.sent[-1][2]).group(1)
    token = client.post(me_url(slug, "/verify"), json={"phone": "+968 9555 1212", "code": code}).json()["token"]
    trips = client.get(me_url(slug, "/trips"), headers=hdr(token)).json()
    assert [t["reference"] for t in trips] == [ref] and trips[0]["phase"] == "quotation" and trips[0]["can_upload"]
    # The client sends a paper from the page (kept with the request, not a payment proof yet).
    trips = client.post(me_url(slug, f"/trips/{trips[0]['id']}/files"), headers=hdr(token),
                        json={"name": "passport", "content_type": "image/jpeg", "data_base64": b64(JPEG)})
    assert trips.status_code == 201 and trips.json()[0]["files"][0]["kind"] == "client_file"
    # The WhatsApp client of this company never sees that request.
    client.post(me_url(slug, "/code"), json={"phone": "+" + PHONE})
    code = re.match(r"(\d{6})", fake.sent[-1][2]).group(1)
    other = client.post(me_url(slug, "/verify"), json={"phone": "+" + PHONE, "code": code}).json()["token"]
    assert ref not in [t["reference"] for t in client.get(me_url(slug, "/trips"), headers=hdr(other)).json()]
