"""Customer-page features the platform owner gives a company: the editorial design and the extra brand sections;
the design options every company has (tagline, prices on request); and the luxury concierge services pack."""

import pytest

from tests.conftest import make_company
from tests.test_library import switch
from tests.test_requests_flow import PHONE, services, wa  # noqa: F401 (fixture)
from tests.test_use_cases import ANSWERS, drive
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

MISSION = {"kicker_en": "The mission", "title_en": "Travel *better*", "intro_en": "To simplify frequent travel.", "items": []}
FAQ = {"title_en": "Questions?", "items": [{"title_en": "Do you publish prices?", "text_en": "Prices are given on request."}]}
PACK = {"villa", "private_jet", "yacht", "cruise", "dining", "vip_events", "car_rental"}


def page(client, slug):
    return client.get(f"/api/public/companies/{slug}").json()


def test_editorial_and_more_sections_follow_the_features(client, owner):
    company, admin = make_company(client, owner)
    r = client.patch("/api/company/branding", headers=admin, json={
        "template": "editorial", "tagline_en": "The modern travel brand", "tagline_ar": "علامة السفر الحديثة",
        "sections": ["brand", "mission", "faq", "about"], "stories": {"mission": MISSION, "faq": FAQ},
        "cards": {"price_on_request": True}, "texts": {"en": {"edCta": "Start planning", "edClosing": "Every journey, *tailored to you*."}}})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["template"] == "editorial" and saved["stories"]["mission"]["title_en"] == "Travel *better*"

    # Prepared before the features are on: the page stays classic and hides the extra sections.
    p = page(client, company["slug"])
    assert p["page_features"] == []
    b = p["branding"]
    assert b["template"] == "classic" and "mission" not in b["sections"] and "faq" not in b["stories"]
    assert b["tagline_en"] == "The modern travel brand" and b["cards"]["price_on_request"] is True
    assert b["texts"]["en"]["edCta"] == "Start planning"

    switch(client, owner, company["id"], page_editorial=True, page_more_sections=True)
    p = page(client, company["slug"])
    assert sorted(p["page_features"]) == ["page_editorial", "page_more_sections"]
    b = p["branding"]
    assert b["template"] == "editorial" and b["sections"] == ["brand", "mission", "faq", "about"]
    assert b["stories"]["faq"]["items"][0]["text_en"] == "Prices are given on request."

    # Taken back: the saved design is kept, the page goes back to classic.
    switch(client, owner, company["id"], page_editorial=False)
    assert page(client, company["slug"])["branding"]["template"] == "classic"
    assert client.get("/api/company/branding", headers=admin).json()["template"] == "editorial"


@pytest.mark.parametrize("body", [{"template": "magazine"}, {"tagline_en": "x" * 81}, {"stories": {"faq": {"items": [{"title_en": "x" * 121}]}}}])
def test_bad_design_values_are_refused(client, owner, body):
    _, admin = make_company(client, owner)
    assert client.patch("/api/company/branding", headers=admin, json=body).status_code == 422


def test_concierge_pack_comes_and_goes_with_the_feature(client, owner):
    company, admin = make_company(client, owner)
    keys = lambda: {s["key"] for s in client.get("/api/services", headers=admin).json() if s["is_active"]}  # noqa: E731
    assert not keys() & PACK
    switch(client, owner, company["id"], concierge_services=True)
    assert PACK <= keys()
    switch(client, owner, company["id"], concierge_services=False)
    assert not keys() & PACK
    # Switched off, not deleted: on again gives the same services back, once each.
    switch(client, owner, company["id"], concierge_services=True)
    all_keys = [s["key"] for s in client.get("/api/services", headers=admin).json()]
    assert PACK <= keys() and all(all_keys.count(k) == 1 for k in PACK)


@pytest.mark.parametrize("key", sorted(PACK))
def test_each_luxury_service_runs_to_the_end(client, owner, wa, key):  # noqa: F811
    company, admin, _ = wa
    switch(client, owner, company["id"], concierge_services=True)
    answers = ANSWERS | {"days": "3", "bedrooms": "2", "cabin": "With a driver", "details": "Table for 4 at 9pm"}
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)[key]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": answers, "summary": "Use case"})
    assert r.status_code == 201, r.text
    t, seen = drive(client, admin, f"/api/tickets/{r.json()['id']}", key)
    assert t["status"] == "completed", (key, seen)


def test_prices_on_request_hide_every_price(client, owner):
    from datetime import date

    from app.ai.tools import ToolContext, run_tool
    from app.database import SessionLocal
    from app.models import Company, Conversation, Customer
    from tests.conftest import make_package

    company, admin = make_company(client, owner)
    pkg = make_package(client, admin, title="Maldives Villa", destination="Maldives", price_per_person=2400)

    def ai_sees():
        with SessionLocal() as db:
            c = db.get(Company, company["id"])
            customer = Customer(company_id=c.id)
            db.add(customer)
            db.flush()
            conv = Conversation(company_id=c.id, customer_id=customer.id, channel="web")
            db.add(conv)
            db.flush()
            ctx = ToolContext(db=db, company=c, conversation=conv, customer=customer, today=date.today())
            found = run_tool(ctx, "search_packages", {"query": "Maldives"})["results"][0]
            booking = run_tool(ctx, "get_package_details", {"package_id": pkg["id"]})
            db.rollback()
        return found, booking

    found, _ = ai_sees()
    assert found["price_per_person"]
    assert client.get(f"/api/public/companies/{company['slug']}/packages").json()[0]["price_per_person"]

    client.patch("/api/company/branding", headers=admin, json={"cards": {"price_on_request": True}})
    assert client.get(f"/api/public/companies/{company['slug']}/packages").json()[0]["price_per_person"] is None
    found, details = ai_sees()
    assert "price_per_person" not in found and "on request" in found["price"]
    assert "2400" not in str(details) and "2,400" not in str(details)
