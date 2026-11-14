"""Business trip requests: client → travel company → vendor → travel company → client → approval → booking.

The travel company is the middle party, so each party gets its own view (``staff_view``, ``client_view``,
``vendor_view``) built here and nowhere else:

* the client never sees the vendor, its cost prices, the vendor thread or the staff history;
* the vendor never sees the client's name, contact, notes, budget or the client prices, sees only the
  options it proposed, and gets the traveller names only once the trip is approved;
* every query is filtered by the travel company, and the portals also by the client or vendor.

Status changes lock the request row, so two clicks at the same moment cannot both pass a check.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..b2b import effective_features
from ..models import (
    Company,
    Conversation,
    Message,
    MessageKind,
    Partner,
    PartnerKind,
    Sender,
    TripOption,
    TripRequest,
    TripRequestEvent,
    TripRequestMessage,
    TripRequestStatus as S,
    User,
)
from ..security import ticket_reference
from ..trip_schemas import (
    CATEGORIES,
    MAX_CHOICES,
    MAX_OPTIONS,
    AssignVendorIn,
    BookedIn,
    ClientOptionOut,
    ClientTripOut,
    EventOut,
    MessageOut,
    OptionIn,
    StaffOptionOut,
    StaffTripOut,
    StaffTripRow,
    StepOut,
    TripRequestIn,
    VendorOptionIn,
    VendorOptionOut,
    VendorTripOut,
)

log = logging.getLogger(__name__)

# Steps each party sees in its own history (without who did it or the details).
CLIENT_STEPS = {"created", "sent_to_client", "chosen", "approved", "booked", "completed", "cancelled"}
VENDOR_STEPS = {"assigned", "accepted", "declined", "options_submitted", "approved", "booked", "cancelled"}
# Before approval, a request can still change hands or be cancelled by the client.
OPEN = (S.NEW, S.WITH_VENDOR, S.OPTIONS_READY, S.WITH_CLIENT, S.CHOSEN)
EDITABLE_OPTIONS = (S.NEW, S.WITH_VENDOR, S.OPTIONS_READY)
MILLI = Decimal("0.001")


class Actor:
    """Who does a step: kind (staff, client, vendor, ai) and the name shown in the travel company's history."""

    def __init__(self, kind: str, name: str | None, user_id: int | None = None):
        self.kind, self.name, self.user_id = kind, name, user_id

    @classmethod
    def of(cls, user: User, kind: str) -> Actor:
        return cls(kind, user.full_name, user.id)


# --- Loading ------------------------------------------------------------------------------------------

def get_for_company(db: Session, company_id: int, request_id: int, lock: bool = False) -> TripRequest:
    stmt = select(TripRequest).where(TripRequest.id == request_id, TripRequest.company_id == company_id)
    if lock:
        stmt = stmt.with_for_update()
    req = db.scalar(stmt)
    if req is None:
        raise HTTPException(404, "Request not found")
    if lock:
        db.refresh(req)
    return req


def get_for_client(db: Session, user: User, request_id: int, lock: bool = False) -> TripRequest:
    req = get_for_company(db, user.company_id, request_id, lock)
    if req.client_id != user.partner_id:
        raise HTTPException(404, "Request not found")
    return req


def get_for_vendor(db: Session, user: User, request_id: int, lock: bool = False) -> TripRequest:
    req = get_for_company(db, user.company_id, request_id, lock)
    if req.vendor_id is None or req.vendor_id != user.partner_id:
        raise HTTPException(404, "Request not found")
    return req


def _require(req: TripRequest, *statuses: str) -> None:
    if req.status not in statuses:
        raise HTTPException(409, f"This request is now '{req.status}', so this step is not possible.")


def _event(db: Session, req: TripRequest, actor: Actor, action: str, detail: str | None = None) -> None:
    db.add(TripRequestEvent(company_id=req.company_id, request_id=req.id, actor_kind=actor.kind,
                            actor_name=actor.name, action=action, detail=(detail or None) and detail[:500]))


def ordered(options: list[TripOption]) -> list[TripOption]:
    """Options by part (flight, hotel, transport, activity, food), then in the order they were added."""
    return sorted(options, key=lambda o: (CATEGORIES.index(o.category) if o.category in CATEGORIES else 99, o.id))


# --- Views --------------------------------------------------------------------------------------------

