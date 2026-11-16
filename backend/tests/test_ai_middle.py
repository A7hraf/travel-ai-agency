"""The AI between the team and the client: the conversation's language, requests opened early and kept up to date,
the team's questions asked by the AI, the client's preferences and history, packages priced on request, and the
website chat proving a WhatsApp number before showing earlier requests."""

import re
from datetime import date, timedelta

from app.ai.llm import LLMResponse, ToolCall
from tests.conftest import make_company
from tests.test_ai_agent import say, start_chat
from tests.test_requests_flow import PHONE, services, tool_results, wa, wa_say  # noqa: F401 (fixture)
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)

IN_30 = (date.today() + timedelta(days=30)).isoformat()


def hotel_card(sid, **answers):
    return ToolCall("c", "create_request", {"service_id": sid, "summary": "Hotel", "answers": {
        "destination": "Dubai", "depart_date": IN_30, "return_date": IN_30, "adults": "2", "rooms": "1",
        "full_name": "Omar", **answers}})


def test_updates_follow_the_clients_language(client, wa, scripted):
    company, admin, fake = wa
    sid = services(client, admin)["hotel"]["id"]
    llm = wa_say(client, "السلام عليكم، أبغى فندق في دبي", "wamid.l1", [LLMResponse(None, [hotel_card(sid)]), LLMResponse("تم")], scripted)
    assert "Arabic" in llm.calls[0][0]["content"]
    t = client.get("/api/tickets", headers=admin).json()[0]
    base = f"/api/tickets/{t['id']}"
    oid = client.post(f"{base}/options", headers=admin, json={"category": "hotel", "title": "Atlantis", "price": "900"}).json()["options"][0]["id"]
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]})
    assert "هذه خياراتك" in fake.sent[-1][2] and "Here are your options" not in fake.sent[-1][2]
    # The client asks for English: the updates switch, and stay English even if they write Arabic again.
    wa_say(client, "please reply in English", "wamid.l2", [LLMResponse("Sure!")], scripted)
    llm = wa_say(client, "شكرا", "wamid.l3", [LLMResponse("You're welcome")], scripted)
    assert "asked for replies in English" in llm.calls[0][0]["content"]
    client.post(f"{base}/client-answer", headers=admin, json={"action": "changes", "note": "cheaper"})
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [oid]})
    assert "Here are your options" in fake.sent[-1][2] and "هذه خياراتك" not in fake.sent[-1][2]


def test_the_request_opens_early_and_the_team_asks_through_the_ai(client, wa, scripted):
    company, admin, fake = wa
    sid = services(client, admin)["hotel"]["id"]
    partial = ToolCall("c", "create_request", {"service_id": sid, "summary": "A hotel", "answers": {"destination": "Dubai"}})
    llm = wa_say(client, "I want a hotel in Dubai", "wamid.q1", [LLMResponse(None, [partial]), LLMResponse("When?")], scripted)
    ref = tool_results(llm)[0]["reference"]
    t = client.get("/api/tickets", headers=admin).json()[0]
    assert t["current_step"]["type"] == "intake" and t["urgency"] is not None
    # The answers come one by one; the request moves to the team's review when they are all in.
    upd = ToolCall("u", "update_request", {"reference": ref, "answers": {"depart_date": IN_30, "return_date": IN_30, "adults": "2",
                                                                          "rooms": "1", "full_name": "Omar"}})
    llm = wa_say(client, "next month, 2 people", "wamid.q2", [LLMResponse(None, [upd]), LLMResponse("Thanks")], scripted)
    assert tool_results(llm)[0]["missing"] == []
    t = client.get("/api/tickets", headers=admin).json()[0]
    base = f"/api/tickets/{t['id']}"
    assert t["current_step"]["type"] == "review" and t["adults"] == 2
    # The team asks for something; the AI writes to the client in their language and keeps the question open.
    r = client.post(f"{base}/ask", headers=admin, json={"kind": "info", "note": "Which area of Dubai: Marina or Downtown?"})
    assert r.status_code == 200, r.text
    q = r.json()["questions"][0]
    assert q["answered_at"] is None and ref in fake.sent[-1][2] and "Marina or Downtown" in fake.sent[-1][2]
    assert client.post(f"{base}/ask", headers=admin, json={"kind": "info", "note": ""}).status_code == 422
    # The client answers in the chat: the AI sees the open question and records the answer for the team.
    ans = ToolCall("a", "answer_team_question", {"reference": ref, "question_id": q["id"], "answer": "Marina, near the beach"})
    llm = wa_say(client, "Marina please, near the beach", "wamid.q3", [LLMResponse(None, [ans]), LLMResponse("Noted!")], scripted)
    assert "OPEN QUESTIONS FROM OUR TEAM" in llm.calls[0][0]["content"] and f"{ref} question {q['id']}" in llm.calls[0][0]["content"]
    t = client.get(base, headers=admin).json()
    assert t["questions"][0]["answer"] == "Marina, near the beach" and t["questions"][0]["answered_at"]
    llm = wa_say(client, "thanks", "wamid.q4", [LLMResponse("Anytime")], scripted)
    assert "OPEN QUESTIONS FROM OUR TEAM" not in llm.calls[0][0]["content"]
    # A question answered on the phone is written down by the team.
    q2 = client.post(f"{base}/ask", headers=admin, json={"kind": "meeting"}).json()["questions"][-1]
    assert "which are not possible" in fake.sent[-1][2]
    t = client.post(f"{base}/questions/{q2['id']}/answer", headers=admin, json={"answer": "Sunday 10am"}).json()
    assert t["questions"][-1]["answer"] == "Sunday 10am" and "(for the client)" in t["questions"][-1]["answered_by"]
    # The client's rejection reasons go to the team as a question too.
    client.post(f"{base}/ask", headers=admin, json={"kind": "feedback", "note": "Budget?"})
    assert "what would you like instead" in fake.sent[-1][2]


