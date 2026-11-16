"""The newer screens keep companies and business partners apart: workflows, team questions, quotations,
notifications, broadcasts, team figures, payment plans and partner figures. Another company's ids get 404
(or nothing), and a partner never reaches another partner's request."""

from app.addons import FEATURES as ADDONS
from app.b2b import FEATURES as B2B
from tests.conftest import make_company
from tests.test_b2b_flow import setup_trip
from tests.test_library import switch
from tests.test_partners import add_login, add_partner, switch_on


def staff_request(client, admin, name="Private Client", place="Zanzibar"):
    sid = {s["key"]: s for s in client.get("/api/services", headers=admin).json()}["custom_trip"]["id"]
    t = client.post("/api/tickets", headers=admin, json={
        "service_id": sid, "name": name, "phone": "+968 9111 2233",
        "answers": {"destination": place, "origin": "Muscat", "depart_date": "2030-02-01", "adults": "2"},
        "summary": f"secret plan of {name}"}).json()
    base = f"/api/tickets/{t['id']}"
    opt = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Beach villa", "cost_price": "900",
                                                              "price": "1100"}).json()["options"][0]["id"]
    q = client.post(f"{base}/ask", headers=admin, json={"kind": "info", "note": "Passport names please"}).json()
    return t["id"], opt, q["questions"][0]["id"] if q.get("questions") else 1


def test_staff_of_another_company_get_nothing(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="admin@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    for c in (a, b):
        switch(client, owner, c["id"], **{k: True for k in ADDONS})
    tid, opt, qid = staff_request(client, admin_a)
    staff_request(client, admin_b, name="Beta Guest", place="Tbilisi")

    tries = [
        ("GET", f"/api/tickets/{tid}", None),
        ("POST", f"/api/tickets/{tid}/workflow/done", {"key": "intake"}),
        ("PUT", f"/api/tickets/{tid}/workflow", {"steps": [{"key": "intake", "type": "intake", "label_en": "Details"}]}),
        ("POST", f"/api/tickets/{tid}/close", {"by": "team", "reason": "not needed"}),
        ("POST", f"/api/tickets/{tid}/remind", {}),
        ("POST", f"/api/tickets/{tid}/ask", {"kind": "info", "note": "hi"}),
        ("POST", f"/api/tickets/{tid}/questions/{qid}/answer", {"answer": "x"}),
        ("PUT", f"/api/tickets/{tid}/options/{opt}/presentation", {"photos": []}),
        ("PUT", f"/api/tickets/{tid}/quotation", {"intro": "x"}),
        ("POST", f"/api/tickets/{tid}/quotation/ai-details", {}),
        ("PUT", f"/api/tickets/{tid}/workflow/intake/appointment", {"starts_at": "2030-01-01T10:00:00"}),
        ("POST", f"/api/tickets/{tid}/workflow/intake/confirm", {}),
    ]
    for method, url, body in tries:
        r = client.request(method, url, headers=admin_b, json=body)
        assert r.status_code == 404, (method, url, r.status_code, r.text)
        assert "secret plan of Private" not in r.text and "Private Client" not in r.text

    # Lists, plans, figures and broadcasts only ever show the caller's own company.
    for url in ("/api/tickets", "/api/tickets/team", "/api/tickets/plan", "/api/tickets/sla", "/api/broadcasts",
                "/api/notifications", "/api/insights?levels=basic,marketing,deep,finance"):
        r = client.get(url, headers=admin_b)
        assert r.status_code in (200, 404), (url, r.status_code)
        assert "Private Client" not in r.text and "Zanzibar" not in r.text and "secret plan of Private" not in r.text, url

    # Marking "all read" in one company leaves the other company's bell alone.
    before = client.get("/api/notifications", headers=admin_a).json()["unread"]
    client.post("/api/notifications/read", headers=admin_b, json={})
    assert client.get("/api/notifications", headers=admin_a).json()["unread"] == before


def test_business_partners_stay_apart(client, owner):
    s = setup_trip(client, owner)
    rid, admin = s["rid"], s["admin"]
    assert client.put(f"/api/partner/jobs/{rid}/payment-plan", headers=s["v_h"],
                      json={"steps": [{"label": "All", "percent": 100}]}).status_code == 200
    step = client.get(f"/api/b2b/requests/{rid}", headers=admin).json()["payment_plan"][0]["id"]

    # Another client and another vendor of the same travel company.
    cl2 = add_partner(client, admin, name="Other Client", features=["client.requests", "client.reports", "client.payments"]).json()
    _, cl2_h = add_login(client, admin, cl2["id"], email="boss@other.example")
    v2 = add_partner(client, admin, kind="vendor", name="Other Vendor",
                     features=["vendor.requests", "vendor.quotes", "vendor.payments", "vendor.history"]).json()
    _, v2_h = add_login(client, admin, v2["id"], email="ops@othervendor.example")
    for method, url, body, who in [
        ("GET", f"/api/partner/requests/{rid}", None, cl2_h),
        ("POST", f"/api/partner/requests/{rid}/changes", {"note": "change it"}, cl2_h),
        ("POST", f"/api/partner/requests/{rid}/rating", {"rating": 1}, cl2_h),
        ("GET", f"/api/partner/jobs/{rid}", None, v2_h),
        ("PUT", f"/api/partner/jobs/{rid}/payment-plan", {"steps": [{"label": "All", "percent": 100}]}, v2_h),
        # A client cannot use the vendor's endpoints, nor the staff ones.
        ("PUT", f"/api/partner/jobs/{rid}/payment-plan", {"steps": [{"label": "All", "percent": 100}]}, s["cl_h"]),
        ("POST", f"/api/b2b/requests/{rid}/payments/{step}", {"side": "client", "paid": True}, s["cl_h"]),
        ("GET", "/api/b2b/stats", None, s["v_h"]),
    ]:
        r = client.request(method, url, headers=who, json=body)
        assert r.status_code in (403, 404), (method, url, r.status_code, r.text)
    assert client.get("/api/partner/stats", headers=cl2_h).json()["total"] == 0
    assert client.get("/api/partner/stats", headers=v2_h).json()["total"] == 0

    # Another travel company.
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="admin@beta.com")
    switch_on(client, owner, b["id"], features=list(B2B))
    for method, url, body in [
        ("GET", f"/api/b2b/requests/{rid}", None),
        ("PUT", f"/api/b2b/requests/{rid}/payment-plan", {"steps": [{"label": "All", "percent": 100}]}),
        ("POST", f"/api/b2b/requests/{rid}/payments/{step}", {"side": "client", "paid": True}),
    ]:
        assert client.request(method, url, headers=admin_b, json=body).status_code == 404, url
    figures = client.get("/api/b2b/stats", headers=admin_b).json()
    assert figures["requests"] == 0 and figures["clients"] == [] and figures["vendors"] == []
