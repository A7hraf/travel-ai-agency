"""A client's request, from the AI's request card to the booked trip:

    NEW ─send choices─▶ QUOTED ─client picks─▶ CHOSEN ─send final─▶ FINAL ─client approves─▶ PENDING_PAYMENT
     ▲                    │                                           │
     └──── CHANGES ◀──────┴──────── the client asks for changes ──────┘   (or REJECTED / CANCELLED)

    PENDING_PAYMENT ─client says paid─▶ IN_PROGRESS ─staff check─▶ PAID ─booked & sent─▶ CONFIRMED

A ready-made package starts at PENDING_PAYMENT (its price is known). Every step is recorded (TicketEvent) and
the client gets each update in their own chat. Choices are the shared trip options (TripOption.ticket_id), so
the AI planner drafts and learns the same way as for business requests.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..catalog import check_answers
from ..addons import has_addon
from ..members import level_of
from ..models import (
    Company,
    Conversation,
    Customer,
    Service,
    Ticket,
    TicketEvent,
    TicketStatus as T,
    TripOption,
    User,
    utcnow,
)
from ..security import ticket_reference
from ..trip_schemas import CATEGORIES, MAX_CHOICES, MAX_OPTIONS
from . import trip_requests as shared
from .notify import say_in_chat

QUOTING = (T.NEW, T.QUOTED, T.CHANGES, T.CHOSEN, T.FINAL)  # before the client approves
EDITABLE = (T.NEW, T.CHANGES, T.CHOSEN)  # staff can change the choices
CLIENT_CAN_CANCEL = (*QUOTING, T.PENDING_PAYMENT)
WAITING_FOR_STAFF = (T.NEW, T.CHANGES, T.CHOSEN, T.IN_PROGRESS, T.PAID)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def event(db: Session, ticket: Ticket, actor: str, action: str, old=None, new=None, user: User | None = None) -> None:
    db.add(TicketEvent(ticket_id=ticket.id, user_id=user.id if user else None, actor=actor[:200], action=action,
                       old_value=None if old is None else str(old), new_value=None if new is None else str(new)))


def _require(ticket: Ticket, *statuses: str) -> None:
    if ticket.status not in statuses:
        raise HTTPException(409, f"This request is now '{ticket.status}', so this step is not possible.")


def _status(db: Session, ticket: Ticket, new: str, actor: str, user: User | None = None) -> None:
    event(db, ticket, actor, "status", ticket.status, new, user)
    ticket.status = new


# --- Creating (the AI's request card) -----------------------------------------------------------------

def create_request(db: Session, company: Company, customer: Customer, service: Service, answers: dict,
                   summary: str, conversation: Conversation | None, actor: str = "AI") -> Ticket:
    if service.company_id != company.id or not service.is_active or service.pricing == "packages":
        raise HTTPException(404, "Service not found")
    clean, missing = check_answers(service, answers)
    if missing:
        raise HTTPException(422, "Missing: " + ", ".join(missing))
    adults = int(clean["adults"]) if clean.get("adults", "").isdigit() else 1
    kids = re.match(r"\s*(\d+)", clean.get("children", ""))
    title = service.name_en + (f" · {clean['destination']}" if clean.get("destination") else "")
    fixed = service.pricing == "fixed" and service.price is not None
    for _ in range(5):
        ticket = Ticket(
            company_id=company.id, reference=ticket_reference(), conversation_id=conversation.id if conversation else None,
            customer_id=customer.id, service_id=service.id, package_title=title[:200], answers=clean,
            parts=list(service.parts or []), destination=clean.get("destination", "")[:120] or None,
            origin=clean.get("origin", "")[:120] or None, departure_date=clean.get("depart_date") or None,
            return_date=clean.get("return_date") or None, adults=max(1, min(adults, 500)),
            children=min(int(kids.group(1)), 50) if kids else 0,
            lead_traveler_name=(clean.get("full_name") or customer.name or "—")[:200],
            contact_phone=clean.get("phone") or customer.phone, contact_email=clean.get("email") or customer.email,
            special_requests=(summary or "").strip()[:4000],
            total_price=service.price if fixed else Decimal(0), currency=company.currency or "OMR",
            status=T.NEW, created_by="ai" if actor == "AI" else "staff", last_client_at=utcnow(),
        )
        try:
            with db.begin_nested():
                db.add(ticket)
                db.flush()
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(500, "Could not create the request, please try again")
    if clean.get("full_name") and not customer.name:
        customer.name = clean["full_name"][:200]
    if clean.get("phone") and not customer.phone:
        customer.phone = clean["phone"][:50]
    event(db, ticket, actor, "created", None, service.name_en)
    db.flush()
    return ticket


# --- Choices (up to 3 per part) -----------------------------------------------------------------------

def _option(ticket: Ticket, option_id: int) -> TripOption:
    option = next((o for o in ticket.options if o.id == option_id), None)
    if option is None:
        raise HTTPException(404, "Option not found")
    return option


def add_option(db: Session, ticket: Ticket, data: dict, user: User) -> None:
    _require(ticket, *EDITABLE)
    if len(ticket.options) >= MAX_OPTIONS:
        raise HTTPException(409, f"A request can have at most {MAX_OPTIONS} options")
    ticket.options.append(TripOption(company_id=ticket.company_id, added_by="staff", **data))
    event(db, ticket, user.full_name, "option_added", None, f"{data['category']}: {data['title']}", user)


def update_option(db: Session, ticket: Ticket, option_id: int, data: dict, user: User) -> None:
    _require(ticket, *EDITABLE)
    option = _option(ticket, option_id)
    for key, value in data.items():
        setattr(option, key, value)
    event(db, ticket, user.full_name, "option_changed", None, f"{option.category}: {option.title}", user)


def delete_option(db: Session, ticket: Ticket, option_id: int, user: User) -> None:
    _require(ticket, *EDITABLE)
    option = _option(ticket, option_id)
    if option.added_by == "ai":
        shared.signal(db, ticket, option, "removed")
    ticket.options.remove(option)
    event(db, ticket, user.full_name, "option_removed", None, f"{option.category}: {option.title}", user)


def ai_draft(db: Session, ticket: Ticket, company: Company, user: User) -> None:
    from ..ai import planner  # noqa: PLC0415

    _require(ticket, *EDITABLE)
    room = MAX_OPTIONS - len(ticket.options)
    parts = [p for p in (ticket.parts or []) if p in CATEGORIES]
    if room <= 0 or not parts:
        raise HTTPException(409, "This request has no parts to draft, or already has the most options")
    answers = ticket.answers or {}
    case = {"from": ticket.origin or "Muscat", "to": ticket.destination or answers.get("details", ""),
            "depart": ticket.departure_date, "return": ticket.return_date, "travellers": ticket.adults + ticket.children,
            "parts": parts, "budget": answers.get("budget"), "preferences": answers.get("preferences") or answers.get("details"),
            "notes": ticket.client_note}
    # The company's own saved suppliers for this place come first.
    saved = 0
    if has_addon(company, "library"):
        from . import library  # noqa: PLC0415

        have = {(o.category, (o.provider or o.title).lower()) for o in ticket.options}
        for part in parts:
            for s in library.matches(db, company.id, part, ticket.destination, limit=3):
                if room <= 0 or (part, s.name.lower()) in have:
                    continue
                data = library.option_from(s)
                ticket.options.append(TripOption(company_id=ticket.company_id, added_by="ai", estimate_price=s.usual_price,
                                                 ai_reason="From your library" + (" (preferred)" if s.preferred else ""),
                                                 **{k: v for k, v in data.items() if k != "price"}))
                room -= 1
                saved += 1
    if room <= 0:
        event(db, ticket, user.full_name, "ai_drafted", None, f"{saved} options from the library", user)
        return
    cleaned, searched = planner.suggest(db, company, case, room)
    for opt in cleaned:
        option = TripOption(company_id=ticket.company_id, category=opt["category"], title=opt["title"],
                            provider=opt["provider"], details=opt["details"], estimate_price=opt["estimate_price"],
                            ai_reason=opt["reason"], added_by="ai")
        ticket.options.append(option)
        shared.signal(db, ticket, option, "suggested")
    event(db, ticket, user.full_name, "ai_drafted", None, f"{len(cleaned) + saved} options" + (" · web search" if searched else "")
          + (f" · {saved} from the library" if saved else ""), user)


def send_choices(db: Session, company: Company, ticket: Ticket, option_ids: list[int], user: User) -> None:
    _require(ticket, *EDITABLE)
    wanted = set(option_ids)
    picked = [o for o in ticket.options if o.id in wanted]
    if not picked or len(picked) != len(wanted):
        raise HTTPException(404, "Option not found")
    for part in CATEGORIES:
        if sum(1 for o in picked if o.category == part) > MAX_CHOICES:
            raise HTTPException(422, f"Send at most {MAX_CHOICES} choices for each part")
    for o in picked:
        if o.price is None:
            raise HTTPException(422, f"Set the client price of \"{o.title}\" first")
    for o in ticket.options:
        o.sent_to_client = o.id in wanted
        o.chosen = False
        if o.id in wanted:
            shared.signal(db, ticket, o, "sent")
        elif o.added_by == "ai":
            shared.signal(db, ticket, o, "removed")
    ticket.quote_round += 1
    ticket.client_note = None
    _status(db, ticket, T.QUOTED, user.full_name, user)
    db.commit()
    say_in_chat(db, ticket.company_id, ticket.conversation_id, choices_text(ticket, company))


def send_final(db: Session, company: Company, ticket: Ticket, total: Decimal | None, note: str | None, user: User) -> None:
    """The final quotation: the client's picks (or a fixed price) with the final total."""
    if ticket.status == T.NEW and ticket.service is not None and ticket.service.pricing == "fixed":
        pass  # a fixed-price service goes straight to its final quotation
    else:
        _require(ticket, T.CHOSEN, T.CHANGES)
    chosen = [o for o in ticket.options if o.chosen]
    computed = sum((o.price for o in chosen if o.price is not None), Decimal(0)) if chosen else ticket.total_price
    final = (total if total is not None else computed).quantize(Decimal("0.001"))
    if final <= 0:
        raise HTTPException(422, "Set the final total first")
    if final != ticket.total_price:
        event(db, ticket, user.full_name, "price", ticket.total_price, final, user)
    ticket.total_price = final
    if note:
        event(db, ticket, user.full_name, "final_note", None, note.strip()[:1000], user)
    _status(db, ticket, T.FINAL, user.full_name, user)
    db.commit()
    say_in_chat(db, ticket.company_id, ticket.conversation_id, final_text(ticket, company, note))