def test_another_company_cant_ask_or_answer(client, wa, scripted, owner):
    company, admin, fake = wa
    sid = services(client, admin)["hotel"]["id"]
    wa_say(client, "hotel", "wamid.i1", [LLMResponse(None, [hotel_card(sid)]), LLMResponse("ok")], scripted)
    tid = client.get("/api/tickets", headers=admin).json()[0]["id"]
    q = client.post(f"/api/tickets/{tid}/ask", headers=admin, json={"note": "Which area?"}).json()["questions"][0]
    _, other = make_company(client, owner, name="Other Travel", admin_email="admin@other.com")
    sent = len(fake.sent)
    assert client.post(f"/api/tickets/{tid}/ask", headers=other, json={"note": "Your passport?"}).status_code == 404
    assert client.post(f"/api/tickets/{tid}/questions/{q['id']}/answer", headers=other, json={"answer": "x"}).status_code == 404
    assert len(fake.sent) == sent


def test_preferences_and_history_personalise_the_ai(client, wa, scripted):
    company, admin, _ = wa
    sid = services(client, admin)["hotel"]["id"]
    save = ToolCall("p", "save_client_preferences", {"preferences": {"airline": "Oman Air", "seat": "Aisle", "x": "ignored",
                                                                     "hotel_stars": "5 <script>"}})
    wa_say(client, "I always fly Oman Air, aisle seat", "wamid.p1", [LLMResponse(None, [save, hotel_card(sid)]), LLMResponse("Noted")], scripted)
    llm = wa_say(client, "hello again", "wamid.p2", [LLMResponse("Welcome back")], scripted)
    system = llm.calls[0][0]["content"]
    assert "Favourite airline: Oman Air" in system and "Seat (window, aisle, emergency exit…): Aisle" in system
    assert "<script>" not in system and "History: 1 requests" in system
    cid = client.get("/api/tickets", headers=admin).json()[0]["customer"]["id"]
    c = client.get(f"/api/customers/{cid}", headers=admin).json()
    assert c["preferences"] == {"airline": "Oman Air", "seat": "Aisle", "hotel_stars": "5 script"}
    assert c["history"]["requests"] == 1 and c["history"]["loyalty"] == "new" and c["preference_labels"]["meal"][1]
    # The team writes or removes preferences too.
    c = client.patch(f"/api/customers/{cid}", headers=admin, json={"preferences": {"meal": "Vegetarian", "seat": ""}}).json()
    assert c["preferences"] == {"airline": "Oman Air", "hotel_stars": "5 script", "meal": "Vegetarian"}
    t = client.get(f"/api/tickets/{client.get('/api/tickets', headers=admin).json()[0]['id']}", headers=admin).json()
    assert t["client_preferences"]["meal"] == "Vegetarian"


