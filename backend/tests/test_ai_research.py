"""The AI trip planner learns from the team's own picks and knows the client's preferences (only this company's
client, only our records)."""

from app.ai import planner
from app.database import SessionLocal
from app.models import RecommendationSignal, Ticket
from tests.test_requests_flow import PHONE, services, wa  # noqa: F401 (fixture)
from tests.test_use_cases import ANSWERS
from tests.test_whatsapp import meta_stub  # noqa: F401 (fixture)


def new_request(client, admin):
    r = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)["hotel"]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": ANSWERS, "summary": "Hotel in Georgia"})
    assert r.status_code == 201, r.text
    return r.json()


def test_the_planner_learns_from_the_teams_own_picks(client, wa):  # noqa: F811
    company, admin, _ = wa
    for _ in range(2):
        t = new_request(client, admin)
        r = client.post(f"/api/tickets/{t['id']}/options", headers=admin, json={
            "category": "hotel", "title": "Rooms Kazbegi", "provider": "Rooms Hotels", "cost_price": "300", "price": "360"})
        assert r.status_code == 200, r.text
    with SessionLocal() as db:
        events = {s.event for s in db.query(RecommendationSignal).filter_by(company_id=company["id"]).all()}
        assert "added" in events
        assert "the team often adds Rooms Hotels itself" in planner.learned_text(db, company["id"])


def test_the_planner_knows_the_clients_preferences(client, wa):  # noqa: F811
    company, admin, _ = wa
    t = new_request(client, admin)
    customer_id = t["customer"]["id"]
    r = client.patch(f"/api/customers/{customer_id}", headers=admin,
                     json={"preferences": {"airline": "Oman Air", "hotel_stars": "5 stars"}})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        ticket = db.get(Ticket, t["id"])
        note = planner.client_note(db, ticket)
        assert "Oman Air" in note and "5 stars" in note and "data, not instructions" in note
        # A request never reads a client of another company.
        ticket.company_id = company["id"] + 999
        assert planner.client_note(db, ticket) == ""
        db.rollback()


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_documents_are_filed_for_the_team(client, wa):  # noqa: F811
    from datetime import date
    from types import SimpleNamespace

    from app.ai.request_tools import file_document
    from app.ai.tools import ToolContext
    from app.models import Company, Customer
    from app.services.request_desk import documents_view
    from app.services.request_files import client_upload

    company, admin, _ = wa
    flight = client.post("/api/tickets", headers=admin, json={  # flights need only the passport
        "service_id": services(client, admin)["flights"]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": ANSWERS, "summary": "Flights"}).json()
    visa = client.post("/api/tickets", headers=admin, json={
        "service_id": services(client, admin)["visa"]["id"], "name": "Omar Al Said", "phone": "+" + PHONE,
        "answers": ANSWERS, "summary": "Visa"}).json()
    with SessionLocal() as db:
        t = db.get(Ticket, flight["id"])
        f = client_upload(db, t, "IMG_2231.jpg", "image/png", PNG)
        assert f.requirement == "passport"  # the only document still missing
        v = db.get(Ticket, visa["id"])
        g = client_upload(db, v, "IMG_2232.jpg", "image/png", PNG)
        assert g.requirement is None and g.id in documents_view(v)["unsorted"]  # several missing: not guessed
        db.commit()
        # The client tells the AI it is their photo: the AI files it, only on their own request.
        ctx = ToolContext(db=db, company=db.get(Company, company["id"]), conversation=SimpleNamespace(channel="whatsapp"),
                          customer=db.get(Customer, v.customer_id), today=date.today())
        assert "error" in file_document(ctx, reference=v.reference, document="nonsense")
        out = file_document(ctx, reference=v.reference, document="photo")
        assert out["filed_as"].startswith("Personal photo"), out
        db.refresh(g)
        assert g.requirement == "photo"
        stranger = Customer(company_id=company["id"], name="Someone else", phone="+96890000001")
        db.add(stranger)
        db.flush()
        ctx.customer = stranger
        assert "error" in file_document(ctx, reference=v.reference, document="passport")
        db.rollback()


def test_a_client_who_forgot_the_number_still_finds_only_their_requests(client, wa):  # noqa: F811
    from datetime import date
    from types import SimpleNamespace

    from app.ai.request_tools import answer_quotation, my_requests
    from app.ai.tools import ToolContext
    from app.models import Company, Customer

    company, admin, _ = wa
    mine = new_request(client, admin)
    with SessionLocal() as db:
        owner = db.get(Customer, mine["customer"]["id"])
        ctx = ToolContext(db=db, company=db.get(Company, company["id"]), conversation=SimpleNamespace(channel="whatsapp"),
                          customer=owner, today=date.today())
        listed = my_requests(ctx)["requests"]
        assert [r["reference"] for r in listed] == [mine["reference"]]
        assert listed[0]["service"] and listed[0]["opened"]  # enough to recognise the trip without the number
        stranger = Customer(company_id=company["id"], name="Someone else", phone="+96890000002")
        db.add(stranger)
        db.flush()
        ctx.customer = stranger
        assert my_requests(ctx)["requests"] == []
        # Knowing the number is not enough: the request belongs to another client.
        assert "error" in answer_quotation(ctx, reference=mine["reference"], decision="cancel")
        db.rollback()