# --- The client's answers (from the chat, the trips page, or staff writing them down) -----------------

def client_choose(db: Session, ticket: Ticket, option_ids: list[int], actor: str) -> None:
    _require(ticket, T.QUOTED)
    sent = [o for o in ticket.options if o.sent_to_client]
    wanted = set(option_ids)
    picked = [o for o in sent if o.id in wanted]
    if len(picked) != len(wanted) or not picked:
        raise HTTPException(404, "Option not found")
    if sorted(o.category for o in picked) != sorted({o.category for o in sent}):
        raise HTTPException(422, "Choose exactly one option for each part")
    for o in ticket.options:
        o.chosen = o.id in wanted
        if o.chosen:
            shared.signal(db, ticket, o, "chosen")
    ticket.last_client_at = utcnow()
    event(db, ticket, actor, "chosen", None, ", ".join(o.title for o in picked))
    _status(db, ticket, T.CHOSEN, actor)


def client_changes(db: Session, ticket: Ticket, note: str, actor: str) -> None:
    _require(ticket, T.QUOTED, T.FINAL)
    note = (note or "").strip()[:2000]
    if len(note) < 2:
        raise HTTPException(422, "Say what should change")
    ticket.client_note = note
    ticket.last_client_at = utcnow()
    event(db, ticket, actor, "changes", None, note)
    _status(db, ticket, T.CHANGES, actor)


