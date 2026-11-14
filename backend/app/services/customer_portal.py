"""A customer's private trips page: their bookings (with where each one stands), their chats, their member
requests and their feedback.

Getting in proves the customer owns the WhatsApp number the company knows them by:

* a link the AI sends in the customer's own WhatsApp chat (writing from that number is the proof), or
* a 6-digit code sent to that number (WhatsApp delivers it only within 24 hours of their last message).

Codes and links are random, stored only as a hash, short-lived, used once, and a code allows 5 tries.
The answer to "send me a code" never says whether the number is known. The session is a token for this
one customer of this one company, which no staff endpoint accepts (and the staff token is refused here).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Channel,
    Company,
    CompanyStatus,
    Conversation,
    Customer,
    CustomerAccessCode,
    MemberRequest,
    Message,
    MessageKind,
    Sender,
    Ticket,
    TicketEvent,
    TicketStatus,
    TripFeedback,
    utcnow,
)

log = logging.getLogger(__name__)

AUDIENCE = "customer-portal"
CODE_MINUTES = 10
LINK_MINUTES = 30
CODE_TRIES = 5
WINDOW = timedelta(hours=24)
FEEDBACK_DAYS = 30  # feedback can be given up to this many days after the trip
PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Session token --------------------------------------------------------------------------------------

def create_token(customer: Customer) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {"sub": f"customer:{customer.id}", "co": customer.company_id, "aud": AUDIENCE,
              "iat": int(now.timestamp()), "iat_ms": int(now.timestamp() * 1000),
              "exp": now + timedelta(days=settings.customer_session_days)}
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def customer_from_token(db: Session, company: Company, token: str | None) -> Customer:
    """The signed-in customer of this company, or 401."""
    unauthorized = HTTPException(401, "Please sign in again")
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"], audience=AUDIENCE,
                             options={"require": ["exp", "iat", "sub", "aud"]})
        kind, _, raw_id = str(payload["sub"]).partition(":")
        customer_id, company_id, issued_ms = int(raw_id), int(payload["co"]), int(payload["iat_ms"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise unauthorized from None
    if kind != "customer" or company_id != company.id:
        raise unauthorized
    customer = db.get(Customer, customer_id)
    if customer is None or customer.company_id != company.id:
        raise unauthorized
    valid_after = _aware(customer.portal_valid_after)
    if valid_after is not None and issued_ms < int(valid_after.timestamp() * 1000):
        raise unauthorized
    return customer


# --- Codes and links ------------------------------------------------------------------------------------

def _new_access(db: Session, customer: Customer, kind: str, secret: str, minutes: int) -> None:
    # A new code replaces the earlier ones of the same kind.
    for old in db.scalars(select(CustomerAccessCode).where(CustomerAccessCode.customer_id == customer.id,
                                                           CustomerAccessCode.kind == kind,
                                                           CustomerAccessCode.used_at.is_(None))).all():
        old.used_at = utcnow()
    db.add(CustomerAccessCode(company_id=customer.company_id, customer_id=customer.id, kind=kind,
                              secret_hash=_hash(secret), expires_at=utcnow() + timedelta(minutes=minutes)))


def find_whatsapp_customer(db: Session, company: Company, phone: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.company_id == company.id, Customer.whatsapp_id == phone))


def send_code(db: Session, company: Company, customer: Customer) -> None:
    """Creates a code and sends it on WhatsApp. Never raises: the caller answers the same either way."""
    from .whatsapp import WhatsAppError, get_whatsapp_sender  # noqa: PLC0415

    code = f"{secrets.randbelow(1_000_000):06d}"
    _new_access(db, customer, "code", code, CODE_MINUTES)
    db.commit()
    text = (f"{code} is your code for your trips page at {company.name}. It works for {CODE_MINUTES} minutes. "
            f"Never share it.\n{code} هو رمز صفحة رحلاتك لدى {company.name}، صالح لمدة {CODE_MINUTES} دقائق. "
            "لا تشاركه مع أحد.")
    try:
        get_whatsapp_sender().send_text(company, customer.whatsapp_id, text)
    except WhatsAppError as exc:
        log.info("Trips-page code not delivered to customer %s: %s", customer.id, exc)
    except Exception:  # noqa: BLE001
        log.exception("Trips-page code failed for customer %s", customer.id)


def verify_code(db: Session, company: Company, phone: str, code: str) -> Customer:
    wrong = HTTPException(400, "This code is wrong or expired. Ask for a new one.")
    customer = find_whatsapp_customer(db, company, phone)
    if customer is None:
        raise wrong
    access = db.scalar(select(CustomerAccessCode).where(
        CustomerAccessCode.customer_id == customer.id, CustomerAccessCode.kind == "code",
        CustomerAccessCode.used_at.is_(None)).order_by(CustomerAccessCode.id.desc()).with_for_update())
    if access is None or _aware(access.expires_at) < utcnow() or access.attempts >= CODE_TRIES:
        raise wrong
    access.attempts += 1
    if not secrets.compare_digest(access.secret_hash, _hash(code.strip())):
        db.commit()
        raise wrong
    access.used_at = utcnow()
    db.commit()
    return customer


def make_link(db: Session, company: Company, customer: Customer) -> str:
    secret = secrets.token_urlsafe(24)
    _new_access(db, customer, "link", secret, LINK_MINUTES)
    db.flush()
    # The secret is after "#", so it never reaches server logs or other sites.
    return f"{get_settings().site_url}/c/{company.slug}/me#k={secret}"


def use_link(db: Session, company: Company, secret: str) -> Customer:
    expired = HTTPException(400, "This link has expired or was already used. Ask us for a new one on WhatsApp.")
    access = db.scalar(select(CustomerAccessCode).where(
        CustomerAccessCode.company_id == company.id, CustomerAccessCode.kind == "link",
        CustomerAccessCode.secret_hash == _hash(secret or "")).with_for_update())
    if access is None or access.used_at is not None or _aware(access.expires_at) < utcnow():
        raise expired
    access.used_at = utcnow()
    db.commit()
    customer = db.get(Customer, access.customer_id)
    if customer is None or customer.company_id != company.id:
        raise expired
    return customer


# --- Trips --------------------------------------------------------------------------------------------

def _departure(ticket: Ticket) -> date | None:
    try:
        return date.fromisoformat((ticket.departure_date or "")[:10])
    except ValueError:
        return None


def trip_end(ticket: Ticket) -> date | None:
    start = _departure(ticket)
    if start is None:
        return None
    days = ticket.package.duration_days if ticket.package is not None else 1
    return start + timedelta(days=max(0, (days or 1) - 1))


def phase(ticket: Ticket, today: date) -> str:
    """booking (not paid yet), upcoming, travelling, finished or cancelled."""
    if ticket.status == TicketStatus.CANCELLED:
        return "cancelled"
    if ticket.status not in PAID:
        return "booking"
    start, end = _departure(ticket), trip_end(ticket)
    if start is None or today < start:
        return "upcoming"
    if end is not None and today <= end:
        return "travelling"
    return "finished"


def can_give_feedback(ticket: Ticket, today: date, has_feedback: bool) -> bool:
    end = trip_end(ticket)
    return (not has_feedback and phase(ticket, today) == "finished" and end is not None
            and (today - end).days <= FEEDBACK_DAYS)


def customer_steps(db: Session, ticket: Ticket) -> list[dict]:
    """Only what the customer may see: when it was booked and each status, never notes, prices or staff."""
    events = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)).all()
    steps = [{"action": "created", "at": ticket.created_at}]
    steps += [{"action": e.new_value, "at": e.created_at} for e in events
              if e.action == "status" and e.new_value in {s.value for s in TicketStatus}]
    return steps


def finished_without_feedback(db: Session, customer: Customer, today: date) -> list[Ticket]:
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == customer.company_id,
                                              Ticket.customer_id == customer.id,
                                              Ticket.status.in_(PAID))).all()
    rated = set(db.scalars(select(TripFeedback.ticket_id).where(TripFeedback.customer_id == customer.id)).all())
    return [t for t in tickets if can_give_feedback(t, today, t.id in rated)]


def save_feedback(db: Session, customer: Customer, ticket: Ticket, rating: int, comment: str | None,
                  source: str, today: date) -> TripFeedback:
    if ticket.customer_id != customer.id or ticket.company_id != customer.company_id:
        raise HTTPException(404, "Trip not found")
    exists = db.scalar(select(TripFeedback.id).where(TripFeedback.ticket_id == ticket.id))
    if exists or not can_give_feedback(ticket, today, False):
        raise HTTPException(409, "Feedback can be given once, after the trip.")
    if not 1 <= int(rating) <= 5:
        raise HTTPException(422, "The rating is from 1 to 5")
    fb = TripFeedback(company_id=customer.company_id, customer_id=customer.id, ticket_id=ticket.id,
                      rating=int(rating), comment=(comment or "").strip()[:2000] or None, source=source)
    db.add(fb)
    db.flush()
    return fb


# --- "How was your trip?" on WhatsApp ----------------------------------------------------------------

def send_feedback_requests(db: Session, today: date) -> int:
    """For trips that ended in the last days: ask on WhatsApp while the 24-hour window is open (outside it,
    the AI asks the next time the customer writes). Each booking is asked once."""
    from .conversations import deliver  # noqa: PLC0415

    since = today - timedelta(days=14)
    tickets = db.scalars(select(Ticket).join(Company, Company.id == Ticket.company_id).where(
        Ticket.status.in_(PAID), Ticket.feedback_requested_at.is_(None), Company.status == CompanyStatus.ACTIVE,
        Ticket.departure_date >= since.isoformat(), Ticket.departure_date <= today.isoformat())).all()
    sent = 0
    for ticket in tickets:
        end = trip_end(ticket)
        if end is None or not (since <= end < today):
            continue
        if db.scalar(select(TripFeedback.id).where(TripFeedback.ticket_id == ticket.id)):
            ticket.feedback_requested_at = utcnow()
            continue
        conv = db.scalar(select(Conversation).where(
            Conversation.company_id == ticket.company_id, Conversation.customer_id == ticket.customer_id,
            Conversation.channel == Channel.WHATSAPP).order_by(Conversation.last_customer_message_at.desc()))
        last = _aware(conv.last_customer_message_at) if conv else None
        if conv is None or last is None or utcnow() - last > WINDOW:
            continue
        name = (ticket.lead_traveler_name or "").split(" ")[0]
        message = Message(conversation_id=conv.id, sender=Sender.AI, kind=MessageKind.TEXT, content=(
            f"Welcome back{', ' + name if name else ''}! How was your trip *{ticket.package_title}*? "
            "Reply with a rating from 1 to 5 and a few words, it helps us a lot.\n"
            f"حمدالله على السلامة! كيف كانت رحلتك *{ticket.package_title}*؟ رد بتقييم من 1 إلى 5 وكلمتين عن التجربة."))
        db.add(message)
        ticket.feedback_requested_at = utcnow()
        db.commit()
        deliver(db, conv, message)
        sent += 1
    db.commit()
    return sent
