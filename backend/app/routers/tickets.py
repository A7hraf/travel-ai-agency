"""Booking tickets created by the AI, finished (payment) by employees."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import require_permission
from ..models import (
    Message,
    MessageKind,
    Role,
    Sender,
    Ticket,
    TicketEvent,
    TicketStatus,
    User,
)
from ..permissions import effective_permissions
from ..schemas import TicketEventOut, TicketOut, TicketUpdate
from ..services import seats

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
    stmt = select(Ticket).where(Ticket.company_id == me.company_id).options(
        selectinload(Ticket.customer), selectinload(Ticket.assigned_to)
    )
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


# Allowed status changes. Cancelled is final, except a company admin may reopen a booking.
NEXT_STATUSES: dict[str, set[str]] = {
    TicketStatus.PENDING_PAYMENT: {TicketStatus.IN_PROGRESS, TicketStatus.PAID, TicketStatus.CANCELLED},
    TicketStatus.IN_PROGRESS: {TicketStatus.PENDING_PAYMENT, TicketStatus.PAID, TicketStatus.CANCELLED},
    TicketStatus.PAID: {TicketStatus.CONFIRMED, TicketStatus.CANCELLED},
    TicketStatus.CONFIRMED: {TicketStatus.CANCELLED},
    TicketStatus.CANCELLED: {TicketStatus.PENDING_PAYMENT},
}
NEEDS_PAYMENT_REFERENCE = {TicketStatus.PAID, TicketStatus.CONFIRMED}


def _event(db: Session, ticket: Ticket, me: User, action: str, old=None, new=None) -> None:
    db.add(TicketEvent(ticket_id=ticket.id, user_id=me.id, actor=me.full_name, action=action,
                       old_value=None if old is None else str(old), new_value=None if new is None else str(new)))


@router.get("/{ticket_id}/events", response_model=list[TicketEventOut])
def ticket_events(ticket_id: int, me: User = Depends(require_permission("tickets.view")),
                  db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id)
    return db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)).all()


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, body: TicketUpdate, me: User = Depends(require_permission("tickets.manage")),
                  db: Session = Depends(get_db)):
    # Lock the ticket so two employees can't apply the same change twice at the same moment.
    ticket = db.get(Ticket, ticket_id, with_for_update=True)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    can_assign = "tickets.assign" in effective_permissions(me)
    is_admin = me.role == Role.COMPANY_ADMIN
    chat_events: list[str] = []

    if body.unassign:
        if ticket.assigned_to_id is not None:
            if not can_assign and ticket.assigned_to_id != me.id:
                raise HTTPException(403, "Missing permission: tickets.assign")
            _event(db, ticket, me, "unassigned", ticket.assigned_to.full_name if ticket.assigned_to else None)
            ticket.assigned_to_id = None
    elif body.assigned_to_id is not None and body.assigned_to_id != ticket.assigned_to_id:
        # Without tickets.assign an employee may only take a ticket nobody has yet.
        if not can_assign and (body.assigned_to_id != me.id or ticket.assigned_to_id is not None):
            raise HTTPException(403, "Missing permission: tickets.assign")
        assignee = db.get(User, body.assigned_to_id)
        if assignee is None or assignee.company_id != me.company_id or not assignee.is_active:
            raise HTTPException(400, "Assignee must be an active employee of your company")
        _event(db, ticket, me, "assigned", ticket.assigned_to.full_name if ticket.assigned_to else None,
               assignee.full_name)
        ticket.assigned_to_id = assignee.id
        chat_events.append(f"Ticket {ticket.reference} assigned to {assignee.full_name}")

    if body.payment_reference is not None:
        new_ref = body.payment_reference.strip() or None
        if new_ref != ticket.payment_reference:
            if ticket.status in NEEDS_PAYMENT_REFERENCE and new_ref is None:
                raise HTTPException(400, "A paid booking must keep its payment reference")
            _event(db, ticket, me, "payment_reference", ticket.payment_reference, new_ref)
            ticket.payment_reference = new_ref

    if body.total_price is not None:
        new_total = Decimal(str(body.total_price)).quantize(Decimal("0.001"))
        if new_total != ticket.total_price:
            if not is_admin:
                raise HTTPException(403, "Only a company admin can change the price of a booking")
            _event(db, ticket, me, "price", ticket.total_price, new_total)
            ticket.total_price = new_total

    if body.status is not None and body.status != ticket.status:
        old, new = ticket.status, body.status
        if new not in NEXT_STATUSES.get(old, set()):
            raise HTTPException(400, f"A booking can't go from {old} to {new}")
        if old == TicketStatus.CANCELLED and not is_admin:
            raise HTTPException(403, "Only a company admin can reopen a cancelled booking")
        if new in NEEDS_PAYMENT_REFERENCE and not ticket.payment_reference:
            raise HTTPException(400, "Enter the payment reference (receipt or transfer number) first")
        if new == TicketStatus.CANCELLED:
            seats.release(db, ticket)
        else:
            seats.hold_or_409(db, ticket)  # also covers bookings made before seats were held at booking time
        _event(db, ticket, me, "status", old, new)
        chat_events.append(f"Ticket {ticket.reference}: {old} → {new} by {me.full_name}")
        ticket.status = new
        if new == TicketStatus.IN_PROGRESS and ticket.assigned_to_id is None:
            ticket.assigned_to_id = me.id

    if body.internal_notes is not None and body.internal_notes != ticket.internal_notes:
        _event(db, ticket, me, "notes")
        ticket.internal_notes = body.internal_notes

    if ticket.conversation_id:
        for text in chat_events:
            db.add(Message(conversation_id=ticket.conversation_id, sender=Sender.SYSTEM, kind=MessageKind.TEXT,
                           content=text))
    db.commit()
    db.refresh(ticket)
    return ticket