def client_approve(db: Session, company: Company, ticket: Ticket, actor: str) -> None:
    _require(ticket, T.FINAL)
    ticket.last_client_at = utcnow()
    _status(db, ticket, T.PENDING_PAYMENT, actor)
    db.commit()
    say_in_chat(db, ticket.company_id, ticket.conversation_id, payment_text(ticket, company))


def client_reject(db: Session, ticket: Ticket, actor: str, note: str | None = None) -> None:
    _require(ticket, T.FINAL, T.QUOTED)
    ticket.client_note = (note or "").strip()[:2000] or None
    _status(db, ticket, T.REJECTED, actor)


def client_cancel(db: Session, ticket: Ticket, actor: str) -> None:
    from . import seats  # noqa: PLC0415

    _require(ticket, *CLIENT_CAN_CANCEL)
    seats.release(db, ticket)
    _status(db, ticket, T.CANCELLED, actor)


def client_paid(db: Session, ticket: Ticket, transfer_reference: str, actor: str) -> None:
    """The client says they paid (bank transfer number). Staff check it before the booking starts."""
    _require(ticket, T.PENDING_PAYMENT)
    ref = " ".join((transfer_reference or "").split())[:200]
    if len(ref) < 3:
        raise HTTPException(422, "Give the transfer or receipt number")
    ticket.payment_reference = ref
    ticket.last_client_at = utcnow()
    event(db, ticket, actor, "payment_reference", None, ref)
    _status(db, ticket, T.IN_PROGRESS, actor)


