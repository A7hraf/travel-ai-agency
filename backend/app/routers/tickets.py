"""Clients' requests (stored as "tickets"): the AI's request card, the quotation loop, the payment and the
booking. The flow itself lives in services/requests.py; this file checks who may do what."""

import base64
import binascii
from decimal import Decimal

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..audit import audit
from ..database import get_db
from ..deps import require_permission
from ..models import (
    Message,
    MessageKind,
    RequestFile,
    Role,
    Supplier,
    Sender,
    Ticket,
    TicketEvent,
    TicketStatus,
    User,
    utcnow,
)
from ..permissions import effective_permissions
from ..schemas import TicketEventOut, TicketOut, TicketUpdate
from ..services import library
from ..services import request_desk as desk
from ..services import request_files as files
from .media import media_belongs_to
from ..services.request_files import file_response
from ..services import requests as flow
from ..services import seats
from ..timeutil import local_today
from ..addons import has_addon, require_addon
from ..ratelimit import limiter
from pydantic import BaseModel, Field, field_validator
from typing import Literal

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _get(db: Session, me: User, ticket_id: int, lock: bool = False) -> Ticket:
    ticket = db.get(Ticket, ticket_id, with_for_update=lock)
    if ticket is None or ticket.company_id != me.company_id:
        raise HTTPException(404, "Ticket not found")
    return ticket


def ticket_out(ticket: Ticket, me: User, detail: bool = False) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.stage = desk.stage_of(ticket)
    out.money = desk.money(ticket)
    if detail:
        out.request_files = [files.file_out(f) for f in ticket.files]
        out.booking_steps = files.checklist_view(ticket)
        out.payment_list = [desk.payment_out(p) for p in ticket.payments]
        out.client_documents = desk.documents_view(ticket)
        out.itinerary = desk.apply_dates_hint(ticket.departure_date, ticket.itinerary or [])
    out.options = sorted(out.options, key=lambda o: (flow.CATEGORIES.index(o.category) if o.category in flow.CATEGORIES else 99, o.id))
    out.urgency = flow.urgency(ticket, me.company, local_today())
    return out


def _filtered(db: Session, me: User, *, status=None, stage=None, mine=False, assigned=None, service_id=None, q=None):
    stmt = select(Ticket).where(Ticket.company_id == me.company_id)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if stage == "open":
        stmt = stmt.where(Ticket.status.notin_(desk.STAGES["confirmed"] + desk.STAGES["closed"]))
    elif stage:
        stmt = stmt.where(Ticket.status.in_(desk.STAGES[stage]))
    if mine or assigned == "me":
        stmt = stmt.where(Ticket.assigned_to_id == me.id)
    elif assigned == "none":
        stmt = stmt.where(Ticket.assigned_to_id.is_(None))
    elif assigned and assigned.isdigit():
        stmt = stmt.where(Ticket.assigned_to_id == int(assigned))
    if service_id:
        stmt = stmt.where(Ticket.service_id == service_id)
    if q:
        # % and _ are searched as typed, not as wildcards.
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(Ticket.reference.ilike(like, escape="\\"), Ticket.lead_traveler_name.ilike(like, escape="\\"),
                Ticket.contact_phone.ilike(like, escape="\\"), Ticket.destination.ilike(like, escape="\\"),
                Ticket.package_title.ilike(like, escape="\\"))
        )
    return stmt


@router.get("", response_model=list[TicketOut])
def list_tickets(
    response: Response,
    status: str | None = None,
    stage: Literal["open", "quote", "client", "payment", "booking", "confirmed", "closed"] | None = None,
    mine: bool = False,
    assigned: str | None = Query(default=None, max_length=12),
    service_id: int | None = None,
    urgent: bool = False,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort: Literal["newest", "urgency", "departure"] = "newest",
    me: User = Depends(require_permission("tickets.view")),
    db: Session = Depends(get_db),
):
    """Requests, filtered and in pages (X-Total-Count gives the number of matches)."""
    # Unpaid bookings past their hold time give their seats back (shown in their history).
    if seats.release_expired(db, company_id=me.company_id):
        db.commit()
    stmt = _filtered(db, me, status=status, stage=stage, mine=mine, assigned=assigned, service_id=service_id, q=q)
    stmt = stmt.options(selectinload(Ticket.customer), selectinload(Ticket.assigned_to), selectinload(Ticket.service),
                        selectinload(Ticket.options), selectinload(Ticket.payments))
    if sort == "newest" and not urgent:
        response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = db.scalars(stmt.order_by(Ticket.id.desc()).offset(offset).limit(limit)).all()
        return [ticket_out(t, me) for t in rows]
    # Priority and departure need every match (priority is worked out per request), then one page of them.
    rows = [ticket_out(t, me) for t in db.scalars(stmt.order_by(Ticket.id.desc()).limit(3000)).all()]
    if urgent:
        rows = [r for r in rows if (r.urgency.get("score") or 0) >= 45]
    if sort == "urgency":
        rows.sort(key=lambda t: -t.urgency.get("score", 0))
    elif sort == "departure":
        rows.sort(key=lambda t: (t.departure_date is None, t.departure_date or ""))
    response.headers["X-Total-Count"] = str(len(rows))
    return rows[offset:offset + limit]


