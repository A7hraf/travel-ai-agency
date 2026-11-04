"""CSV downloads for company admins (reports.view): bookings and payments, by date range.

Dates are the agency's local days (Oman by default) and both ends are included.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..csvutil import csv_response
from ..database import get_db
from ..deps import require_permission
from ..models import Ticket, TicketEvent, TicketStatus, User
from ..timeutil import local_today, start_of_local_day

router = APIRouter(prefix="/api/exports", tags=["exports"])

# Booking rows hold customer contact details, so seeing tickets is needed as well.
can_export = require_permission("reports.view", "tickets.view")
STATUSES = "^(pending_payment|in_progress|paid|confirmed|cancelled|open)$"
OPEN = (TicketStatus.PENDING_PAYMENT, TicketStatus.IN_PROGRESS)
PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)


EARLIEST, LATEST = date(2000, 1, 1), date(2100, 12, 31)


def _range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    if any(d is not None and not EARLIEST <= d <= LATEST for d in (date_from, date_to)):
        # Year 1 or 9999 would overflow when turned into a moment in time (a 500 error otherwise).
        raise HTTPException(400, "Choose dates between 2000 and 2100")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "The start date must be before the end date")
    start = start_of_local_day(date_from) if date_from else None
    end = start_of_local_day(date_to + timedelta(days=1)) if date_to else None
    return start, end


def _name(date_from: date | None, date_to: date | None, what: str) -> str:
    return f"{what}-{date_from or 'start'}-to-{date_to or local_today()}.csv"


@router.get("/tickets.csv")
def export_tickets(
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = Query(default=None, pattern=STATUSES),
    me: User = Depends(can_export),
    db: Session = Depends(get_db),
):
    """Bookings created in the period (optionally one status, or "open")."""
    start, end = _range(date_from, date_to)
    stmt = select(Ticket).where(Ticket.company_id == me.company_id).options(
        selectinload(Ticket.customer), selectinload(Ticket.assigned_to), selectinload(Ticket.conversation))
    if start:
        stmt = stmt.where(Ticket.created_at >= start)
    if end:
        stmt = stmt.where(Ticket.created_at < end)
    if status == "open":
        stmt = stmt.where(Ticket.status.in_(OPEN))
    elif status:
        stmt = stmt.where(Ticket.status == status)
    tickets = db.scalars(stmt.order_by(Ticket.created_at, Ticket.id)).all()
    header = ["Reference", "Created", "Status", "Package", "Departure date", "Adults", "Children", "Lead traveller",
              "Phone", "Email", "Total", "Currency", "Payment reference", "Assigned to", "Channel", "Created by"]
    rows = ([t.reference, t.created_at, t.status, t.package_title, t.departure_date, t.adults, t.children,
             t.lead_traveler_name, t.contact_phone or (t.customer.phone if t.customer else None),
             t.contact_email or (t.customer.email if t.customer else None), f"{t.total_price:.3f}", t.currency,
             t.payment_reference, t.assigned_to.full_name if t.assigned_to else None,
             t.conversation.channel if t.conversation else None, t.created_by] for t in tickets)
    return csv_response(_name(date_from, date_to, "bookings"), header, rows)


@router.get("/payments.csv")
def export_payments(
    date_from: date | None = None,
    date_to: date | None = None,
    me: User = Depends(can_export),
    db: Session = Depends(get_db),
):
    """Paid and confirmed bookings, dated by the moment they were marked as paid."""
    start, end = _range(date_from, date_to)
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == me.company_id, Ticket.status.in_(PAID))
                         .options(selectinload(Ticket.customer))).all()
    paid_at: dict[int, tuple[datetime, str]] = {}
    if tickets:
        events = db.scalars(select(TicketEvent).where(
            TicketEvent.ticket_id.in_([t.id for t in tickets]), TicketEvent.action == "status",
            TicketEvent.new_value == TicketStatus.PAID).order_by(TicketEvent.id)).all()
        for e in events:  # the latest "marked as paid" wins (a reopened booking is paid again)
            paid_at[e.ticket_id] = (e.created_at, e.actor)
    rows = []
    for t in tickets:
        when, who = paid_at.get(t.id, (t.updated_at, None))
        if (start and when < start) or (end and when >= end):
            continue
        rows.append((when, t))
    rows.sort(key=lambda x: (x[0], x[1].id))
    header = ["Paid", "Reference", "Customer", "Package", "Amount", "Currency", "Payment reference", "Status",
              "Recorded by"]
    return csv_response(
        _name(date_from, date_to, "payments"), header,
        ([when, t.reference, t.lead_traveler_name or (t.customer.name if t.customer else None), t.package_title,
          f"{t.total_price:.3f}", t.currency, t.payment_reference, t.status, paid_at.get(t.id, (None, None))[1]]
         for when, t in rows),
    )