# --- Texts sent in the client's chat ------------------------------------------------------------------

def _money(v, cur: str) -> str:
    return f"{Decimal(v):,.3f} {cur}" if v is not None else "—"


PART_LABEL = {"flight": ("Flights", "الطيران"), "hotel": ("Hotels", "الفنادق"), "transport": ("Transport", "المواصلات"),
              "activity": ("Activities", "الأنشطة"), "food": ("Dining", "الطعام"), "visa": ("Visa", "التأشيرة"),
              "insurance": ("Insurance", "التأمين"), "other": ("Your request", "طلبك")}


def numbered(ticket: Ticket) -> list[tuple[int, TripOption]]:
    return list(enumerate([o for o in shared.ordered(ticket.options) if o.sent_to_client], start=1))


def choices_text(ticket: Ticket, company: Company) -> str:
    cur = ticket.currency
    lines = [f"*{ticket.reference}* · {ticket.package_title}",
             "Here are your options. Reply with the number of your choice for each part, or tell us what to change.",
             "هذه خياراتك. رد برقم اختيارك لكل جزء، أو أخبرنا بما تريد تغييره.", ""]
    current = None
    for n, o in numbered(ticket):
        if o.category != current:
            current = o.category
            en, ar = PART_LABEL.get(o.category, (o.category, o.category))
            lines.append(f"*{en} · {ar}*")
        line = f"{n}. {o.title}" + (f" ({o.provider})" if o.provider else "") + f" · {_money(o.price, cur)}"
        lines.append(line + (f"\n   {o.link}" if o.link else ""))
    return "\n".join(lines)


def final_text(ticket: Ticket, company: Company, note: str | None) -> str:
    chosen = [o for o in shared.ordered(ticket.options) if o.chosen]
    lines = [f"*{ticket.reference}* · final quotation · عرض السعر النهائي"]
    lines += [f"• {o.title}" + (f" ({o.provider})" if o.provider else "") for o in chosen]
    lines.append(f"*Total · الإجمالي: {_money(ticket.total_price, ticket.currency)}*")
    if note:
        lines.append(note.strip()[:600])
    lines.append("Reply *approve* to confirm, or tell us what to change.\nرد بـ *موافق* للتأكيد، أو أخبرنا بما تريد تغييره.")
    return "\n".join(lines)