def _chosen_total(options: list[TripOption], field: str) -> Decimal | None:
    chosen = [o for o in options if o.chosen]
    if not chosen or any(getattr(o, field) is None for o in chosen):
        return None
    return sum((getattr(o, field) for o in chosen), Decimal(0))


def _common(req: TripRequest, company: Company) -> dict:
    return dict(id=req.id, reference=req.reference, status=req.status, purpose=req.purpose, origin=req.origin,
                destination=req.destination, depart_date=req.depart_date, return_date=req.return_date,
                travellers=req.travellers, needs=list(req.needs or []), created_at=req.created_at,
                updated_at=req.updated_at, currency=company.currency or "OMR")


def _messages(req: TripRequest, thread: str | None) -> list[MessageOut]:
    return [MessageOut(id=m.id, thread=m.thread, author_kind=m.author_kind, author_name=m.author_name, text=m.text,
                       created_at=m.created_at) for m in req.messages if thread is None or m.thread == thread]


def staff_view(req: TripRequest, company: Company) -> StaffTripOut:
    return StaffTripOut(
        **_common(req, company), source=req.source, client_id=req.client_id, client_name=req.client.name,
        vendor_id=req.vendor_id, vendor_name=req.vendor.name if req.vendor else None,
        vendor_accepted=req.vendor_accepted, traveller_names=req.traveller_names, budget=req.budget,
        notes=req.notes, vendor_brief=req.vendor_brief, markup_percent=req.markup_percent,
        booking_reference=req.booking_reference, booking_notes=req.booking_notes,
        total_price=_chosen_total(req.options, "price"), total_cost=_chosen_total(req.options, "cost_price"),
        options=[StaffOptionOut(id=o.id, category=o.category, title=o.title, provider=o.provider, details=o.details,
                                cost_price=o.cost_price, price=o.price, added_by=o.added_by,
                                sent_to_client=o.sent_to_client, chosen=o.chosen) for o in ordered(req.options)],
        events=[EventOut(action=e.action, created_at=e.created_at, actor_kind=e.actor_kind, actor_name=e.actor_name,
                         detail=e.detail) for e in req.events],
        messages=_messages(req, None),
    )


def staff_row(req: TripRequest) -> StaffTripRow:
    return StaffTripRow(id=req.id, reference=req.reference, status=req.status, source=req.source,
                        client_name=req.client.name, vendor_name=req.vendor.name if req.vendor else None,
                        destination=req.destination, depart_date=req.depart_date, travellers=req.travellers,
                        updated_at=req.updated_at)


def client_view(req: TripRequest, company: Company) -> ClientTripOut:
    sent = [o for o in ordered(req.options) if o.sent_to_client]
    return ClientTripOut(
        **_common(req, company), traveller_names=req.traveller_names, budget=req.budget, notes=req.notes,
        booking_reference=req.booking_reference if req.status in (S.BOOKED, S.COMPLETED) else None,
        total_price=_chosen_total(sent, "price"),
        options=[ClientOptionOut(id=o.id, category=o.category, title=o.title, provider=o.provider, details=o.details,
                                 price=o.price, chosen=o.chosen) for o in sent],
        steps=[StepOut(action=e.action, created_at=e.created_at) for e in req.events if e.action in CLIENT_STEPS],
        messages=_messages(req, "client"),
    )


def vendor_view(req: TripRequest, company: Company) -> VendorTripOut:
    mine = [o for o in ordered(req.options) if o.vendor_id == req.vendor_id]
    approved = req.status in (S.APPROVED, S.BOOKED, S.COMPLETED)
    # The purpose can name the client ("PDO board meeting"): the vendor gets the travel company's brief instead.
    return VendorTripOut(
        **(_common(req, company) | {"purpose": None}), brief=req.vendor_brief,
        traveller_names=req.traveller_names if approved else None, accepted=req.vendor_accepted,
        booking_reference=req.booking_reference, booking_notes=req.booking_notes,
        total_cost=_chosen_total(mine, "cost_price") if approved else None,
        options=[VendorOptionOut(id=o.id, category=o.category, title=o.title, provider=o.provider, details=o.details,
                                 cost_price=o.cost_price, chosen=o.chosen and approved) for o in mine],
        steps=[StepOut(action=e.action, created_at=e.created_at) for e in req.events if e.action in VENDOR_STEPS],
        messages=_messages(req, "vendor"),
    )


# --- Creating -----------------------------------------------------------------------------------------

