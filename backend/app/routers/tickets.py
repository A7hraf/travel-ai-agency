"""Booking tickets created by the AI, finished (payment) by employees."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_permission
from ..models import Message, MessageKind, Sender, Ticket, TicketStatus, TravelPackage, User
from ..permissions import effective_permissions
from ..schemas import TicketOut, TicketUpdate

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _get(db: Session, me: User, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    mine: bool = False,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, le=1000),
    me: User = Depends(require_permission("tickets.view")),
    db: Session = Depends(get_db),
):
    stmt = select(Ticket).where(Ticket.company_id == me.company_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if mine:
        stmt = stmt.where(Ticket.assigned_to_id == me.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Ticket.reference.ilike(like), Ticket.lead_traveler_name.ilike(like), Ticket.contact_phone.ilike(like))
        )
    return db.scalars(stmt.order_by(Ticket.id.desc()).limit(limit)).all()


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, me: User = Depends(require_permission("tickets.view")), db: Session = Depends(get_db)):
    return _get(db, me, ticket_id)


def _adjust_seats(db: Session, ticket: Ticket, old: str, new: str) -> None:
    """Seats are taken when a booking is confirmed and given back if it is un-confirmed."""
    if old == new or ticket.package_id is None:
        return
    pkg = db.get(TravelPackage, ticket.package_id)
    if pkg is None or pkg.seats_available is None:
        return
    travelers = ticket.adults + ticket.children
    if new == TicketStatus.CONFIRMED:
        if pkg.seats_available < travelers:
            raise HTTPException(409, f"Only {pkg.seats_available} seats left on this package")
        pkg.seats_available -= travelers
    elif old == TicketStatus.CONFIRMED:
        pkg.seats_available += travelers


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, body: TicketUpdate, me: User = Depends(require_permission("tickets.manage")),
                  db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id)
    events: list[str] = []

    if body.unassign:
        if "tickets.assign" not in effective_permissions(me) and ticket.assigned_to_id != me.id:
            raise HTTPException(403, "Missing permission: tickets.assign")
        ticket.assigned_to_id = None
    elif body.assigned_to_id is not None and body.assigned_to_id != ticket.assigned_to_id:
        if body.assigned_to_id != me.id and "tickets.assign" not in effective_permissions(me):
            raise HTTPException(403, "Missing permission: tickets.assign")
        assignee = db.get(User, body.assigned_to_id)
        if assignee is None or assignee.company_id != me.company_id or not assignee.is_active:
            raise HTTPException(400, "Assignee must be an active employee of your company")
        ticket.assigned_to_id = assignee.id
        events.append(f"Ticket {ticket.reference} assigned to {assignee.full_name}")

    if body.status is not None and body.status != ticket.status:
        _adjust_seats(db, ticket, ticket.status, body.status)
        events.append(f"Ticket {ticket.reference}: {ticket.status} → {body.status} by {me.full_name}")
        ticket.status = body.status
        if body.status == TicketStatus.IN_PROGRESS and ticket.assigned_to_id is None:
            ticket.assigned_to_id = me.id

    if body.internal_notes is not None:
        ticket.internal_notes = body.internal_notes
    if body.payment_reference is not None:
        ticket.payment_reference = body.payment_reference.strip() or None
    if body.total_price is not None:
        ticket.total_price = Decimal(str(body.total_price))

    if ticket.conversation_id:
        for text in events:
            db.add(Message(conversation_id=ticket.conversation_id, sender=Sender.SYSTEM, kind=MessageKind.TEXT,
                           content=text))
    db.commit()
    db.refresh(ticket)
    return ticket
