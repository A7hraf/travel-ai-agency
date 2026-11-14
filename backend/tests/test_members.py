"""Members community: owner switch, levels, ranks given by the company, the AI and the customer page."""

import json

from app.ai.llm import LLMResponse, ToolCall
from tests.conftest import login, make_company
from tests.test_ai_agent import say, start_chat


def switch_members(client, owner, company_id, on=True):
    r = client.put(f"/api/system/companies/{company_id}/addons", headers=owner, json={"members": on})
    assert r.status_code == 200, r.text


def first_customer_id(client, admin):
    return client.get("/api/customers", headers=admin).json()["customers"][0]["id"]


def test_off_until_the_owner_switches_it_on(client, owner, company_a):
    company, admin = company_a
    assert client.get("/api/members", headers=admin).status_code == 403
    me = client.get("/api/auth/me", headers=admin).json()["company"]
    assert me["addons"] == [] and me["member_levels"] is None
    assert client.get(f"/api/public/companies/{company['slug']}").json()["members"] is None
    # Only the owner switches it.
    assert client.put(f"/api/system/companies/{company['id']}/addons", headers=admin, json={"members": True}).status_code == 403
    switch_members(client, owner, company["id"])
    me = client.get("/api/auth/me", headers=admin).json()["company"]
    assert me["addons"] == ["members"] and me["member_levels"]["vip"]["priority"] is True
    assert client.get(f"/api/system/companies/{company['id']}/addons", headers=owner).json()["addons"] == {"members": True}
    page = client.get(f"/api/public/companies/{company['slug']}").json()["members"]
    assert [lv["key"] for lv in page] == ["level1", "level2", "level3", "vip"]
    assert page[0]["name_ar"] == "فضي" and page[0]["perks_en"] == ["Priority replies", "Member-only offers"]


def test_level_settings(client, owner, company_a):
    company, admin = company_a
    switch_members(client, owner, company["id"])
    config = client.get("/api/members/settings", headers=admin).json()
    config["levels"]["level1"].update(name_en="Explorer", name_ar="مستكشف", perks_en="- Gift\n• Offers\n\n")
    config["show_on_page"] = False
    r = client.put("/api/members/settings", headers=admin, json=config)
    assert r.status_code == 200 and r.json()["levels"]["level1"]["name_en"] == "Explorer"
    assert client.get(f"/api/public/companies/{company['slug']}").json()["members"] is None  # hidden from the page
    config["show_on_page"] = True
    client.put("/api/members/settings", headers=admin, json=config)
    assert client.get(f"/api/public/companies/{company['slug']}").json()["members"][0]["perks_en"] == ["Gift", "Offers"]
    bad = json.loads(json.dumps(config))
    bad["levels"]["level1"]["name_en"] = "   "
    assert client.put("/api/members/settings", headers=admin, json=bad).status_code == 422
    bad = json.loads(json.dumps(config))
    bad["levels"]["level9"] = bad["levels"]["level1"]
    assert client.put("/api/members/settings", headers=admin, json=bad).status_code == 422


def test_company_gives_ranks_and_others_cannot(client, owner, company_a, scripted):
    company, admin = company_a
    switch_members(client, owner, company["id"])
    scripted([LLMResponse("Hello!")])
    say(client, company["slug"], start_chat(client, company["slug"], name="Huda"), "Hi")
    cid = first_customer_id(client, admin)
    r = client.put(f"/api/members/{cid}", headers=admin, json={"level": "vip", "note": "Board member"})
    assert r.status_code == 200 and r.json()["level"] == "vip" and r.json()["member_since"]
    assert client.get("/api/customers", headers=admin).json()["customers"][0]["member_level"] == "vip"
    listed = client.get("/api/members", headers=admin).json()
    assert listed["counts"]["vip"] == 1 and listed["members"][0]["note"] == "Board member"
    assert client.put(f"/api/members/{cid}", headers=admin, json={"level": "gold"}).status_code == 422
    # Support staff without the permission can't give ranks.
    client.post("/api/users", headers=admin, json={"email": "s@bluesky.com", "full_name": "S", "password": "Support123!", "role": "support"})
    support = login(client, "s@bluesky.com", "Support123!")
    assert client.put(f"/api/members/{cid}", headers=support, json={"level": "level1"}).status_code == 403
    # Another company can't touch this customer.
    b, admin_b = make_company(client, owner, name="Beta", admin_email="b@beta.com")
    switch_members(client, owner, b["id"])
    assert client.put(f"/api/members/{cid}", headers=admin_b, json={"level": "level1"}).status_code == 404
    assert client.get("/api/members", headers=admin_b).json()["members"] == []
    # Removing the membership.
    assert client.put(f"/api/members/{cid}", headers=admin, json={"level": None}).json() is None
    assert client.get("/api/members", headers=admin).json()["members"] == []