def create_request(db: Session, company: Company, client: Partner, data: TripRequestIn, actor: Actor, source: str,
                   conversation_id: int | None = None) -> TripRequest:
    if client.company_id != company.id or client.kind != PartnerKind.CLIENT:
        raise HTTPException(404, "Business client not found")
    if not client.is_active:
        raise HTTPException(409, "This business client is paused")
    for _ in range(5):
        req = TripRequest(
            company_id=company.id, reference=ticket_reference().replace("TRV-", "BR-"), client_id=client.id,
            status=S.NEW, source=source, created_by_id=actor.user_id, conversation_id=conversation_id,
            purpose=data.purpose, origin=data.origin, destination=data.destination, depart_date=data.depart_date,
            return_date=data.return_date, travellers=data.travellers, traveller_names=data.traveller_names,
            needs=list(data.needs), budget=data.budget, notes=data.notes,
        )
        try:
            with db.begin_nested():
                db.add(req)
                db.flush()
            break
        except IntegrityError:  # the same reference already exists: draw another
            continue
    else:
        raise HTTPException(500, "Could not create the request, please try again")
    _event(db, req, actor, "created", source)
    db.commit()
    db.refresh(req)
    return req


# --- Travel company steps -----------------------------------------------------------------------------

def assign_vendor(db: Session, req: TripRequest, data: AssignVendorIn, actor: Actor) -> TripRequest:
    _require(req, S.NEW, S.WITH_VENDOR, S.OPTIONS_READY)
    vendor = db.get(Partner, data.vendor_id)
    if vendor is None or vendor.company_id != req.company_id or vendor.kind != PartnerKind.VENDOR:
        raise HTTPException(404, "Vendor not found")
    if not vendor.is_active or "vendor.requests" not in effective_features(vendor):
        raise HTTPException(409, "This vendor can't receive requests (paused, or the feature is off)")
    req.vendor_id = vendor.id
    req.vendor_accepted = None
    req.vendor_brief = data.brief
    req.status = S.WITH_VENDOR
    _event(db, req, actor, "assigned", vendor.name)
    db.commit()
    db.refresh(req)
    return req


def set_markup(db: Session, req: TripRequest, markup: Decimal, actor: Actor) -> TripRequest:
    _require(req, *EDITABLE_OPTIONS)
    req.markup_percent = markup
    _event(db, req, actor, "markup", f"{markup}%")
    db.commit()
    return req


def _option_count(req: TripRequest) -> None:
    if len(req.options) >= MAX_OPTIONS:
        raise HTTPException(409, f"A request can have at most {MAX_OPTIONS} options")


def add_staff_option(db: Session, req: TripRequest, data: OptionIn, actor: Actor) -> TripRequest:
    _require(req, *EDITABLE_OPTIONS)
    _option_count(req)
    req.options.append(TripOption(company_id=req.company_id, category=data.category, title=data.title,
                                  provider=data.provider, details=data.details, cost_price=data.cost_price,
                                  price=data.price, added_by="staff", vendor_id=None))
    if req.status == S.NEW:
        req.status = S.OPTIONS_READY
    _event(db, req, actor, "option_added", f"{data.category}: {data.title}")
    db.commit()
    db.refresh(req)
    return req


def update_staff_option(db: Session, req: TripRequest, option_id: int, data: OptionIn, actor: Actor) -> TripRequest:
    _require(req, *EDITABLE_OPTIONS)
    option = _option(req, option_id)
    for key in ("category", "title", "provider", "details", "cost_price", "price"):
        setattr(option, key, getattr(data, key))
    _event(db, req, actor, "option_changed", f"{option.category}: {option.title}")
    db.commit()
    db.refresh(req)
    return req


def delete_option(db: Session, req: TripRequest, option_id: int, actor: Actor) -> TripRequest:
    _require(req, *EDITABLE_OPTIONS)
    option = _option(req, option_id)
    req.options.remove(option)
    _event(db, req, actor, "option_removed", f"{option.category}: {option.title}")
    db.commit()
    db.refresh(req)
    return req


def _option(req: TripRequest, option_id: int) -> TripOption:
    option = next((o for o in req.options if o.id == option_id), None)
    if option is None:
        raise HTTPException(404, "Option not found")
    return option


def _with_markup(cost: Decimal, markup: Decimal) -> Decimal:
    return (cost * (Decimal(100) + markup) / Decimal(100)).quantize(MILLI, ROUND_HALF_UP)


