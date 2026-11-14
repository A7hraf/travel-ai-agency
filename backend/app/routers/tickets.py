"""Clients' requests (stored as "tickets"): the AI's request card, the quotation loop, the payment and the
booking. The flow itself lives in services/requests.py; this file checks who may do what."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..audit import audit
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
from ..services import requests as flow
from ..services import seats
from ..timeutil import local_today
from ..addons import has_addon
from ..ratelimit import limiter
from pydantic import BaseModel, Field, field_validator
from typing import Literal

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _get(db: Session, me: User, ticket_id: int, lock: bool = False) -> Ticket:
    ticket = db.get(Ticket, ticket_id, with_for_update=lock)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    return ticket


def ticket_out(ticket: Ticket, me: User) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.options = sorted(out.options, key=lambda o: (flow.CATEGORIES.index(o.category) if o.category in flow.CATEGORIES else 99, o.id))
    out.urgency = flow.urgency(ticket, me.company, local_today())
    return out


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: str | None = None,
    mine: bool = False,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, le=1000),
    sort: Literal["newest", "urgency"] = "newest",
    me: User = Depends(require_permission("tickets.view")),
    db: Session = Depends(get_db),
):
    # Unpaid bookings past their hold time give their seats back (shown in their history).
    if seats.release_expired(db, company_id=me.company_id):
        db.commit()
    stmt = select(Ticket).where(Ticket.company_id == me.company_id).options(
        selectinload(Ticket.customer), selectinload(Ticket.assigned_to)
    )
    if status:
        stmt = stmt.where(Ticket.status == status)
    if mine:
        stmt = stmt.where(Ticket.assigned_to_id == me.id)
    if q:
        # % and _ are searched as typed, not as wildcards.
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(Ticket.reference.ilike(like, escape="\\"), Ticket.lead_traveler_name.ilike(like, escape="\\"),
                Ticket.contact_phone.ilike(like, escape="\\"))
        )
    rows = [ticket_out(t, me) for t in db.scalars(stmt.order_by(Ticket.id.desc()).limit(limit)).all()]
    if sort == "urgency":
        rows.sort(key=lambda t: -t.urgency.get("score", 0))
    return rows


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, me: User = Depends(require_permission("tickets.view")), db: Session = Depends(get_db)):
    if seats.release_expired(db, company_id=me.company_id):
        db.commit()
    return ticket_out(_get(db, me, ticket_id), me)


# Status changes staff make here (the quotation steps have their own endpoints below). Cancelled and
# rejected are final, except a company admin may reopen them.
NEXT_STATUSES: dict[str, set[str]] = {
    TicketStatus.NEW: {TicketStatus.CANCELLED},
    TicketStatus.QUOTED: {TicketStatus.CANCELLED},
    TicketStatus.CHANGES: {TicketStatus.CANCELLED},
    TicketStatus.CHOSEN: {TicketStatus.CANCELLED},
    TicketStatus.FINAL: {TicketStatus.CANCELLED},
    TicketStatus.REJECTED: {TicketStatus.NEW},
    TicketStatus.PENDING_PAYMENT: {TicketStatus.IN_PROGRESS, TicketStatus.PAID, TicketStatus.CANCELLED},
    TicketStatus.IN_PROGRESS: {TicketStatus.PENDING_PAYMENT, TicketStatus.PAID, TicketStatus.CANCELLED},
    TicketStatus.PAID: {TicketStatus.CONFIRMED, TicketStatus.CANCELLED},
    TicketStatus.CONFIRMED: {TicketStatus.CANCELLED},
    TicketStatus.CANCELLED: {TicketStatus.PENDING_PAYMENT, TicketStatus.NEW},
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
def update_ticket(ticket_id: int, body: TicketUpdate,
                  me: User = Depends(require_permission("tickets.view", "tickets.manage")),
                  db: Session = Depends(get_db)):
    # Lock the ticket so two employees can't apply the same change twice at the same moment.
    ticket = db.get(Ticket, ticket_id, with_for_update=True)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    can_assign = "tickets.assign" in effective_permissions(me)
    is_admin = me.role == Role.COMPANY_ADMIN
    chat_events: list[str] = []
    reference_before = ticket.payment_reference

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
        if "tickets.view" not in effective_permissions(assignee):
            raise HTTPException(400, "This employee can't see tickets. Give them the tickets.view permission first")
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
            audit(db, me, "ticket.payment", target=ticket.reference,
                  detail="payment reference added" if new_ref and not ticket.payment_reference
                  else "payment reference removed" if not new_ref else "payment reference changed")
            ticket.payment_reference = new_ref

    if body.total_price is not None:
        new_total = Decimal(str(body.total_price)).quantize(Decimal("0.001"))
        if new_total != ticket.total_price:
            if not is_admin:
                raise HTTPException(403, "Only a company admin can change the price of a booking")
            _event(db, ticket, me, "price", ticket.total_price, new_total)
            audit(db, me, "ticket.price", target=ticket.reference,
                  detail=f"{ticket.total_price} → {new_total} {ticket.currency}")
            ticket.total_price = new_total

    if body.status is not None and body.status != ticket.status:
        old, new = ticket.status, body.status
        if new not in NEXT_STATUSES.get(old, set()):
            raise HTTPException(400, f"A booking can't go from {old} to {new}")
        if old in (TicketStatus.CANCELLED, TicketStatus.REJECTED) and not is_admin:
            raise HTTPException(403, "Only a company admin can reopen a cancelled booking")
        if new == TicketStatus.NEW and old == TicketStatus.CANCELLED and ticket.service_id is None:
            raise HTTPException(400, "A booking can't go from cancelled to new")
        if new in NEEDS_PAYMENT_REFERENCE and not ticket.payment_reference:
            raise HTTPException(400, "Enter the payment reference (receipt or transfer number) first")
        departed = ticket.departure_date and ticket.departure_date < local_today().isoformat()
        if new in NEEDS_PAYMENT_REFERENCE and departed:
            raise HTTPException(400, f"The departure date ({ticket.departure_date}) has passed: "
                                     "this booking can only be cancelled")
        if new == TicketStatus.CANCELLED:
            seats.release(db, ticket)
        elif new == TicketStatus.NEW:
            pass  # reopened: the quotation starts again
        else:
            # Also re-takes seats released after an unpaid hold expired, and covers bookings made
            # before seats were held at booking time.
            seats.hold_or_409(db, ticket)
            if new == TicketStatus.PENDING_PAYMENT:
                seats.restart_hold(ticket)
        if (new == TicketStatus.CANCELLED or old == TicketStatus.CANCELLED) and ticket.payment_reference \
                and ticket.payment_reference == reference_before:
            # A cancelled or reopened booking must be paid again with a new receipt; the old one stays
            # in the history.
            _event(db, ticket, me, "payment_reference", ticket.payment_reference, None)
            ticket.payment_reference = None
        _event(db, ticket, me, "status", old, new)
        audit(db, me, "ticket.status", target=ticket.reference, detail=f"{old} → {new}")
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
    if body.status is not None and ticket.status == body.status:
        flow.notify_status(db, ticket)  # the client hears about payment received, booked, cancelled
        db.refresh(ticket)
    return ticket_out(ticket, me)


# --- Quotation (choices, final quotation) and the client's answers -------------------------------------

class OptionIn(BaseModel):
    category: Literal["flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other"]
    title: str = Field(min_length=2, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    link: str | None = Field(default=None, max_length=500)
    details: str | None = Field(default=None, max_length=2000)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)

    @field_validator("title", "provider")
    @classmethod
    def one_line(cls, v):
        return " ".join(v.split()) or None if v is not None else None

    @field_validator("link")
    @classmethod
    def web_link(cls, v):
        v = (v or "").strip()
        if not v:
            return None
        if not v.startswith(("https://", "http://")) or any(c.isspace() for c in v):
            raise ValueError("The link must start with https://")
        return v


class SendIn(BaseModel):
    option_ids: list[int] = Field(min_length=1, max_length=30)


class FinalIn(BaseModel):
    total: Decimal | None = Field(default=None, gt=0, le=Decimal("100000000"), decimal_places=3)
    note: str | None = Field(default=None, max_length=1000)


class ClientAnswerIn(BaseModel):
    """Staff write down the client's answer (given on the phone or in person)."""

    action: Literal["choose", "changes", "approve", "reject", "cancel", "paid"]
    option_ids: list[int] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=2000)
    transfer_reference: str | None = Field(default=None, max_length=200)


