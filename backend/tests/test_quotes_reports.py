"""Branded quotations (design, draft, final, the client's own view) and business reports (page and Excel)."""

import base64
import io
import re

from openpyxl import load_workbook

from app.ai.llm import MockTravelLLM, set_llm_client
from tests.test_customer_portal import hdr, me_url
from tests.test_library import dubai_request, switch
from tests.test_requests_flow import PHONE, wa  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()


def test_quotation_design_draft_final_and_client_view(client, wa, scripted, owner):
    company, admin, fake = wa
    assert client.get("/api/quote-settings", headers=admin).status_code == 403
    switch(client, owner, company["id"], quotes=True, library=True)
    set_llm_client(MockTravelLLM())
    sample = ("Welcome to Blue Sky Travel, Oman's boutique travel house since 2009.\n\n"
              "Payment terms: 50% on approval, the rest 14 days before travel. Cancellation fees apply.")
    draft = client.post("/api/quote-settings/ai-draft", headers=admin, json={"text": sample}).json()
    assert draft["intro_en"].startswith("Welcome") and "Payment terms" in draft["terms_en"]
    saved = client.put("/api/quote-settings", headers=admin, json={**draft, "intro_ar": "مرحباً بكم", "valid_days": 5}).json()
    assert saved["valid_days"] == 5

    photo = client.post("/api/media", headers=admin, json={"content_type": "image/png", "data_base64": PNG}).json()["url"]
    sup = client.post("/api/library", headers=admin, json={"category": "hotel", "name": "Atlantis The Palm", "place": "Dubai",
                                                           "stars": 5, "image_url": photo, "description": "Iconic resort",
                                                           "usual_cost": "700", "usual_price": "900"}).json()
    t, base = dubai_request(client, admin, scripted, mid="wamid.q1")
    assert client.get(f"{base}/quotation", headers=admin).status_code == 409  # nothing priced yet
    opt = client.post(f"{base}/options/from-library", headers=admin, json={"supplier_id": sup["id"]}).json()["options"][0]
    q = client.get(f"{base}/quotation", headers=admin).json()
    item = q["items"][0]
    assert item["image_url"] == photo and item["details"] == "Iconic resort" and item["stars"] == 5 and item["price"] == 900
    assert "cost" not in str(q) and "estimate" not in str(q) and q["design"]["intro_ar"] == "مرحباً بكم"
    assert q["company"]["name"] == "Blue Sky Travel" and q["total"] is None
    assert client.get(f"{base}/quotation?kind=final", headers=admin).status_code == 409
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [opt["id"]]})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [opt["id"]]})
    client.post(f"{base}/send-final", headers=admin, json={})
    final = client.get(f"{base}/quotation?kind=final", headers=admin).json()
    assert final["total"] == 900 and final["items"][0]["chosen"] is True

    # The client sees their own final quotation on the trips page; nobody else can.
    slug = company["slug"]
    client.post(me_url(slug, "/code"), json={"phone": "+" + PHONE, "reference": t["reference"]})
    code = re.match(r"(\d{6})", fake.sent[-1][2]).group(1)
    token = client.post(me_url(slug, "/verify"), json={"phone": "+" + PHONE, "code": code}).json()["token"]
    trip = client.get(me_url(slug, "/trips"), headers=hdr(token)).json()[0]
    assert trip["has_quotation"] is True
    mine = client.get(me_url(slug, f"/trips/{trip['id']}/quotation"), headers=hdr(token)).json()
    assert mine["kind"] == "final" and mine["total"] == 900 and "cost" not in str(mine)
    assert client.get(me_url(slug, f"/trips/{trip['id']}/quotation")).status_code == 401
    switch(client, owner, company["id"], quotes=False)
    assert client.get(me_url(slug, f"/trips/{trip['id']}/quotation"), headers=hdr(token)).status_code == 404


def test_reports_page_and_excel(client, wa, scripted, owner):
    company, admin, fake = wa
    assert client.get("/api/reports/summary", headers=admin).status_code == 403
    switch(client, owner, company["id"], reports=True)
    t, base = dubai_request(client, admin, scripted, mid="wamid.q2")
    opt = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Atlantis", "price": "900",
                                                             "cost_price": "700"}).json()["options"][0]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [opt["id"]]})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "choose", "option_ids": [opt["id"]]})
    client.post(f"{base}/send-final", headers=admin, json={})
    client.post(f"{base}/client-answer", headers=admin, json={"action": "approve"})
    client.patch(base, headers=admin, json={"status": "in_progress", "payment_reference": "TRX-1"})
    client.patch(base, headers=admin, json={"status": "paid"})
    r = client.get("/api/reports/summary", headers=admin).json()
    assert r["totals"]["requests"] == 1 and r["totals"]["revenue"] == 900 and r["totals"]["margin"] == 200
    assert r["by_service"][0]["name_en"] == "Hotel booking" and r["quotations"] == {
        "quoted": 1, "approved": 1, "approval_rate": 1.0, "average_rounds": 1.0}
    assert r["destinations"] == [["Dubai", 1]]
    assert client.get("/api/reports/summary?start=2026-05-01&end=2026-01-01", headers=admin).status_code == 422
    assert client.get("/api/reports/summary.xlsx", headers=admin).status_code == 403
    switch(client, owner, company["id"], reports_excel=True)
    x = client.get("/api/reports/summary.xlsx", headers=admin)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames[:4] == ["Summary", "Requests", "By service", "By staff"]
    assert wb["Requests"]["A5"].value == t["reference"]
