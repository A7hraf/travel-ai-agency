"""Branding (colours, logo, customer page content), image uploads, dashboard analytics."""

import base64

from app.ai.llm import LLMResponse, ToolCall
from tests.conftest import future, login, make_company, make_package

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def upload(client, headers, data=PNG, content_type="image/png", path="/api/media"):
    return client.post(path, headers=headers, json={"content_type": content_type,
                                                    "data_base64": base64.b64encode(data).decode()})


def test_upload_and_serve_images(client, company_a):
    _, admin = company_a
    r = upload(client, admin)
    assert r.status_code == 201
    url = r.json()["url"]
    served = client.get(url)
    assert served.content == PNG and served.headers["content-type"] == "image/png"
    assert "immutable" in served.headers["cache-control"]
    assert "sandbox" in served.headers["content-security-policy"]
    assert served.headers["x-content-type-options"] == "nosniff"


def test_only_real_images_are_accepted(client, company_a):
    _, admin = company_a
    assert upload(client, admin, b"<svg onload=alert(1)>", "image/svg+xml").status_code == 415
    assert upload(client, admin, b"<html>not a png</html>", "image/png").status_code == 415
    assert upload(client, admin, JPEG, "image/png").status_code == 415  # content must match the type
    assert upload(client, admin, JPEG, "image/jpeg").status_code == 201
    too_big = b"\xff\xd8\xff" + b"\x00" * 2_600_000
    assert upload(client, admin, too_big, "image/jpeg").status_code in (413, 422)
    r = client.post("/api/media", headers=admin, json={"content_type": "image/png", "data_base64": "@@@"})
    assert r.status_code == 400


def test_upload_needs_rights(client, company_a):
    _, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "S", "password": "Password123", "role": "support"})
    support = login(client, "s@bluesky.com", "Password123")
    assert upload(client, support).status_code == 403
    assert client.post("/api/media", json={"content_type": "image/png", "data_base64": ""}).status_code == 401


def test_package_photo_must_belong_to_the_company(client, owner):
    _, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="a@alpha.com")
    _, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    url_a = upload(client, admin_a).json()["url"]
    pkg = make_package(client, admin_a, image_url=url_a)
    assert pkg["image_url"] == url_a
    body = {"title": "Trip", "destination": "x", "country": "x", "duration_days": 1, "price_per_person": 1,
            "image_url": url_a}
    assert client.post("/api/packages", headers=admin_b, json=body).status_code == 400
    body["image_url"] = "javascript:alert(1)"
    assert client.post("/api/packages", headers=admin_b, json=body).status_code == 422


def test_company_admin_brands_the_customer_page(client, company_a):
    company, admin = company_a
    logo = upload(client, admin).json()["url"]
    r = client.patch("/api/company/branding", headers=admin, json={
        "primary_color": "#7c2d12", "logo": logo, "hero_title_ar": "سافر معنا", "hero_title_en": "Travel with us",
        "sections": ["offers", "about", "offers", "contact"], "layout": "list",
        "dashboard_color": "#ff0000"})
    assert r.status_code == 200
    b = r.json()
    assert b["primary_color"] == "#7c2d12" and b["sections"] == ["offers", "about", "contact"]
    assert b["dashboard_color"] != "#ff0000"  # dashboard colours are for the platform owner only
    public = client.get(f"/api/public/companies/{company['slug']}").json()["branding"]
    assert public["logo"] == logo and public["hero_title_ar"] == "سافر معنا" and public["layout"] == "list"
    assert "dashboard_color" not in public
    for bad in ({"primary_color": "red; background:url(x)"}, {"sections": ["hacker"]},
                {"logo": "javascript:alert(1)"}, {"hero_title_en": "x" * 500}):
        assert client.patch("/api/company/branding", headers=admin, json=bad).status_code == 422


def test_platform_owner_sets_dashboard_colours(client, owner, company_a):
    company, admin = company_a
    logo = upload(client, owner, path=f"/api/system/companies/{company['id']}/media").json()["url"]
    r = client.patch(f"/api/system/companies/{company['id']}/branding", headers=owner, json={
        "dashboard_color": "#123456", "dashboard_sidebar": "#000000", "logo": logo})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=admin).json()
    assert me["company"]["branding"] == {"logo": logo, "dashboard_color": "#123456", "dashboard_sidebar": "#000000"}
    assert client.patch(f"/api/system/companies/{company['id']}/branding", headers=admin,
                        json={"dashboard_color": "#000000"}).status_code == 403


def test_branding_cannot_use_another_company_image(client, owner):
    _, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="a@alpha.com")
    _, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    url_a = upload(client, admin_a).json()["url"]
    assert client.patch("/api/company/branding", headers=admin_b, json={"logo": url_a}).status_code == 400


def test_dashboard_analytics(client, company_a, scripted):
    company, admin = company_a
    pkg = make_package(client, admin, title="Salalah", price_per_person=100)
    scripted([
        LLMResponse(None, [ToolCall("q", "quote_booking", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 2}),
            ToolCall("b", "create_booking_ticket", {
            "package_id": pkg["id"], "departure_date": future(30), "adults": 2,
            "lead_traveler_name": "Ali", "contact_phone": "+968"})]),
        LLMResponse("Booked."),
        LLMResponse("Hello"),
    ])
    slug = company["slug"]
    t1 = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{t1}/messages", json={"content": "book"})
    t2 = client.post(f"/api/public/companies/{slug}/chats", json={}).json()["token"]
    client.post(f"/api/public/companies/{slug}/chats/{t2}/messages", json={"content": "hi"})
    ticket = client.get("/api/tickets", headers=admin).json()[0]
    client.patch(f"/api/tickets/{ticket['id']}", headers=admin, json={"status": "paid", "payment_reference": "R1"})

    a = client.get("/api/dashboard/analytics", headers=admin, params={"days": 7}).json()
    assert a["days"] == 7 and len(a["daily"]) == 7 and a["currency"] == "OMR"
    assert sum(d["web"] for d in a["daily"]) == 2
    assert sum(d["bookings"] for d in a["daily"]) == 1 and a["daily"][-1]["booked_value"] == 200
    assert a["funnel"] == {"conversations": 2, "with_booking": 1, "paid_or_confirmed": 1}
    assert a["top_packages"] == [{"title": "Salalah", "bookings": 1, "value": 200}]
    assert a["handled_by_ai"] == 1 and a["handed_to_team"] == 1
    assert a["paid_value"] == 200