def payment_text(ticket: Ticket, company: Company) -> str:
    info = company.payment_info if isinstance(company.payment_info, dict) else {}
    how = "\n".join(x for x in ((info.get("en") or "").strip(), (info.get("ar") or "").strip()) if x)
    return "\n".join(x for x in [
        f"*{ticket.reference}* approved ✅ Total: {_money(ticket.total_price, ticket.currency)}",
        "To confirm your booking, please pay and send us the transfer receipt here (a photo or PDF) or its number.",
        "لتأكيد الحجز، يرجى الدفع وإرسال إيصال التحويل هنا (صورة أو PDF) أو رقمه.",
        how or "Our team will send you the payment details. سيرسل لك فريقنا تفاصيل الدفع.",
    ] if x)


STATUS_TEXT = {
    T.PAID: ("Payment received for *{ref}* ✅ We are booking everything now.", "استلمنا الدفع لـ *{ref}* ✅ نقوم بالحجز الآن."),
    T.CONFIRMED: ("*{ref}* is fully booked ✈️ Your travel documents are on their way. Have a wonderful trip!",
                  "تم حجز *{ref}* بالكامل ✈️ وثائق سفرك في الطريق. رحلة سعيدة!"),
    T.CANCELLED: ("*{ref}* was cancelled. Contact us if you have a question.", "تم إلغاء *{ref}*. تواصل معنا إذا عندك سؤال."),
}


def notify_status(db: Session, ticket: Ticket) -> None:
    pair = STATUS_TEXT.get(ticket.status)
    if pair and ticket.service_id is not None:
        say_in_chat(db, ticket.company_id, ticket.conversation_id, "\n".join(p.format(ref=ticket.reference) for p in pair))


# --- Urgency (which request to work on first) ---------------------------------------------------------

def urgency(ticket: Ticket, company: Company, today: date, now: datetime | None = None) -> dict:
    """A score from 0 to 100 and its reasons: trip soon, client waiting, high value, member level."""
    if ticket.status not in WAITING_FOR_STAFF:
        return {"score": 0, "reasons": []}
    now = now or utcnow()
    score, reasons = 0, []
    try:
        days = (date.fromisoformat((ticket.departure_date or "")[:10]) - today).days
    except ValueError:
        days = None
    if days is not None and days <= 14:
        pts = 40 if days <= 3 else 25 if days <= 7 else 10
        score += pts
        reasons.append(f"trip in {max(days, 0)} days")
    since = _aware(ticket.last_client_at) or _aware(ticket.created_at)
    if since is not None:
        hours = (now - since).total_seconds() / 3600
        if hours >= 24:
            score += 25
            reasons.append(f"waiting {int(hours // 24)} days")
        elif hours >= 4:
            score += 12
            reasons.append(f"waiting {int(hours)} hours")
    value = Decimal(ticket.total_price or 0)
    if value >= 5000:
        score += 20
        reasons.append("high value")
    elif value >= 2000:
        score += 10
        reasons.append("high value")
    level = level_of(company, ticket.customer.member_level) if ticket.customer else None
    if level is not None:
        pts = 20 if ticket.customer.member_level == "vip" else 12 if ticket.customer.member_level == "level3" else 6
        score += pts
        reasons.append(f"{level.name_en} member")
    return {"score": min(score, 100), "reasons": reasons}


def find_for_customer(db: Session, company_id: int, customer_id: int, reference: str, lock: bool = False) -> Ticket | None:
    stmt = select(Ticket).where(Ticket.company_id == company_id, Ticket.customer_id == customer_id,
                                Ticket.reference == str(reference or "").strip().upper())
    return db.scalar(stmt.with_for_update() if lock else stmt)
