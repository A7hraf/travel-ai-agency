"""Live travel data in the AI's recommendations: real hotels, flights and activities with prices, photos,
features and booking links. Central keys set by the platform owner; a company may get its own key, which it
then uses. Companies see their searches left, never a key. No real network: the providers are stubbed."""

import json

import httpx
import pytest

from app.ai.llm import LLMResponse
from app.services import live_data
from tests.conftest import make_company
from tests.test_ai_brain import custom_request, draft_reply, opt, switch

HOTELS = {"search_metadata": {"google_hotels_url": "https://www.google.com/travel/hotels/zanzibar"}, "properties": [
    {"name": "Zuri Zanzibar", "link": "https://www.zurizanzibar.com/", "overall_rating": 4.7, "reviews": 1234,
     "extracted_hotel_class": 5, "amenities": ["Pool", "Spa", "Beach access", "Free Wi-Fi"],
     "rate_per_night": {"extracted_lowest": 310}, "total_rate": {"extracted_lowest": 2170},
     "images": [{"original_image": "https://img.example/zuri1.jpg"}, {"thumbnail": "https://img.example/zuri2.jpg"}],
     "prices": [{"source": "Booking.com"}, {"source": "Expedia"}]},
    {"name": "Baraza Resort", "overall_rating": 4.5, "reviews": 800, "extracted_hotel_class": 5,
     "total_rate": {"extracted_lowest": 3100}, "images": [{"original_image": "https://img.example/baraza.jpg"}]},
    {"name": "No price hotel"},
]}
FLIGHTS = {"search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?q=MCT-ZNZ"}, "best_flights": [
    {"price": 410, "total_duration": 545, "airline_logo": "https://img.example/wy.png", "layovers": [{"name": "Dar es Salaam", "duration": 90}],
     "flights": [{"airline": "Oman Air", "flight_number": "WY 721", "departure_airport": {"id": "MCT", "time": "2030-02-10 08:10"},
                  "arrival_airport": {"id": "DAR", "time": "2030-02-10 12:30"}, "travel_class": "Economy"},
                 {"airline": "Precision Air", "flight_number": "PW 450", "departure_airport": {"id": "DAR", "time": "2030-02-10 14:00"},
                  "arrival_airport": {"id": "ZNZ", "time": "2030-02-10 14:25"}}]}]}
VIATOR = {"products": {"totalCount": 1, "results": [
    {"productCode": "123P1", "title": "Stone Town walking tour", "productUrl": "https://www.viator.com/tours/123P1",
     "images": [{"variants": [{"url": "https://img.example/st-small.jpg", "width": 200}, {"url": "https://img.example/st.jpg", "width": 720}]}],
     "reviews": {"totalReviews": 950, "combinedAverageRating": 4.83}, "pricing": {"summary": {"fromPrice": 35}, "currency": "USD"},
     "duration": {"fixedDurationInMinutes": 180}, "description": "Old town, spice market"}]}}