def send_to_client(db: Session, req: TripRequest, option_ids: list[int], actor: Actor) -> TripRequest:
    _require(req, S.NEW, S.WITH_VENDOR, S.OPTIONS_READY)
    wanted = set(option_ids)
    picked = [o for o in req.options if o.id in wanted]
    if len(picked) != len(wanted):
        raise HTTPException(404, "Option not found")
    for category in CATEGORIES:
        if sum(1 for o in picked if o.category == category) > MAX_CHOICES:
            raise HTTPException(422, f"Send at most {MAX_CHOICES} choices for each part")
    for o in picked:
        if o.price is None:
            if o.cost_price is None:
                raise HTTPException(422, f"Set a price for \"{o.title}\" first")
            o.price = _with_markup(o.cost_price, req.markup_percent)
    for o in req.options:
        o.sent_to_client = o.id in wanted
        o.chosen = False
    req.status = S.WITH_CLIENT
    _event(db, req, actor, "sent_to_client", f"{len(picked)} options")
    db.commit()
    db.refresh(req)
    _notify_client(db, req, "options")
    return req


def approve(db: Session, req: TripRequest, actor: Actor) -> TripRequest:
    _require(req, S.CHOSEN)
    req.status = S.APPROVED
    total = _chosen_total(req.options, "price")
    _event(db, req, actor, "approved", f"{total}" if total is not None else None)
    db.commit()
    db.refresh(req)
    _notify_client(db, req, "approved")
    return req


def complete(db: Session, req: TripRequest, actor: Actor) -> TripRequest:
    _require(req, S.BOOKED)
    req.status = S.COMPLETED
    _event(db, req, actor, "completed")
    db.commit()
    db.refresh(req)
    return req


def cancel(db: Session, req: TripRequest, actor: Actor, reason: str | None) -> TripRequest:
    if actor.kind == "staff":
        _require(req, *OPEN, S.APPROVED, S.BOOKED)
    else:
        _require(req, *OPEN)  # a client cancels before approval; after that, through the travel company
    req.status = S.CANCELLED
    _event(db, req, actor, "cancelled", reason)
    db.commit()
    db.refresh(req)
    if actor.kind == "staff":
        _notify_client(db, req, "cancelled")
    return req


# --- Client steps -------------------------------------------------------------------------------------

def choose(db: Session, req: TripRequest, option_ids: list[int], actor: Actor) -> TripRequest:
    _require(req, S.WITH_CLIENT)
    sent = [o for o in req.options if o.sent_to_client]
    wanted = set(option_ids)
    picked = [o for o in sent if o.id in wanted]
    if len(picked) != len(wanted):
        raise HTTPException(404, "Option not found")
    parts = {o.category for o in sent}
    if sorted(o.category for o in picked) != sorted(parts):
        raise HTTPException(422, "Choose exactly one option for each part")
    for o in req.options:
        o.chosen = o.id in wanted
    req.status = S.CHOSEN
    _event(db, req, actor, "chosen", ", ".join(o.title for o in picked))
    db.commit()
    db.refresh(req)
    return req


# --- Vendor steps -------------------------------------------------------------------------------------

def vendor_respond(db: Session, req: TripRequest, accept: bool, actor: Actor, reason: str | None) -> TripRequest:
    _require(req, S.WITH_VENDOR)
    if accept:
        req.vendor_accepted = True
        _event(db, req, actor, "accepted")
    else:
        # The request goes back to the travel company; the vendor no longer sees it.
        req.vendor_id = None
        req.vendor_accepted = None
        req.status = S.NEW if not req.options else S.OPTIONS_READY
        _event(db, req, actor, "declined", reason)
    db.commit()
    db.refresh(req)
    return req


def vendor_add_option(db: Session, req: TripRequest, data: VendorOptionIn, actor: Actor) -> TripRequest:
    _require(req, S.WITH_VENDOR)
    if data.category not in (req.needs or []):
        raise HTTPException(422, "This request doesn't ask for that part")
    _option_count(req)
    if not req.vendor_accepted:
        req.vendor_accepted = True
        _event(db, req, actor, "accepted")
    req.options.append(TripOption(company_id=req.company_id, vendor_id=req.vendor_id, category=data.category,
                                  title=data.title, provider=data.provider, details=data.details,
                                  cost_price=data.cost_price, price=None, added_by="vendor"))
    db.commit()
    db.refresh(req)
    return req


