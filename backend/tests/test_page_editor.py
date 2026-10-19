"""Customer page editor: texts per language, colours, sections, hidden parts, photos, package cards."""

import base64
import re
from pathlib import Path

from app.branding import TEXT_KEYS, Branding, get_branding
from app.database import SessionLocal
from app.models import Company
from tests.conftest import make_company

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def upload(client, headers, path="/api/media"):
    r = client.post(path, headers=headers, json={"content_type": "image/png", "data_base64": base64.b64encode(PNG).decode()})
    assert r.status_code == 201, r.text
    return r.json()["url"]


def public(client, slug):
    return client.get(f"/api/public/companies/{slug}").json()["branding"]


def set_raw_branding(company_id, data):
    with SessionLocal() as db:
        db.get(Company, company_id).branding = data
        db.commit()


# --- Text keys stay in step with the frontend ------------------------------------------------------

def test_text_keys_match_the_frontend():
    editor_keys = set(re.findall(r'f\("(\w+)"', (FRONTEND / "components/storefront/texts.ts").read_text()))
    assert editor_keys == set(TEXT_KEYS)
    i18n = (FRONTEND / "i18n.ts").read_text()
    en = i18n[i18n.index("  en: {"):i18n.index("  ar: {")]
    entries = set(re.findall(r"^    (\w+):", en, re.M))
    for key in TEXT_KEYS:
        base = re.sub(r"^(trust|cat)\d$", lambda m: {"trust": "trust", "cat": "categories"}[m[1]], key)
        base = re.sub(r"^how\d(Title|Text)$", "how", base)
        assert base in entries, key


# --- Texts -------------------------------------------------------------------------------------------

def test_texts_in_both_languages(client, company_a):
    company, admin = company_a
    r = client.patch("/api/company/branding", headers=admin, json={"texts": {
        "en": {"featuredTitle": "  Hot deals ", "heroB": "now!", "welcome": "Hi from {agent}\nat {company}"},
        "ar": {"featuredTitle": "عروض حارة", "book": ""},
    }})
    assert r.status_code == 200, r.text
    texts = public(client, company["slug"])["texts"]
    assert texts["en"] == {"featuredTitle": "Hot deals", "heroB": "now!", "welcome": "Hi from {agent}\nat {company}"}
    assert texts["ar"] == {"featuredTitle": "عروض حارة"}  # empty = standard text
    # Sending one language leaves the other one alone; an empty object resets it.
    client.patch("/api/company/branding", headers=admin, json={"texts": {"en": {}}})
    texts = public(client, company["slug"])["texts"]
    assert texts["en"] == {} and texts["ar"] == {"featuredTitle": "عروض حارة"}


def test_text_whitelist_and_limits(client, company_a):
    _, admin = company_a
    for bad in ({"en": {"notAKey": "x"}}, {"en": {"days": "x"}}, {"fr": {"book": "x"}},
                {"en": {"book": "x" * (TEXT_KEYS["book"] + 1)}}, {"en": {"book": 5}}, {"en": "text"}):
        r = client.patch("/api/company/branding", headers=admin, json={"texts": bad})
        assert r.status_code == 422, bad
    ok = client.patch("/api/company/branding", headers=admin, json={"texts": {"en": {"welcome": "x" * TEXT_KEYS["welcome"]}}})
    assert ok.status_code == 200


def test_control_characters_are_removed(client, company_a):
    company, admin = company_a
    client.patch("/api/company/branding", headers=admin, json={
        "texts": {"en": {"book": "Bo\x00ok‮ now\n!", "how1Text": "Line 1\r\nLine\x07 2"}},
        "hero_title_en": "Sea\x1b\nside", "about_en": "We\x00 travel\nwith you"})
    b = public(client, company["slug"])
    assert b["texts"]["en"]["book"] == "Book now !"  # one-line texts lose their line breaks
    assert b["texts"]["en"]["how1Text"] == "Line 1\nLine 2"
    assert b["hero_title_en"] == "Sea side" and b["about_en"] == "We travel\nwith you"


def test_chat_welcome_text_is_used_by_the_server(client, company_a):
    company, admin = company_a
    client.patch("/api/company/branding", headers=admin, json={"texts": {
        "en": {"welcome": "Hello, {agent} from {company} here"}, "ar": {"welcome": "مرحبا من {company}"}}})
    slug = company["slug"]
    en = client.post(f"/api/public/companies/{slug}/chats", json={"lang": "en"}).json()["messages"][0]["content"]
    ar = client.post(f"/api/public/companies/{slug}/chats", json={"lang": "ar"}).json()["messages"][0]["content"]
    assert en.startswith("Hello, ") and company["name"] in en and "{agent}" not in en
    assert ar == f"مرحبا من {company['name']}"


