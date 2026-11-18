"""Messages to many clients at once, and the check-in in the middle of a trip.

A broadcast goes on WhatsApp to the clients of a group (member level, label, a service they used, trips in a
period), each in their language. Outside WhatsApp's 24-hour window it needs the company's approved template,
like reminders. A feedback broadcast asks about each client's last trip; the AI records the answers."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..branding import clean_text
from ..language import Bi, pick
from ..models import Broadcast, Company, CompanyStatus, Conversation, Customer, Ticket, TicketStatus as T, User, utcnow
from .calendar import deliver
from .customer_portal import PAID, trip_end

MAX_RECIPIENTS = 1000
BOOKED = (*PAID, T.WORKING)


class Audience(BaseModel):
    member_levels: list[str] = Field(default_factory=list, max_length=10)  # empty: everyone
    tag: str | None = Field(default=None, max_length=40)
    service_id: int | None = None  # clients who asked for this service
    travelled_within_days: int | None = Field(default=None, ge=1, le=730)  # a trip ended in the last N days
    booked: bool | None = None  # True: booked at least once; False: never booked
    segment: str | None = Field(default=None, max_length=20)  # a client group (Client segments, targeting level)


class BroadcastIn(BaseModel):
    kind: str = Field(default="message", pattern="^(message|feedback)$")
    text_en: str = Field(default="", max_length=1000)
    text_ar: str = Field(default="", max_length=1000)
    audience: Audience = Field(default_factory=Audience)

    @field_validator("text_en", "text_ar")
    @classmethod
    def clean(cls, v: str) -> str:
        return clean_text(v or "", multiline=True)


def recipients(db: Session, company: Company, audience: Audience, today: date) -> list[Customer]:
    """The clients of the group who can be reached on WhatsApp."""
    stmt = select(Customer).where(Customer.company_id == company.id, Customer.whatsapp_id.is_not(None),
                                  Customer.partner_id.is_(None))
    if audience.member_levels:
        stmt = stmt.where(Customer.member_level.in_(audience.member_levels))
    rows = db.scalars(stmt).all()
    if audience.tag:
        tag = audience.tag.strip().lower()
        rows = [c for c in rows if tag in {t.lower() for t in c.tags or []}]
    if audience.service_id is not None or audience.travelled_within_days or audience.booked is not None:
        tickets = db.scalars(select(Ticket).where(Ticket.company_id == company.id,
                                                  Ticket.customer_id.in_([c.id for c in rows] or [0]))).all()
        by_customer: dict[int, list[Ticket]] = {}
        for t in tickets:
            by_customer.setdefault(t.customer_id, []).append(t)

        def keep(c: Customer) -> bool:
            mine = by_customer.get(c.id, [])
            if audience.service_id is not None and not any(t.service_id == audience.service_id for t in mine):
                return False
            if audience.booked is True and not any(t.status in BOOKED for t in mine):
                return False
            if audience.booked is False and any(t.status in BOOKED for t in mine):
                return False
            if audience.travelled_within_days:
                since = today - timedelta(days=audience.travelled_within_days)
                ends = [trip_end(t) for t in mine if t.status in BOOKED]
                if not any(e and since <= e < today for e in ends):
                    return False
            return True

        rows = [c for c in rows if keep(c)]
    if audience.segment:
        from .segments import segment_ids  # noqa: PLC0415

        ids = segment_ids(db, company, audience.segment, today)
        rows = [c for c in rows if c.id in ids]
    return rows[:MAX_RECIPIENTS]


def _language(db: Session, customer: Customer) -> str | None:
    return db.scalar(select(Conversation.language).where(Conversation.customer_id == customer.id,
                                                         Conversation.language.is_not(None))
                     .order_by(Conversation.last_message_at.desc()).limit(1))


def send(db: Session, company: Company, body: BroadcastIn, user: User, today: date) -> Broadcast:
    if not (body.text_en or body.text_ar) and body.kind == "message":
        raise HTTPException(422, "Write the message")
    people = recipients(db, company, body.audience, today)
    if not people:
        raise HTTPException(409, "No client in this group can be reached on WhatsApp")
    b = Broadcast(company_id=company.id, kind=body.kind, text_en=body.text_en, text_ar=body.text_ar,
                  audience=body.audience.model_dump(), created_by=user.full_name)
    db.add(b)
    sent = skipped = 0
    for c in people:
        lang = _language(db, c)
        if body.kind == "feedback":
            trip = next((t for t in sorted((t for t in db.scalars(select(Ticket).where(
                Ticket.customer_id == c.id, Ticket.status.in_(BOOKED))).all()), key=lambda t: t.departure_date or "",
                reverse=True) if trip_end(t) and trip_end(t) < today), None)
            if trip is None:
                skipped += 1
                continue
            name = (c.name or "").split(" ")[0]
            text = pick(Bi(f"Hello{' ' + name if name else ''}! How was your trip *{trip.package_title}*? Reply with a "
                           f"rating from 1 to 5 and a few words." + (f"\n{body.text_en}" if body.text_en else ""),
                           f"مرحبًا{' ' + name if name else ''}! كيف كانت رحلتك *{trip.package_title}*؟ رد بتقييم من 1 إلى 5 "
                           "وكلمتين عن التجربة." + (f"\n{body.text_ar}" if body.text_ar else "")), lang)
            trip.feedback_requested_at = trip.feedback_requested_at or utcnow()
        else:
            text = pick(Bi(body.text_en or body.text_ar, body.text_ar or body.text_en), lang)
        if deliver(db, company, c.whatsapp_id, text) is None:
            sent += 1
        else:
            skipped += 1
    b.sent, b.skipped = sent, skipped
    db.commit()
    return b


# --- In the middle of the trip ------------------------------------------------------------------------------

def send_checkins(db: Session, today: date) -> int:
    """Once per trip of 3 days or more, on its middle day: "how is your trip going?" (the AI records the answer)."""
    from .customer_portal import _departure  # noqa: PLC0415

    rows = db.scalars(select(Ticket).join(Company, Company.id == Ticket.company_id).where(
        Ticket.status.in_((T.CONFIRMED, T.PAID, T.WORKING)), Ticket.checkin.is_(None),
        Company.status == CompanyStatus.ACTIVE, Ticket.departure_date <= today.isoformat(),
        Ticket.departure_date >= (today - timedelta(days=60)).isoformat())).all()
    sent = 0
    for t in rows:
        start, end = _departure(t), trip_end(t)
        if not start or not end or (end - start).days < 2 or not start <= today <= end:
            continue
        if today < start + timedelta(days=(end - start).days // 2):
            continue
        wa_id = t.customer.whatsapp_id if t.customer else None
        t.checkin = {"asked_at": utcnow().isoformat()}
        if wa_id:
            lang = _language(db, t.customer)
            name = (t.lead_traveler_name or "").split(" ")[0]
            why = deliver(db, t.company, wa_id, pick(Bi(
                f"Hello{' ' + name if name else ''}! How is your trip *{t.package_title}* going so far? If anything "
                "is not right, tell us here and we'll help right away.",
                f"مرحبًا{' ' + name if name else ''}! كيف رحلتك *{t.package_title}* حتى الآن؟ إذا كان هناك أي شيء غير مناسب، "
                "أخبرنا هنا وسنساعدك فورًا."), lang))
            t.checkin["note"] = why
            sent += why is None
        db.commit()
    return sent