def vendor_delete_option(db: Session, req: TripRequest, option_id: int, actor: Actor) -> TripRequest:
    _require(req, S.WITH_VENDOR)
    option = _option(req, option_id)
    if option.vendor_id != req.vendor_id:
        raise HTTPException(404, "Option not found")
    req.options.remove(option)
    db.commit()
    db.refresh(req)
    return req


def vendor_submit(db: Session, req: TripRequest, actor: Actor) -> TripRequest:
    _require(req, S.WITH_VENDOR)
    if not any(o.vendor_id == req.vendor_id for o in req.options):
        raise HTTPException(422, "Add at least one option first")
    req.status = S.OPTIONS_READY
    _event(db, req, actor, "options_submitted")
    db.commit()
    db.refresh(req)
    return req


def mark_booked(db: Session, req: TripRequest, data: BookedIn, actor: Actor) -> TripRequest:
    _require(req, S.APPROVED)
    req.booking_reference = data.booking_reference
    req.booking_notes = data.booking_notes
    req.status = S.BOOKED
    _event(db, req, actor, "booked", data.booking_reference)
    db.commit()
    db.refresh(req)
    _notify_client(db, req, "booked")
    return req


# --- Messages -----------------------------------------------------------------------------------------

def post_message(db: Session, req: TripRequest, thread: str, actor: Actor, text: str) -> TripRequest:
    if req.status in (S.COMPLETED, S.CANCELLED) and actor.kind != "staff":
        raise HTTPException(409, "This request is closed")
    db.add(TripRequestMessage(company_id=req.company_id, request_id=req.id, thread=thread, author_kind=actor.kind,
                              author_name=actor.name, text=text))
    db.commit()
    db.refresh(req)
    return req


# --- WhatsApp -----------------------------------------------------------------------------------------

def numbered_options(req: TripRequest) -> list[tuple[int, TripOption]]:
    """The choices sent to the client, numbered 1, 2, 3… in the order shown (for WhatsApp replies)."""
    sent = [o for o in ordered(req.options) if o.sent_to_client]
    return list(enumerate(sent, start=1))


def _money(value: Decimal | None, currency: str) -> str:
    return "—" if value is None else f"{value:,.3f} {currency}"


def whatsapp_text(req: TripRequest, company: Company, what: str) -> str:
    cur = company.currency or "OMR"
    if what == "options":
        lines = [f"*{req.reference}* · {req.destination}",
                 "Your options are ready. Reply with the number of your choice for each part.",
                 "خياراتك جاهزة. رد برقم اختيارك لكل جزء.", ""]
        current = None
        for n, o in numbered_options(req):
            if o.category != current:
                current = o.category
                lines.append(f"*{o.category.capitalize()}*")
            lines.append(f"{n}. {o.title}" + (f" ({o.provider})" if o.provider else "") + f" · {_money(o.price, cur)}")
        return "\n".join(lines)
    if what == "approved":
        return (f"*{req.reference}* is approved ✅ We are booking it now and will send the booking reference.\n"
                f"تمت الموافقة على *{req.reference}* ✅ نقوم بالحجز الآن وسنرسل لك رقم الحجز.")
    if what == "booked":
        return (f"*{req.reference}* is booked ✈️ Booking reference: {req.booking_reference}\n"
                f"تم حجز *{req.reference}* ✈️ رقم الحجز: {req.booking_reference}")
    return (f"*{req.reference}* was cancelled. Contact us if you have a question.\n"
            f"تم إلغاء *{req.reference}*. تواصل معنا إذا عندك أي سؤال.")


def _notify_client(db: Session, req: TripRequest, what: str) -> None:
    """A request made on WhatsApp gets its updates in the same chat. Never fails the step."""
    if req.conversation_id is None:
        return
    try:
        conv = db.get(Conversation, req.conversation_id)
        if conv is None or conv.company_id != req.company_id:
            return
        company = db.get(Company, req.company_id)
        message = Message(conversation_id=conv.id, sender=Sender.AI, kind=MessageKind.TEXT,
                          content=whatsapp_text(req, company, what))
        db.add(message)
        db.commit()
        from .conversations import deliver  # noqa: PLC0415 (conversations imports the AI, which imports us)

        deliver(db, conv, message)
    except Exception:  # noqa: BLE001
        log.exception("Could not send the WhatsApp update of request %s", req.id)
        db.rollback()