manage = require_permission("tickets.view", "tickets.manage")


def _done(db: Session, ticket: Ticket, me: User) -> TicketOut:
    db.commit()
    db.refresh(ticket)
    return ticket_out(ticket, me)


@router.post("/{ticket_id}/options", response_model=TicketOut)
def add_option(ticket_id: int, body: OptionIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.add_option(db, ticket, body.model_dump(), me)
    return _done(db, ticket, me)


@router.put("/{ticket_id}/options/{option_id}", response_model=TicketOut)
def update_option(ticket_id: int, option_id: int, body: OptionIn, me: User = Depends(manage),
                  db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.update_option(db, ticket, option_id, body.model_dump(), me)
    return _done(db, ticket, me)


@router.delete("/{ticket_id}/options/{option_id}", response_model=TicketOut)
def delete_option(ticket_id: int, option_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.delete_option(db, ticket, option_id, me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/ai-draft", response_model=TicketOut)
def ai_draft(ticket_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    if not has_addon(me.company, "trip_planner"):
        raise HTTPException(403, "The AI trip planner is not switched on for your company. Ask the platform admin.")
    limiter.check(f"ai-draft:{me.company_id}", 30, "The AI planner is busy: please try again in a few minutes", window=3600)
    ticket = _get(db, me, ticket_id, lock=True)
    flow.ai_draft(db, ticket, me.company, me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/send-choices", response_model=TicketOut)
def send_choices(ticket_id: int, body: SendIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.send_choices(db, me.company, ticket, body.option_ids, me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/send-final", response_model=TicketOut)
def send_final(ticket_id: int, body: FinalIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.send_final(db, me.company, ticket, body.total, body.note, me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/client-answer", response_model=TicketOut)
def client_answer(ticket_id: int, body: ClientAnswerIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    actor = f"{me.full_name} (for the client)"
    if body.action == "choose":
        flow.client_choose(db, ticket, body.option_ids, actor)
    elif body.action == "changes":
        flow.client_changes(db, ticket, body.note or "", actor)
    elif body.action == "approve":
        flow.client_approve(db, me.company, ticket, actor)
    elif body.action == "reject":
        flow.client_reject(db, ticket, actor, body.note)
    elif body.action == "cancel":
        flow.client_cancel(db, ticket, actor)
    else:
        flow.client_paid(db, ticket, body.transfer_reference or "", actor)
    return _done(db, ticket, me)