# --- Colours -----------------------------------------------------------------------------------------

def test_colours(client, company_a):
    company, admin = company_a
    r = client.patch("/api/company/branding", headers=admin, json={
        "bg_color": "#f5f1ea", "surface_color": "#ffffff", "text_color": "#1b1b1b", "highlight_color": "#c2185b"})
    assert r.status_code == 200
    b = public(client, company["slug"])
    assert (b["bg_color"], b["surface_color"], b["text_color"], b["highlight_color"]) == ("#f5f1ea", "#ffffff", "#1b1b1b", "#c2185b")
    for bad in ("red", "#fff", "#12345g", "url(x)"):
        assert client.patch("/api/company/branding", headers=admin, json={"bg_color": bad}).status_code == 422
    # null / empty = back to the standard colour
    client.patch("/api/company/branding", headers=admin, json={"bg_color": None, "text_color": ""})
    b = public(client, company["slug"])
    assert b["bg_color"] is None and b["text_color"] is None and b["surface_color"] == "#ffffff"


# --- Structure and hidden parts ------------------------------------------------------------------------

def test_sections_and_hidden_elements(client, company_a):
    company, admin = company_a
    r = client.patch("/api/company/branding", headers=admin, json={
        "sections": ["about", "how", "offers"], "elements": {"trust": False, "chips": False, "budget_filter": False}})
    assert r.status_code == 200
    b = public(client, company["slug"])
    assert b["sections"] == ["about", "how", "offers"]
    assert b["elements"]["trust"] is False and b["elements"]["chips"] is False and b["elements"]["lang_switch"] is True
    # elements merge key by key
    client.patch("/api/company/branding", headers=admin, json={"elements": {"trust": True}})
    b = public(client, company["slug"])
    assert b["elements"]["trust"] is True and b["elements"]["chips"] is False
    assert client.patch("/api/company/branding", headers=admin, json={"elements": {"hack": False}}).status_code == 422
    assert client.patch("/api/company/branding", headers=admin, json={"sections": ["footer"]}).status_code == 422


def test_only_the_platform_owner_hides_powered_by(client, owner, company_a):
    company, admin = company_a
    client.patch("/api/company/branding", headers=admin, json={"elements": {"powered_by": False, "kicker": False}})
    b = public(client, company["slug"])
    assert b["elements"]["powered_by"] is True and b["elements"]["kicker"] is False
    r = client.patch(f"/api/system/companies/{company['id']}/branding", headers=owner, json={"elements": {"powered_by": False}})
    assert r.status_code == 200
    assert public(client, company["slug"])["elements"]["powered_by"] is False
    # The admin saving the whole design again does not bring it back, nor hide it on their own.
    client.patch("/api/company/branding", headers=admin, json={"elements": {"powered_by": True, "kicker": True}})
    assert public(client, company["slug"])["elements"]["powered_by"] is False


# --- Package cards -------------------------------------------------------------------------------------

def test_package_card_design(client, company_a):
    company, admin = company_a
    r = client.patch("/api/company/branding", headers=admin, json={"cards": {
        "style": "photo", "columns": 4, "show_hotel": True, "show_seats": True, "per_person": True, "show_button": False}})
    assert r.status_code == 200
    cards = public(client, company["slug"])["cards"]
    assert cards["style"] == "photo" and cards["columns"] == 4 and cards["show_hotel"] and not cards["show_button"]
    assert cards["show_price"] is True  # untouched keys keep their value
    for bad in ({"style": "fancy"}, {"columns": 5}, {"columns": "3; x"}, {"show_price": "maybe"}, {"unknown": True}):
        assert client.patch("/api/company/branding", headers=admin, json={"cards": bad}).status_code == 422, bad
    # The old "layout" field follows the card style, and older clients can still switch it.
    client.patch("/api/company/branding", headers=admin, json={"cards": {"style": "compact"}})
    assert public(client, company["slug"])["layout"] == "list"
    client.patch("/api/company/branding", headers=admin, json={"layout": "grid"})
    b = public(client, company["slug"])
    assert b["layout"] == "grid" and b["cards"]["style"] == "poster"


# --- Photos --------------------------------------------------------------------------------------------