@router.get("/summary")
def summary(me: User = Depends(require_permission("tickets.view")), db: Session = Depends(get_db)):
    """The pipeline at a glance: requests per stage, what needs the team now, and the money."""
    rows = db.scalars(select(Ticket).where(Ticket.company_id == me.company_id, or_(
        Ticket.status.notin_(desk.STAGES["closed"] + desk.STAGES["confirmed"]),
        Ticket.updated_at >= utcnow() - timedelta(days=62)))
        .options(selectinload(Ticket.options), selectinload(Ticket.payments), selectinload(Ticket.customer))).all()
    today = local_today()
    month = today.replace(day=1).isoformat()
    stages = {k: 0 for k in desk.STAGES}
    pipeline = Decimal(0)
    to_collect = Decimal(0)
    profit_month = Decimal(0)
    sales_month = Decimal(0)
    urgent = unassigned = proofs = 0
    for t in rows:
        stage = desk.stage_of(t)
        stages[stage] += 1
        m = desk.money(t)
        if stage in ("quote", "client"):
            pipeline += Decimal(str(m["total"] or m["choices_total"] or 0))
        if stage == "payment":
            to_collect += Decimal(str(m["balance"] or 0))
        if stage in ("booking", "confirmed") and t.updated_at and t.updated_at.date().isoformat() >= month:
            sales_month += Decimal(str(m["total"] or 0))
            profit_month += Decimal(str(m["profit"] or 0))
        if stage not in ("closed", "confirmed"):
            if (flow.urgency(t, me.company, today).get("score") or 0) >= 45:
                urgent += 1
            if t.assigned_to_id is None:
                unassigned += 1
        proofs += m["pending_proofs"]
    # Confirmed and closed are counted for all time (the list shows them all).
    for stage in ("confirmed", "closed"):
        stages[stage] = db.scalar(select(func.count(Ticket.id)).where(
            Ticket.company_id == me.company_id, Ticket.status.in_(desk.STAGES[stage]))) or 0
    f = lambda v: float(round(v, 3))  # noqa: E731
    return {"stages": stages, "urgent": urgent, "unassigned": unassigned, "proofs_to_check": proofs,
            "pipeline_value": f(pipeline), "to_collect": f(to_collect), "sales_this_month": f(sales_month),
            "profit_this_month": f(profit_month), "currency": me.company.currency or "OMR"}


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, me: User = Depends(require_permission("tickets.view")), db: Session = Depends(get_db)):
    if seats.release_expired(db, company_id=me.company_id):
        db.commit()
    return ticket_out(_get(db, me, ticket_id), me, detail=True)


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
    return ticket_out(ticket, me, detail=True)


# --- Quotation (choices, final quotation) and the client's answers -------------------------------------