def test_packages_priced_on_request(client, wa, scripted):
    company, admin, _ = wa
    pkg = client.post("/api/packages", headers=admin, json={
        "title": "Formula 1 Abu Dhabi weekend", "destination": "Abu Dhabi", "country": "UAE", "duration_days": 3,
        "price_per_person": 900, "departure_dates": [IN_30], "price_mode": "on_request", "kind": "experience"}).json()
    assert pkg["price_mode"] == "on_request" and pkg["kind"] == "experience"
    public = client.get(f"/api/public/companies/{company['slug']}/packages").json()
    item = next(p for p in public if p["id"] == pkg["id"])
    assert item["price_per_person"] is None and item["kind"] == "experience"
    search = ToolCall("s", "search_packages", {"query": "Formula 1"})
    quote = ToolCall("q", "quote_booking", {"package_id": pkg["id"], "departure_date": IN_30, "adults": 2})
    llm = wa_say(client, "Formula 1 tickets?", "wamid.f1", [LLMResponse(None, [search, quote]), LLMResponse("Let me arrange it")], scripted)
    found, quoted = tool_results(llm)
    hit = next(p for p in found["results"] if p["id"] == pkg["id"])
    assert "price_per_person" not in hit and "on request" in hit["price"]
    assert "priced for each client" in quoted["error"]
    # The client likes it: a tailor-made request linked to the package.
    sid = services(client, admin)["custom_trip"]["id"]
    card = ToolCall("c", "create_request", {"service_id": sid, "package_id": pkg["id"], "summary": "F1 with paddock access",
                                            "answers": {"destination": "Abu Dhabi", "adults": "2"}})
    llm = wa_say(client, "yes, I like it", "wamid.f2", [LLMResponse(None, [card]), LLMResponse("Opened")], scripted)
    t = client.get("/api/tickets", headers=admin).json()[0]
    assert t["package_id"] == pkg["id"] and t["special_requests"].startswith('Based on the package "Formula 1 Abu Dhabi weekend"')


def test_website_chat_proves_the_number_before_showing_earlier_requests(client, wa, scripted):
    company, admin, fake = wa
    slug = company["slug"]
    sid = services(client, admin)["hotel"]["id"]
    wa_say(client, "hotel in Dubai", "wamid.w1", [LLMResponse(None, [hotel_card(sid)]), LLMResponse("Done")], scripted)
    ref = client.get("/api/tickets", headers=admin).json()[0]["reference"]
    token = start_chat(client, slug)
    # Before proving the number, the website chat sees nothing of the WhatsApp requests.
    llm = scripted([LLMResponse(None, [ToolCall("m", "my_requests", {})]), LLMResponse("Nothing yet")])
    say(client, slug, token, "what about my Dubai hotel?")
    assert tool_results(llm)[0]["requests"] == [] and "send_whatsapp_code" in llm.calls[0][0]["content"]
    # A code goes to the WhatsApp number; an unknown number gets the same answer and no message.
    sent_before = len(fake.sent)
    llm = scripted([LLMResponse(None, [ToolCall("v", "send_whatsapp_code", {"phone": "+968 9999 0000"})]), LLMResponse("ok")])
    say(client, slug, token, "+968 9999 0000")
    assert tool_results(llm)[0]["sent"] is True and len(fake.sent) == sent_before
    llm = scripted([LLMResponse(None, [ToolCall("v", "send_whatsapp_code", {"phone": "+" + PHONE})]), LLMResponse("ok")])
    say(client, slug, token, "+" + PHONE)
    code = re.search(r"\b(\d{6})\b", fake.sent[-1][2]).group(1)
    assert fake.sent[-1][1] == PHONE
    wrong = "000000" if code != "000000" else "111111"
    llm = scripted([LLMResponse(None, [ToolCall("c", "check_whatsapp_code", {"code": wrong})]), LLMResponse("Wrong")])
    say(client, slug, token, wrong)
    assert "wrong or expired" in tool_results(llm)[0]["error"]
    llm = scripted([LLMResponse(None, [ToolCall("c", "check_whatsapp_code", {"code": code}), ToolCall("m", "my_requests", {})]),
                    LLMResponse("Here it is")])
    say(client, slug, token, code)
    checked, mine = tool_results(llm)
    assert checked["verified"] is True and [r["reference"] for r in mine["requests"]] == [ref]
    # Another visitor's chat on the website still sees nothing.
    other = start_chat(client, slug)
    llm = scripted([LLMResponse(None, [ToolCall("m", "my_requests", {})]), LLMResponse("None")])
    say(client, slug, other, "my requests?")
    assert tool_results(llm)[0]["requests"] == []


def test_the_welcome_lists_the_services(client, wa):
    company, admin, _ = wa
    msg = client.post(f"/api/public/companies/{company['slug']}/chats", json={"lang": "en"}).json()["messages"][0]["content"]
    assert "I can help you with: Holiday packages, Tailor-made trip, Flight tickets" in msg
    info = client.get(f"/api/public/companies/{company['slug']}").json()
    assert "Embassy appointment" in info["welcome_message"]