class Providers:
    """Stands in for SerpApi and Viator; remembers which key each search used."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kw):
        key = (kw.get("params") or {}).get("api_key") or (kw.get("headers") or {}).get("exp-api-key")
        if "account" in url:
            return httpx.Response(200, json={"total_searches_left": 241, "searches_per_month": 250, "this_month_usage": 9})
        engine = (kw.get("params") or {}).get("engine") or "viator"
        self.calls.append((engine, key))
        return httpx.Response(200, json={"google_hotels": HOTELS, "google_flights": FLIGHTS, "viator": VIATOR}[engine])


@pytest.fixture
def providers(monkeypatch):
    p = Providers()
    monkeypatch.setattr(live_data, "http", p)
    monkeypatch.setattr(live_data, "FETCH", lambda url: (_ for _ in ()).throw(AssertionError("no page fetch expected")))
    live_data._account_cache.clear()
    return p


def central_keys(client, owner, serpapi="central-serp-key-123", viator="central-viator-key-123"):
    r = client.put("/api/system/live-data", headers=owner, json={"serpapi_key": serpapi, "viator_key": viator})
    assert r.status_code == 200, r.text
    return r.json()


def test_live_choices_have_price_photos_features_and_link(client, owner, company_a, scripted, providers):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner)
    t, _ = custom_request(client, company, admin, scripted)
    # The AI picks among the real offers by their ref; it keeps writing free options for other parts.
    llm = scripted([draft_reply({"category": "hotel", "ref": "h2", "reason": "Quiet, for a honeymoon"},
                                {"category": "flight", "ref": "f1", "reason": "One stop, morning"},
                                {"category": "activity", "ref": "a1", "reason": "Top rated"})])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    by = {o["title"]: o for o in trip["options"]}
    baraza = by["Baraza Resort"]
    assert baraza["source"] == "google_hotels" and baraza["estimate_price"] == 3100 and baraza["ai_reason"] == "Quiet, for a honeymoon"
    assert baraza["image_url"] == "https://img.example/baraza.jpg" and baraza["link"].startswith("https://www.google.com/travel/hotels")
    flight = next(o for o in trip["options"] if o["source"] == "google_flights")
    assert flight["estimate_price"] == 410 and flight["facts"]["stops"] == 1 and "WY 721" in flight["facts"]["flight_numbers"]
    tour = next(o for o in trip["options"] if o["source"] == "viator")
    assert tour["facts"]["rating"] == 4.8 and tour["image_url"] == "https://img.example/st.jpg" and tour["estimate_price"] == 70
    zuri = by.get("Zuri Zanzibar")  # not picked by the AI, but the part still gets the agency's best offers
    assert zuri is None or zuri["facts"]["features"][:2] == ["Pool", "Spa"]
    # The AI was given the real offers (and still never the client's name).
    system = llm.calls[-1][0]["content"]
    assert "LIVE CHOICES" in system and "Baraza Resort" in system and "Huda" not in llm.calls[-1][1]["content"]
    assert {e for e, _ in providers.calls} == {"google_hotels", "google_flights", "viator"}
    # Three searches counted against the company's free 20 this month.
    usage = client.get("/api/live-data", headers=admin).json()
    assert usage["used"] == 3 and usage["left"] == 17 and usage["providers"] == {"serpapi": "platform", "viator": "platform"}
    assert "central-serp-key" not in str(usage)


def test_a_company_key_is_used_instead_of_the_central_one(client, owner, company_a, scripted, providers):
    company, admin = company_a
    b, admin_b = make_company(client, owner, "Beta Travel", "b@beta.example")
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner)
    r = client.put(f"/api/system/companies/{company['id']}/live-data", headers=owner,
                   json={"serpapi_key": "alpha-own-serp-key-999", "unlimited": True})
    assert r.status_code == 200, r.text
    assert r.json()["own_serpapi"] is True and r.json()["limit"] is None and r.json()["own_account"]["left"] == 241
    t, _ = custom_request(client, company, admin, scripted)
    scripted([draft_reply()])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    keys = {engine: key for engine, key in providers.calls}
    assert keys["google_hotels"] == "alpha-own-serp-key-999" and keys["viator"] == "central-viator-key-123"
    mine = client.get("/api/live-data", headers=admin).json()
    assert mine["providers"]["serpapi"] == "company" and mine["key_left"] == 241 and mine["left"] is None
    # Another company keeps the central key; nobody but the owner reaches the key screens.
    assert client.get("/api/live-data", headers=admin_b).json()["providers"]["serpapi"] == "platform"
    for path in ("/api/system/live-data", f"/api/system/companies/{company['id']}/live-data"):
        assert client.get(path, headers=admin).status_code == 403
    assert client.put(f"/api/system/companies/{b['id']}/live-data", headers=admin, json={"serpapi_key": "x" * 20}).status_code == 403
    assert client.put("/api/system/live-data", headers=owner, json={"serpapi_key": "bad key!"}).status_code == 422


def test_the_monthly_limit_and_no_keys(client, owner, company_a, scripted, providers):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    t, _ = custom_request(client, company, admin, scripted)
    # No keys anywhere: the AI plans as before, nothing is searched or counted.
    scripted([draft_reply(opt("hotel", "Zuri Zanzibar", "Zuri", 1200))])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    assert providers.calls == [] and trip["options"][0]["source"] is None
    assert client.get("/api/live-data", headers=admin).json()["used"] == 0
    # With a limit of 1 a month: one search, then the planner goes on without live data.
    central_keys(client, owner)
    client.put(f"/api/system/companies/{company['id']}/features", headers=owner, json={"live_search": {"on": True, "limit": 1}})
    scripted([draft_reply()])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert len(providers.calls) == 1
    usage = client.get("/api/live-data", headers=admin).json()
    assert usage["used"] == 1 and usage["left"] == 0
    # Switched off by the owner: no searches at all.
    client.put(f"/api/system/companies/{company['id']}/features", headers=owner, json={"live_search": {"on": False}})
    before = len(providers.calls)
    scripted([draft_reply(opt("hotel", "Another", "X", 100))])
    client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin)
    assert len(providers.calls) == before


def test_free_link_check_takes_the_photo_and_drops_broken_links(client, owner, company_a, scripted, monkeypatch):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    pages = {"https://zuri.example/": (200, "https://zuri.example/", '<meta property="og:image" content="/photo.jpg">'),
             "https://gone.example/": (404, "https://gone.example/", ""),
             "https://booking.example/h": (403, "https://booking.example/h", "")}
    monkeypatch.setattr(live_data, "FETCH", lambda url: pages[url])
    t, _ = custom_request(client, company, admin, scripted)
    scripted([draft_reply({**opt("hotel", "Zuri", "Zuri", 900), "link": "https://zuri.example/"},
                          {**opt("hotel", "Gone Hotel", "Gone", 500), "link": "https://gone.example/"},
                          {**opt("hotel", "Big Site Hotel", "Big", 700), "link": "https://booking.example/h"},
                          {**opt("activity", "Bad link", "X", 10), "link": "javascript:alert(1)"})])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    by = {o["title"]: o for o in trip["options"]}
    assert by["Zuri"]["image_url"] == "https://zuri.example/photo.jpg" and by["Zuri"]["facts"]["link_checked"] is True
    assert by["Gone Hotel"]["link"] is None and by["Gone Hotel"]["facts"]["link_checked"] is False
    assert by["Big Site Hotel"]["link"] == "https://booking.example/h" and by["Big Site Hotel"]["facts"]["link_checked"] is None
    assert by["Bad link"]["link"] is None


def test_the_server_never_opens_private_addresses():
    for url in ("http://127.0.0.1/", "http://localhost:8000/", "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.5/", "file:///etc/passwd", "https://user:pw@example.com/"):
        with pytest.raises(live_data.LiveError):
            live_data.safe_get(url)
    assert live_data.check_link("http://127.0.0.1/admin")["ok"] is False


def test_airport_codes():
    from app.ai.planner import _airport
    assert _airport("Muscat") == "MCT" and _airport("تبليسي") == "TBS" and _airport("LHR") == "LHR" and _airport("Nowhere") is None


def test_a_country_destination_searches_the_right_area_and_prefers_real_hotels(client, owner, company_a, scripted, monkeypatch):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner, viator="")
    seen = []

    def providers(method, url, **kw):
        params = kw.get("params") or {}
        seen.append(params)
        if params.get("engine") == "google_hotels":
            return httpx.Response(200, json={"properties": [
                {"name": "Pool villa far away", "type": "vacation rental", "overall_rating": 5, "reviews": 4,
                 "total_rate": {"extracted_lowest": 200}},
                *[{"name": f"Hotel {n}", "type": "hotel", "overall_rating": 4.5, "reviews": 300 + n, "extracted_hotel_class": 4,
                   "total_rate": {"extracted_lowest": 500 + n}} for n in range(3)]]})
        return httpx.Response(200, json={"error": "Google Flights hasn't returned any results for this query."})

    monkeypatch.setattr(live_data, "http", providers)
    t, _ = custom_request(client, company, admin, scripted, destination="Thailand")
    pages = {"https://www.booking.com/hotel/th/katathani.html": (403, "https://www.booking.com/hotel/th/katathani.html", ""),
             "https://www.agoda.com/the-shore/hotel/phuket.html": (200, "https://www.agoda.com/the-shore/hotel/phuket.html",
                                                                   '<meta property="og:image" content="https://pix.agoda.net/shore.jpg">'),
             "https://www.booking.com/hotel/th/third.html": (200, "https://www.booking.com/hotel/th/third.html", "")}
    monkeypatch.setattr(live_data, "FETCH", lambda url: pages[url])
    llm = scripted([LLMResponse('{"from": "MCT", "to": "HKT", "hotel_area": "Phuket"}'),
                    draft_reply({"category": "hotel", "ref": "h1", "reason": "Quiet beach hotel"},
                                {**opt("hotel", "Katathani Phuket", "Katathani", 900), "link": "https://www.booking.com/hotel/th/katathani.html"},
                                {**opt("hotel", "The Shore", "Katathani", 1500), "link": "https://www.agoda.com/the-shore/hotel/phuket.html"},
                                {**opt("hotel", "A third web hotel", "X", 700), "link": "https://www.booking.com/hotel/th/third.html"},
                                {"category": "transport", "title": "Airport transfer to the hotel", "provider": None, "reason": "r"})])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    hotel_opts = [o for o in trip["options"] if o["category"] == "hotel"]
    # 2 live offers first, then 2 the AI found on Booking.com and Agoda (a third web hotel is not kept).
    assert [o["source"] for o in hotel_opts] == ["google_hotels", "google_hotels", "web", "web"]
    shore = next(o for o in hotel_opts if o["title"] == "The Shore")
    assert shore["facts"]["site"] == "agoda.com" and shore["image_url"] == "https://pix.agoda.net/shore.jpg"
    assert next(o for o in hotel_opts if o["title"] == "Katathani Phuket")["facts"]["site"] == "booking.com"
    hotels = next(p for p in seen if p.get("engine") == "google_hotels")
    flights = next(p for p in seen if p.get("engine") == "google_flights")
    assert hotels["q"] == "hotels in Phuket" and flights["arrival_id"] == "HKT"
    titles = [o["title"] for o in trip["options"] if o["category"] == "hotel" and o["source"] == "google_hotels"]
    assert "Pool villa far away" not in titles and len(titles) == 2  # the AI's pick, then the best reviewed
    # The AI is told the official class and the guest rating apart, and that transport is local.
    system = llm.calls[-1][0]["content"]
    assert '"hotel_stars": 4' in system and "guest_rating" in system and "never \\\ntravel between countries" not in system
    assert "never travel between countries" in system.replace("\n", " ").replace("\\ ", "")
    # A provider with no results is noted in the request's history for the team.
    history = client.get(f"/api/tickets/{t['id']}/events", headers=admin).json()
    drafted = next(e for e in history if e["action"] == "ai_drafted")
    assert "live prices: Google Hotels" in drafted["new_value"] and "Google Flights:" in drafted["new_value"]


def test_viator_errors_say_why_and_keys_can_be_tested(client, owner, company_a, monkeypatch):
    company, admin = company_a
    central_keys(client, owner, viator="viator-sandbox-key-123")

    def providers(method, url, **kw):
        if "account" in url:
            return httpx.Response(200, json={"total_searches_left": 250})
        if "sandbox" in url:  # the key only works on Viator's test server
            return httpx.Response(200, json={"products": {"results": []}})
        return httpx.Response(401, json={"code": "UNAUTHORIZED", "message": "Invalid API Key"})

    monkeypatch.setattr(live_data, "http", providers)
    live_data._account_cache.clear()
    r = client.post("/api/system/live-data/test", headers=owner).json()
    assert r["serpapi"] == {"ok": True, "detail": "250 searches left"}
    assert r["viator"]["ok"] is False and "test (sandbox) key" in r["viator"]["detail"]
    # A wrong key: Viator's own words are kept.
    monkeypatch.setattr(live_data, "_viator_sandbox_ok", lambda headers: False)
    r = client.post("/api/system/live-data/test", headers=owner).json()
    assert "refused the key (401: Invalid API Key)" in r["viator"]["detail"]
    assert client.post("/api/system/live-data/test", headers=admin).status_code == 403
    assert client.post(f"/api/system/companies/{company['id']}/live-data/test", headers=owner).json()["viator"]["ok"] is None


def test_a_live_option_can_be_priced_and_keeps_its_photos(client, owner, company_a, scripted, providers):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner)
    t, _ = custom_request(client, company, admin, scripted)
    scripted([draft_reply()])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    hotel = next(o for o in trip["options"] if o["source"] == "google_hotels" and o["photos"])
    flight = next(o for o in trip["options"] if o["source"] == "google_flights")
    base = f"/api/tickets/{t['id']}/options"
    # The form sends back what it has (including the live photo), plus the client price.
    for o, price in ((hotel, "2500"), (flight, "980")):
        body = {k: o[k] for k in ("category", "title", "provider", "link", "details", "image_url", "supplier_id")}
        r = client.put(f"{base}/{o['id']}", headers=admin, json={**body, "cost_price": None, "price": price})
        assert r.status_code == 200, r.text
    after = {o["id"]: o for o in r.json()["options"]}
    assert after[hotel["id"]]["price"] == 2500 and after[hotel["id"]]["photos"] == hotel["photos"]
    assert after[hotel["id"]]["image_url"] == hotel["image_url"] and after[flight["id"]]["price"] == 980
    # A photo from another website typed in by hand is still refused.
    body = {k: hotel[k] for k in ("category", "title", "provider", "link", "details", "supplier_id")}
    r = client.put(f"{base}/{hotel['id']}", headers=admin, json={**body, "image_url": "https://evil.example/x.jpg", "price": "1"})
    assert r.status_code == 422
    # Priced: it can be sent to the client.
    r = client.post(f"/api/tickets/{t['id']}/send-choices", headers=admin, json={"option_ids": [flight["id"], hotel["id"]]})
    assert r.status_code == 200 and r.json()["status"] == "quoted", r.text


def test_the_choices_message_is_written_for_the_client_without_links(client, owner, company_a, scripted, providers):
    company, admin = company_a
    switch(client, owner, company["id"], trip_planner=True)
    central_keys(client, owner)
    t, token = custom_request(client, company, admin, scripted)
    scripted([draft_reply()])
    trip = client.post(f"/api/tickets/{t['id']}/ai-draft", headers=admin).json()
    base = f"/api/tickets/{t['id']}"
    flight = next(o for o in trip["options"] if o["source"] == "google_flights")
    hotel = next(o for o in trip["options"] if o["source"] == "google_hotels")
    for o, price in ((flight, "980"), (hotel, "2500.5")):
        body = {k: o[k] for k in ("category", "title", "provider", "link", "details", "image_url", "supplier_id")}
        client.put(f"{base}/options/{o['id']}", headers=admin, json={**body, "price": price})
    writer = scripted([LLMResponse(json.dumps({
        "intro": {"en": "Your honeymoon in Zanzibar, quiet beaches and warm evenings.", "ar": "شهر عسلكم في زنجبار."},
        "items": {"1": {"en": "One short stop, you land by mid-afternoon https://bad.example", "ar": "توقف قصير واحد"},
                  "2": {"en": "Beachfront, perfect for a quiet honeymoon", "ar": "على الشاطئ"}, "9": {"en": "x", "ar": "y"}}}))])
    client.post(f"{base}/send-choices", headers=admin, json={"option_ids": [flight["id"], hotel["id"]]})
    from app.database import SessionLocal
    from app.models import Message, Ticket
    with SessionLocal() as db:
        conv_id = db.get(Ticket, t["id"]).conversation_id
        sent = db.query(Message).filter_by(conversation_id=conv_id).order_by(Message.id.desc()).first().content
    assert "Your honeymoon in Zanzibar" in sent and "_One short stop, you land by mid-afternoon_" in sent
    assert "💰 *980 OMR* · round trip" in sent and "💰 *2,500.500 OMR*" in sent and "★" in sent
    assert "http" not in sent and "Huda" not in writer.calls[-1][1]["content"]  # no links; the AI never gets her name
    # Nothing the client (or the AI talking to them) sees carries a booking link: the team books.
    from app.ai.request_tools import my_requests
    from app.services.quotes import quotation
    from app.ai.tools import ToolContext
    from app.models import Company, Conversation
    from app.timeutil import local_today
    with SessionLocal() as db:
        tk = db.get(Ticket, t["id"])
        ctx = ToolContext(db=db, company=db.get(Company, company["id"]), conversation=db.get(Conversation, tk.conversation_id),
                          customer=tk.customer, today=local_today())
        seen = json.dumps(my_requests(ctx), ensure_ascii=False, default=str)
        sheet = quotation(db, ctx.company, tk, "draft")["items"]
    assert sheet and "http" not in json.dumps([{k: v for k, v in i.items() if k not in ("image_url", "photos")} for i in sheet])
    assert "choices_waiting" in seen and "http" not in seen and "round_trip" in seen