class OptionIn(BaseModel):
    category: Literal["flight", "hotel", "transport", "activity", "food", "visa", "insurance", "other"]
    title: str = Field(min_length=2, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    link: str | None = Field(default=None, max_length=500)
    details: str | None = Field(default=None, max_length=2000)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    supplier_id: int | None = None
    image_url: str | None = Field(default=None, max_length=500)

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
    return ticket_out(ticket, me, detail=True)


def _option_data(db: Session, me: User, body: OptionIn) -> dict:
    """The option's fields, with its supplier and photo checked to be the company's own."""
    data = body.model_dump()
    if data["supplier_id"] is not None:
        s = db.get(Supplier, data["supplier_id"])
        if s is None or s.company_id != me.company_id:
            raise HTTPException(404, "Supplier not found")
    if data["image_url"] and not (data["image_url"].startswith("/api/media/")
                                  and media_belongs_to(db, data["image_url"], me.company_id)):
        raise HTTPException(422, "Upload the photo (photos from other websites can't be used)")
    return data


@router.post("/{ticket_id}/options", response_model=TicketOut)
def add_option(ticket_id: int, body: OptionIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.add_option(db, ticket, _option_data(db, me, body), me)
    return _done(db, ticket, me)


@router.get("/{ticket_id}/library")
def library_suggestions(ticket_id: int, me: User = Depends(require_permission("tickets.view")),
                        db: Session = Depends(get_db)):
    """Saved suppliers for each part of this request, for its place: one click adds them as a choice."""
    if not has_addon(me.company, "library"):
        return {}
    ticket = _get(db, me, ticket_id)
    parts = ticket.parts or list(flow.CATEGORIES)
    out = {}
    for part in parts:
        rows = library.matches(db, me.company_id, part, ticket.destination, limit=6)
        if rows:
            out[part] = [{"id": s.id, "name": s.name, "place": s.place, "stars": s.stars, "usual_price": s.usual_price,
                          "usual_cost": s.usual_cost, "preferred": s.preferred, "image_url": s.image_url} for s in rows]
    return out


class FromLibraryIn(BaseModel):
    supplier_id: int


@router.post("/{ticket_id}/options/from-library", response_model=TicketOut)
def add_from_library(ticket_id: int, body: FromLibraryIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    require_addon(me.company, "library")
    ticket = _get(db, me, ticket_id, lock=True)
    s = db.get(Supplier, body.supplier_id)
    if s is None or s.company_id != me.company_id:
        raise HTTPException(404, "Supplier not found")
    flow.add_option(db, ticket, library.option_from(s), me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/options/{option_id}/save-to-library", response_model=TicketOut)
def save_to_library(ticket_id: int, option_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    require_addon(me.company, "library")
    ticket = _get(db, me, ticket_id, lock=True)
    option = flow._option(ticket, option_id)
    s = library.save_option(db, ticket, option, me)
    flow.event(db, ticket, me.full_name, "saved_to_library", None, s.name, me)
    return _done(db, ticket, me)


@router.put("/{ticket_id}/options/{option_id}", response_model=TicketOut)
def update_option(ticket_id: int, option_id: int, body: OptionIn, me: User = Depends(manage),
                  db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    flow.update_option(db, ticket, option_id, _option_data(db, me, body), me)
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


# --- Files, booking checklist and documents --------------------------------------------------------------

class FileIn(BaseModel):
    kind: Literal["document", "payment_proof", "client_file"] = "document"
    name: str | None = Field(default=None, max_length=200)
    content_type: str = Field(max_length=60)
    data_base64: str = Field(max_length=files.MAX_FILE_BYTES * 4 // 3 + 16)


def decode(data_base64: str) -> bytes:
    try:
        return base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The file data is not valid") from None


@router.post("/{ticket_id}/files", response_model=TicketOut, status_code=201)
def upload_file(ticket_id: int, body: FileIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    limiter.check(f"request-files:{me.company_id}", 300, "Too many uploads, please wait a few minutes", window=3600)
    ticket = _get(db, me, ticket_id, lock=True)
    files.staff_upload(db, ticket, body.kind, body.name, body.content_type, decode(body.data_base64), me)
    return _done(db, ticket, me)


@router.get("/{ticket_id}/files/{file_id}")
def open_file(ticket_id: int, file_id: int, me: User = Depends(require_permission("tickets.view")),
              db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id)
    f = db.scalar(select(RequestFile).where(RequestFile.id == file_id, RequestFile.ticket_id == ticket.id,
                                            RequestFile.company_id == me.company_id))
    if f is None:
        raise HTTPException(404, "File not found")
    return file_response(f)


@router.delete("/{ticket_id}/files/{file_id}", response_model=TicketOut)
def remove_file(ticket_id: int, file_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    files.delete_file(db, ticket, file_id, me)
    return _done(db, ticket, me)


class StepIn(BaseModel):
    step: str = Field(min_length=1, max_length=40)
    done: bool


@router.post("/{ticket_id}/checklist", response_model=TicketOut)
def tick_step(ticket_id: int, body: StepIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    files.tick(db, ticket, body.step, body.done, me)
    return _done(db, ticket, me)


class DocumentsIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{ticket_id}/send-documents", response_model=TicketOut)
def send_documents(ticket_id: int, body: DocumentsIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    failed = files.send_documents(db, me.company, ticket, body.note, me)
    out = _done(db, ticket, me)
    if failed:
        out.notice = f"{failed} documents could not be sent on WhatsApp: the client can open them on their trips page"
    return out


# --- A request made by staff (a call, a walk-in, an email) ------------------------------------------------

class NewRequestIn(BaseModel):
    service_id: int
    customer_id: int | None = None
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=200)
    answers: dict[str, str] = Field(default_factory=dict, max_length=40)
    summary: str = Field(default="", max_length=4000)


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(body: NewRequestIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    """A request the team takes outside the chat. The client is found by phone (or made), so their private
    trips page shows it after they confirm the code on WhatsApp. Missing answers can be added later."""
    from ..models import Customer, Service  # noqa: PLC0415
    from ..services.whatsapp import normalize_phone  # noqa: PLC0415

    service = db.get(Service, body.service_id)
    if service is None or service.company_id != me.company_id or service.pricing == "packages":
        raise HTTPException(404, "Service not found")
    if body.customer_id is not None:
        customer = db.get(Customer, body.customer_id)
        if customer is None or customer.company_id != me.company_id:
            raise HTTPException(404, "Customer not found")
    else:
        phone = normalize_phone(body.phone or "") if body.phone else None
        if body.phone and not phone:
            raise HTTPException(422, "Write the phone with the country code, for example +968 9123 4567")
        if not phone and not (body.name or "").strip():
            raise HTTPException(422, "Give the client's name or phone")
        customer = db.scalar(select(Customer).where(Customer.company_id == me.company_id, Customer.whatsapp_id == phone)) if phone else None
        if customer is None:
            customer = Customer(company_id=me.company_id, name=(body.name or "").strip()[:200] or None,
                                whatsapp_id=phone, phone=f"+{phone}" if phone else None, email=(body.email or None))
            db.add(customer)
            db.flush()
    answers = {k: str(v) for k, v in body.answers.items()}
    if body.name and not answers.get("full_name"):
        answers["full_name"] = body.name
    if customer.phone and not answers.get("phone"):
        answers["phone"] = customer.phone
    conversation = None
    if customer.whatsapp_id and me.company.whatsapp_phone_number_id:
        # Updates (choices, quotation, payment details) then reach the client on WhatsApp like any request.
        from ..services.conversations import _channel_conversation  # noqa: PLC0415
        from ..models import Channel  # noqa: PLC0415

        conversation = _channel_conversation(db, me.company, customer, Channel.WHATSAPP)
    ticket = flow.create_request(db, me.company, customer, service, answers, body.summary, conversation,
                                 actor=me.full_name, strict=False)
    ticket.assigned_to_id = me.id
    ticket.created_by = "staff"
    audit(db, me, "ticket.created", target=ticket.reference)
    return _done(db, ticket, me)


class DetailsIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict, max_length=40)
    special_requests: str | None = Field(default=None, max_length=4000)


@router.put("/{ticket_id}/details", response_model=TicketOut)
def update_details(ticket_id: int, body: DetailsIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    """Staff correct or complete what the client asked (dates, travellers, names…)."""
    from ..catalog import check_answers  # noqa: PLC0415

    ticket = _get(db, me, ticket_id, lock=True)
    if ticket.status in (TicketStatus.CANCELLED, TicketStatus.REJECTED, TicketStatus.CONFIRMED):
        raise HTTPException(409, "This request is closed: reopen it to change it")
    if ticket.service is None or ticket.service.pricing == "packages":
        raise HTTPException(409, "A package booking keeps the package's details")
    clean, _missing = check_answers(ticket.service, {**(ticket.answers or {}), **body.answers})
    flow.fill_from_answers(ticket, ticket.service, clean, ticket.customer)
    if body.special_requests is not None:
        ticket.special_requests = body.special_requests.strip()
    flow.event(db, ticket, me.full_name, "details_changed", None, ", ".join(sorted(body.answers)) or None, me)
    return _done(db, ticket, me)


class MoneyIn(BaseModel):
    total_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    cost_price: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)
    clear_cost: bool = False


@router.put("/{ticket_id}/money", response_model=TicketOut)
def update_money(ticket_id: int, body: MoneyIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    """The client price (until the payment is complete) and the company's cost, for the profit."""
    ticket = _get(db, me, ticket_id, lock=True)
    if body.total_price is not None and body.total_price != ticket.total_price:
        if ticket.status in (TicketStatus.PAID, TicketStatus.CONFIRMED) and me.role != Role.COMPANY_ADMIN:
            raise HTTPException(403, "Only a company admin can change the price of a paid booking")
        if ticket.status in (TicketStatus.CANCELLED, TicketStatus.REJECTED):
            raise HTTPException(409, "This request is closed: reopen it to change it")
        flow.event(db, ticket, me.full_name, "price", ticket.total_price, body.total_price, me)
        audit(db, me, "ticket.price", target=ticket.reference, detail=f"{ticket.total_price} → {body.total_price} {ticket.currency}")
        ticket.total_price = body.total_price
    if body.clear_cost and ticket.cost_price is not None:
        flow.event(db, ticket, me.full_name, "cost", ticket.cost_price, None, me)
        ticket.cost_price = None
    elif body.cost_price is not None and body.cost_price != ticket.cost_price:
        flow.event(db, ticket, me.full_name, "cost", ticket.cost_price, body.cost_price, me)
        ticket.cost_price = body.cost_price
    return _done(db, ticket, me)


# --- Payments -------------------------------------------------------------------------------------------

class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("100000000"), decimal_places=3)
    method: Literal["bank_transfer", "cash", "card", "link", "other"] = "bank_transfer"
    reference: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)
    file_id: int | None = None


def _after_payment(db: Session, ticket: Ticket, me: User, became_paid: bool) -> TicketOut:
    out = _done(db, ticket, me)
    if became_paid:
        flow.notify_status(db, ticket)  # the client hears the payment was received
        db.refresh(ticket)
        out = ticket_out(ticket, me, detail=True)
    return out


@router.post("/{ticket_id}/payments", response_model=TicketOut, status_code=201)
def add_payment(ticket_id: int, body: PaymentIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    """A payment received (deposit, balance, cash at the office…). Fully paid moves the request to booking."""
    ticket = _get(db, me, ticket_id, lock=True)
    paid = desk.record(db, ticket, body.amount, body.method, (body.reference or "").strip() or None, body.note, body.file_id, me)
    audit(db, me, "ticket.payment", target=ticket.reference, detail=f"{body.amount} {ticket.currency} recorded")
    return _after_payment(db, ticket, me, paid)


class ApproveIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("100000000"), decimal_places=3)
    method: Literal["bank_transfer", "cash", "card", "link", "other"] = "bank_transfer"
    reference: str | None = Field(default=None, max_length=200)


@router.post("/{ticket_id}/payments/{payment_id}/approve", response_model=TicketOut)
def approve_payment(ticket_id: int, payment_id: int, body: ApproveIn, me: User = Depends(manage),
                    db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    paid = desk.approve(db, ticket, payment_id, body.amount, body.method, (body.reference or "").strip() or None, me)
    audit(db, me, "ticket.payment", target=ticket.reference, detail=f"receipt approved: {body.amount} {ticket.currency}")
    return _after_payment(db, ticket, me, paid)


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


@router.post("/{ticket_id}/payments/{payment_id}/reject", response_model=TicketOut)
def reject_payment(ticket_id: int, payment_id: int, body: RejectIn, me: User = Depends(manage),
                   db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    desk.reject(db, ticket, payment_id, body.note.strip(), me)
    db.refresh(ticket)
    return ticket_out(ticket, me, detail=True)


# --- Sorting files, and the trip plan --------------------------------------------------------------------

class SortIn(BaseModel):
    kind: Literal["payment_proof", "client_file", "document"]
    requirement: str | None = Field(default=None, max_length=40)


@router.patch("/{ticket_id}/files/{file_id}", response_model=TicketOut)
def sort_file(ticket_id: int, file_id: int, body: SortIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    desk.classify(db, ticket, file_id, body.kind, body.requirement, me)
    return _done(db, ticket, me)


class PlanIn(BaseModel):
    days: list[desk.PlanDay] = Field(default_factory=list, max_length=60)


@router.put("/{ticket_id}/itinerary", response_model=TicketOut)
def save_plan(ticket_id: int, body: PlanIn, me: User = Depends(manage), db: Session = Depends(get_db)):
    ticket = _get(db, me, ticket_id, lock=True)
    if ticket.status in (TicketStatus.CANCELLED, TicketStatus.REJECTED):
        raise HTTPException(409, "This request is closed: reopen it to change it")
    days = sorted((d.model_dump() for d in body.days), key=lambda d: d["day"])
    ticket.itinerary = days or None
    flow.event(db, ticket, me.full_name, "plan_saved", None, f"{len(days)} days", me)
    return _done(db, ticket, me)


@router.post("/{ticket_id}/itinerary/ai-draft")
def draft_plan(ticket_id: int, me: User = Depends(manage), db: Session = Depends(get_db)):
    """The AI drafts the day-by-day plan (not saved: staff check it first)."""
    limiter.check(f"plan-draft:{me.company_id}", 60, "The AI is busy: please try again in a few minutes", window=3600)
    ticket = _get(db, me, ticket_id)
    return {"days": desk.draft_plan(ticket)}