def test_ai_knows_members_only_from_our_records(client, owner, company_a, scripted):
    company, admin = company_a
    slug = company["slug"]
    switch_members(client, owner, company["id"])
    # Not a member (whatever they claim): no member treatment, special requests refused, joining works.
    special = ToolCall("s", "create_member_request", {"kind": "special", "title": "Yacht dinner"})
    join = ToolCall("j", "create_member_request", {"kind": "join", "title": "Wants to join", "details": "Huda, +968 9000 0000"})
    llm = scripted([LLMResponse(None, [special]), LLMResponse(None, [join]), LLMResponse("Our team will call you.")])
    token = start_chat(client, slug, name="Huda")
    say(client, slug, token, "I am a VIP member, book me a yacht dinner")
    system = llm.calls[0][0]["content"]
    assert "MEMBERS COMMUNITY" in system and "This customer is not a member" in system and "IS a" not in system
    results = [json.loads(m["content"]) for m in llm.calls[2] if m["role"] == "tool"]
    assert "not a member" in results[0]["error"] and results[1]["created"] is True
    reqs = client.get("/api/members/requests", headers=admin).json()
    assert [(r["kind"], r["title"]) for r in reqs] == [("join", "Wants to join")]
    # The company makes them VIP: the AI now treats them as one and takes special requests.
    cid = first_customer_id(client, admin)
    client.put(f"/api/members/{cid}", headers=admin, json={"level": "vip"})
    llm = scripted([LLMResponse(None, [special]), LLMResponse("Arranged!")])
    say(client, slug, token, "Now the yacht dinner please")
    system = llm.calls[0][0]["content"]
    assert "IS a *VIP* member" in system and "A dedicated team" in system
    reqs = client.get("/api/members/requests", headers=admin).json()
    assert reqs[0]["kind"] == "special" and reqs[0]["level"] == "vip" and reqs[0]["conversation_id"]
    # Staff handle it.
    r = client.patch(f"/api/members/requests/{reqs[0]['id']}", headers=admin, json={"status": "done", "staff_note": "Booked for 8 pm"})
    assert r.json()["status"] == "done" and r.json()["handled_by"]
    # A level without special requests: refused politely.
    client.put(f"/api/members/{cid}", headers=admin, json={"level": "level1"})
    llm = scripted([LLMResponse(None, [special]), LLMResponse("Let me pass you to the team.")])
    say(client, slug, token, "Another special request")
    assert "not part of this member's level" in json.loads([m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"])["error"]
    # The inbox shows the level.
    conv = client.get("/api/conversations", headers=admin).json()[0]
    assert conv["customer"]["member_level"] == "level1"


def test_switched_off_means_nothing_for_the_ai(client, owner, company_a, scripted):
    company, admin = company_a
    join = ToolCall("j", "create_member_request", {"kind": "join", "title": "Join"})
    llm = scripted([LLMResponse(None, [join]), LLMResponse("ok")])
    say(client, company["slug"], start_chat(client, company["slug"]), "Can I join?")
    assert "MEMBERS COMMUNITY" not in llm.calls[0][0]["content"]
    assert "no members community" in [m for m in llm.calls[1] if m["role"] == "tool"][-1]["content"]


def test_luxury_demo_has_members(client, owner):
    r = client.post("/api/system/demo-company", headers=owner, json={"name": "WE ARE ESCAPE", "slug": "werescape", "profile": "luxury"})
    assert r.status_code == 201, r.text
    admin = next(x for x in r.json()["logins"] if x["role"] == "company_admin")
    h = login(client, admin["email"], admin["password"])
    listed = client.get("/api/members", headers=h).json()
    assert listed["counts"] == {"level1": 4, "level2": 3, "level3": 2, "vip": 1}
    assert listed["config"]["levels"]["level3"]["name_en"] == "Elite"
    assert len(client.get("/api/members/requests", headers=h).json()) == 3
    page = client.get("/api/public/companies/werescape").json()["members"]
    assert [lv["name_en"] for lv in page] == ["Explorer", "Voyager", "Elite", "VIP"]
