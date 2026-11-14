"""Story sections of the customer page: The Brand, Experiences, Services, Leadership, The Community."""

import re
from pathlib import Path

from app.branding import MAX_STORY_ITEMS, SECTIONS, STORY_SECTIONS, Branding, branding_image_urls
from app.services.demo_luxury import branding_for
from tests.conftest import make_company
from tests.test_page_editor import public, upload

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def card(title="Mission", **extra):
    return {"title_en": title, "title_ar": "الرسالة", "text_en": "Effortless travel.", "text_ar": "سفر سهل.", **extra}


def test_story_keys_match_the_frontend():
    stories = (FRONTEND / "components/storefront/Stories.tsx").read_text()
    keys = re.search(r"STORY_KEYS: StoryKey\[\] = \[([^\]]+)\]", stories)[1]
    assert tuple(re.findall(r'"(\w+)"', keys)) == STORY_SECTIONS


def test_off_by_default_and_old_designs_keep_working():
    assert Branding().sections == list(SECTIONS)
    assert Branding().stories == {}
    assert Branding.model_validate({"sections": ["search", "about"]}).stories == {}


def test_save_and_show_both_languages(client, company_a):
    company, admin = company_a
    r = client.patch("/api/company/branding", headers=admin, json={
        "sections": ["search", "brand", "experiences", "offers"],
        "stories": {
            "brand": {"title_en": "The Brand", "title_ar": "البراند", "items": [card(), card("Philosophy")]},
            "experiences": {"intro_en": "In Oman\r\nand beyond", "items": [card("Hiking", tag_en="Inside Oman", tag_ar="داخل عُمان")]},
        }})
    assert r.status_code == 200, r.text
    b = public(client, company["slug"])
    assert b["sections"] == ["search", "brand", "experiences", "offers"]
    assert [i["title_en"] for i in b["stories"]["brand"]["items"]] == ["Mission", "Philosophy"]
    assert b["stories"]["brand"]["items"][0]["text_ar"] == "سفر سهل."
    assert b["stories"]["experiences"]["intro_en"] == "In Oman\nand beyond"
    assert b["stories"]["experiences"]["items"][0]["tag_ar"] == "داخل عُمان"
    # A section sent replaces the saved one; the others are kept.
    client.patch("/api/company/branding", headers=admin, json={"stories": {"brand": {"title_en": "New"}}})
    b = public(client, company["slug"])
    assert b["stories"]["brand"]["title_en"] == "New" and b["stories"]["brand"]["items"] == []
    assert b["stories"]["experiences"]["items"][0]["title_en"] == "Hiking"
    # Other changes keep the stories.
    client.patch("/api/company/branding", headers=admin, json={"primary_color": "#112233"})
    assert public(client, company["slug"])["stories"]["experiences"]["items"]


def test_limits_and_unknown_fields(client, company_a):
    _, admin = company_a
    bad = [
        {"stories": {"footer": {"title_en": "x"}}},
        {"stories": {"brand": {"hack": "x"}}},
        {"stories": {"brand": {"items": [card(hack="x")]}}},
        {"stories": {"brand": {"title_en": "x" * 121}}},
        {"stories": {"brand": {"items": [card(text_en="x" * 1501)]}}},
        {"stories": {"brand": {"items": [card() for _ in range(MAX_STORY_ITEMS + 1)]}}},
        {"stories": {"brand": {"image": "javascript:alert(1)"}}},
        {"stories": {"brand": {"items": [card(image="http://x/y.png")]}}},
    ]
    for body in bad:
        assert client.patch("/api/company/branding", headers=admin, json=body).status_code == 422, body
    ok = {"stories": {"brand": {"items": [card() for _ in range(MAX_STORY_ITEMS)]}}}
    assert client.patch("/api/company/branding", headers=admin, json=ok).status_code == 200


def test_control_characters_are_removed(client, company_a):
    company, admin = company_a
    client.patch("/api/company/branding", headers=admin, json={
        "stories": {"services": {"title_en": "Vi‮sas\x07", "items": [card("Fli⁦ghts\nnow")]}}})
    s = public(client, company["slug"])["stories"]["services"]
    assert s["title_en"] == "Visas" and s["items"][0]["title_en"] == "Flights now"


def test_story_photos_must_belong_to_the_company(client, owner):
    a, admin_a = make_company(client, owner, name="Alpha Travel", admin_email="a@alpha.com")
    b, admin_b = make_company(client, owner, name="Beta Travel", admin_email="b@beta.com")
    url_a = upload(client, admin_a)
    for body in ({"stories": {"leadership": {"image": url_a}}},
                 {"stories": {"leadership": {"items": [card(image=url_a)]}}}):
        assert client.patch("/api/company/branding", headers=admin_b, json=body).status_code == 400
        assert client.patch(f"/api/system/companies/{b['id']}/branding", headers=owner, json=body).status_code == 400
    r = client.patch("/api/company/branding", headers=admin_a, json={"stories": {"leadership": {"items": [card(image=url_a)]}}})
    assert r.status_code == 200
    assert public(client, a["slug"])["stories"]["leadership"]["items"][0]["image"] == url_a


def test_story_photos_are_kept_by_the_cleanup():
    saved = {"logo": "/api/media/1", "stories": {"brand": {"image": "/api/media/2", "items": [{"image": "/api/media/3"}, {}]}}}
    assert branding_image_urls(saved) == {"/api/media/1", "/api/media/2", "/api/media/3"}


def test_luxury_demo_has_every_story_section():
    b = Branding.model_validate(branding_for("WE ARE ESCAPE"))
    assert set(b.stories) == set(STORY_SECTIONS)
    assert all(key in b.sections for key in STORY_SECTIONS)
    for key, section in b.stories.items():
        assert section.title_en and section.title_ar and section.items, key
        for item in section.items:
            assert item.title_en and item.title_ar and item.text_en and item.text_ar, (key, item.title_en)
    tags = {i.tag_en for i in b.stories["experiences"].items}
    assert tags == {"Inside Oman", "Around the world"}
    leader = b.stories["leadership"].items[0]
    assert leader.title_en == "KHAMIS ALSUBHI" and "WE ARE ESCAPE" in leader.text_en and "WE ARE ESCAPE" in leader.text_ar
    assert len(b.stories["community"].items) == 4 and b.stories["community"].items[-1].title_en == "VIP"
