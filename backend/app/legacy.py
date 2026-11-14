"""One-time move into the single request flow (runs at start-up, safe to run again).

Before services existed, an individual client's need could live in three places: a booking ("ticket"), a
custom trip (a trip request with no business client) or a member request. This gives every company its
built-in services and moves the last two into requests, with their choices, so nothing is lost. Each moved
row is marked (Ticket.legacy_ref) and never moved twice.
"""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .catalog import ensure_built_in, service_by_key
from .models import Company, Customer, Ticket, TicketEvent, TicketStatus as T, utcnow
from .security import ticket_reference

log = logging.getLogger(__name__)

TRIP_STATUS = {"new": T.NEW, "with_vendor": T.NEW, "options_ready": T.NEW, "with_client": T.QUOTED, "chosen": T.CHOSEN,
               "approved": T.PENDING_PAYMENT, "booked": T.PAID, "completed": T.CONFIRMED, "cancelled": T.CANCELLED}
MEMBER_STATUS = {"open": T.NEW, "in_progress": T.NEW, "done": T.CONFIRMED, "declined": T.REJECTED}


def _when(value):
    """Dates read with plain SQL come back as text on SQLite."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return None
    return value


def _moved(db: Session, ref: str) -> bool:
    return db.scalar(select(Ticket.id).where(Ticket.legacy_ref == ref)) is not None


def _ticket(db: Session, company: Company, customer: Customer, **values) -> Ticket:
    reference = ticket_reference()
    while db.scalar(select(Ticket.id).where(Ticket.reference == reference)):
        reference = ticket_reference()
    ticket = Ticket(company_id=company.id, reference=reference, customer_id=customer.id,
                    lead_traveler_name=(customer.name or "—")[:200], contact_phone=customer.phone,
                    currency=company.currency or "OMR", created_by="ai", **values)
    db.add(ticket)
    db.flush()
    db.add(TicketEvent(ticket_id=ticket.id, actor="System", action="moved", new_value=values.get("legacy_ref")))
    return ticket


def merge_into_requests(db: Session) -> None:
    for company in db.scalars(select(Company)).all():
        ensure_built_in(db, company)
    db.commit()
    tables = set(inspect(db.get_bind()).get_table_names())
    moved = 0
    if "member_requests" in tables:
        rows = db.execute(text("SELECT id, company_id, customer_id, conversation_id, title, details, status, "
                               "created_at FROM member_requests ORDER BY id")).mappings().all()
        for r in rows:
            ref = f"member_request:{r['id']}"
            company, customer = db.get(Company, r["company_id"]), db.get(Customer, r["customer_id"])
            if _moved(db, ref) or company is None or customer is None:
                continue
            service = service_by_key(db, company.id, "concierge")
            _ticket(db, company, customer, legacy_ref=ref, service_id=service.id if service else None,
                    conversation_id=r["conversation_id"], package_title=(r["title"] or "Special request")[:200],
                    special_requests=r["details"] or "", answers={"details": r["details"] or r["title"]},
                    parts=["other"], total_price=Decimal(0), status=MEMBER_STATUS.get(r["status"], T.NEW),
                    created_at=_when(r["created_at"]) or utcnow())
            moved += 1
    if "trip_requests" in tables and "customer_id" in {c["name"] for c in inspect(db.get_bind()).get_columns("trip_requests")}:
        rows = db.execute(text("SELECT * FROM trip_requests WHERE client_id IS NULL AND customer_id IS NOT NULL "
                               "ORDER BY id")).mappings().all()
        for r in rows:
            ref = f"custom_trip:{r['id']}"
            company, customer = db.get(Company, r["company_id"]), db.get(Customer, r["customer_id"])
            if company is None or customer is None or _moved(db, ref):
                continue
            service = service_by_key(db, company.id, "custom_trip")
            depart = str(r["depart_date"])[:10] if r["depart_date"] else None
            back = str(r["return_date"])[:10] if r["return_date"] else None
            ticket = _ticket(
                db, company, customer, legacy_ref=ref, service_id=service.id if service else None,
                conversation_id=r["conversation_id"], package_title=f"Tailor-made trip · {r['destination']}"[:200],
                destination=r["destination"], origin=r["origin"], departure_date=depart, return_date=back,
                adults=r["travellers"] or 1, parts=list(r["needs"] or []) if isinstance(r["needs"], list) else ["flight", "hotel"],
                answers={k: v for k, v in {"destination": r["destination"], "origin": r["origin"], "depart_date": depart,
                                           "return_date": back, "adults": str(r["travellers"]), "budget": r["budget"],
                                           "preferences": r["notes"]}.items() if v},
                special_requests=r["notes"] or "", total_price=Decimal(0), status=TRIP_STATUS.get(r["status"], T.NEW),
                created_at=_when(r["created_at"]) or utcnow())
            db.execute(text("UPDATE trip_options SET ticket_id = :t, request_id = NULL WHERE request_id = :r"),
                       {"t": ticket.id, "r": r["id"]})
            db.execute(text("DELETE FROM trip_requests WHERE id = :r"), {"r": r["id"]})
            moved += 1
    db.commit()
    if moved:
        log.info("Moved %s old custom trips and member requests into requests", moved)