def test_section_photos(client, company_a):
    company, admin = company_a
    about, how = upload(client, admin), upload(client, admin)
    r = client.patch("/api/company/branding", headers=admin, json={"about_image": about, "how_bg_image": how, "about_bg_image": about})
    assert r.status_code == 200
    b = public(client, company["slug"])
    assert b["about_image"] == about and b["how_bg_image"] == how and b["about_bg_image"] == about
    assert client.patch("/api/company/branding", headers=admin, json={"about_image": "javascript:alert(1)"}).status_code == 422
    assert client.patch("/api/company/branding", headers=admin, json={"how_bg_image": "http://x/y.png"}).status_code == 422


def test_photos_must_belong_to_the_company(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="a@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    url_a = upload(client, admin_a)
    url_b_owner = upload(client, owner, path=f"/api/system/companies/{b['id']}/media")
    for field in ("about_image", "about_bg_image", "how_bg_image", "hero_image", "logo"):
        # Company B's admin can't use company A's photo …
        assert client.patch("/api/company/branding", headers=admin_b, json={field: url_a}).status_code == 400, field
        # … and the platform owner can't put A's photo on B's page.
        r = client.patch(f"/api/system/companies/{b['id']}/branding", headers=owner, json={field: url_a})
        assert r.status_code == 400, field
    assert client.patch(f"/api/system/companies/{b['id']}/branding", headers=owner, json={"about_image": url_b_owner}).status_code == 200
    assert client.patch("/api/company/branding", headers=admin_a, json={"about_image": url_b_owner}).status_code == 400
    assert public(client, a["slug"])["about_image"] is None
    assert public(client, b["slug"])["about_image"] == url_b_owner


# --- Old saved designs and the public API ---------------------------------------------------------------

def test_old_saved_design_keeps_working(client, company_a):
    company, admin = company_a
    old = {"primary_color": "#7c2d12", "accent_color": "#4fb6dc", "logo": None, "hero_style": "solid",
           "hero_title_en": "Old title", "sections": ["search", "offers", "featured", "about"], "card_style": "square",
           "layout": "list", "dashboard_color": "#123456", "dashboard_sidebar": "#000000"}
    set_raw_branding(company["id"], old)
    b = public(client, company["slug"])
    assert b["primary_color"] == "#7c2d12" and b["hero_title_en"] == "Old title" and b["card_style"] == "square"
    # "How booking works" was always shown after the trips.
    assert b["sections"] == ["search", "offers", "featured", "how", "about"]
    assert b["cards"]["style"] == "compact" and b["cards"]["show_hotel"] and b["layout"] == "list"
    assert b["texts"] == {"en": {}, "ar": {}} and b["elements"]["trust"] is True and b["bg_color"] is None
    # After a save the design is stored in the new form; turning "how" off sticks.
    client.patch("/api/company/branding", headers=admin, json={"sections": ["offers", "about"]})
    assert public(client, company["slug"])["sections"] == ["offers", "about"]
    assert client.get("/api/company/branding", headers=admin).json()["dashboard_color"] == "#123456"


def test_one_bad_value_does_not_reset_the_design(client, company_a):
    company, _ = company_a
    set_raw_branding(company["id"], {"version": 2, "primary_color": "#7c2d12", "texts": {"en": {"gone": "x", "book": "Go"}}})
    with SessionLocal() as db:
        b = get_branding(db.get(Company, company["id"]))
    assert b.primary_color == "#7c2d12"  # the bad texts are dropped, the colour is kept
    assert Branding().sections == ["search", "featured", "offers", "how", "about", "contact"]


def test_public_api_exposes_only_the_page(client, company_a):
    company, _ = company_a
    b = public(client, company["slug"])
    assert "dashboard_color" not in b and "dashboard_sidebar" not in b and "version" not in b
    assert {"texts", "elements", "cards", "about_image", "bg_color"} <= set(b)


def test_page_editor_needs_rights(client, company_a):
    company, admin = company_a
    client.post("/api/users", headers=admin, json={
        "email": "s@bluesky.com", "full_name": "S", "password": "Password123", "role": "support"})
    from tests.conftest import login
    support = login(client, "s@bluesky.com", "Password123")
    assert client.patch("/api/company/branding", headers=support, json={"texts": {"en": {"book": "x"}}}).status_code == 403
    assert client.patch(f"/api/system/companies/{company['id']}/branding", headers=admin, json={}).status_code == 403
