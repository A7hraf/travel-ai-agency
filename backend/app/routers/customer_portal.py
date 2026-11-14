"""The customer's private trips page (``/api/public/companies/{slug}/me``), and the feedback page of staff.

The customer's session token travels in the ``X-Customer-Token`` header (never in ``Authorization``, so a
staff login in the same browser is never mixed up with it). Every answer is about the signed-in customer only.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..addons import has_addon
from ..database import get_db
from ..deps import require_permission
from ..members import level_of
from ..models import Company, Conversation, Customer, MemberRequest, Message, Ticket, TripFeedback, User, utcnow
from ..netutil import client_ip
from ..ratelimit import limiter
from ..routers.public import _company
from ..services import customer_portal as svc
from ..services.conversations import is_customer_visible
from ..services.whatsapp import normalize_phone
from ..timeutil import local_today

router = APIRouter(tags=["customer portal"])
BASE = "/api/public/companies/{slug}/me"


class PhoneIn(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


class CodeIn(PhoneIn):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class LinkIn(BaseModel):
    key: str = Field(min_length=20, max_length=64)


class SessionOut(BaseModel):
    token: str


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class Me(BaseModel):
    name: str | None
    phone: str | None
    company_name: str
    member: dict | None  # level name and perks, when the company has the members community


class TripStep(BaseModel):
    action: str
    at: datetime


class TripOut(BaseModel):
    id: int
    reference: str
    title: str
    departure_date: str | None
    end_date: date | None
    adults: int
    children: int
    total_price: float
    currency: str
    status: str
    phase: str
    steps: list[TripStep]
    rating: int | None
    comment: str | None
    can_rate: bool


class ChatMessage(BaseModel):
    sender: str
    content: str
    created_at: datetime


class ChatOut(BaseModel):
    id: int
    channel: str
    created_at: datetime
    last_message_at: datetime
    messages: list[ChatMessage]


class RequestRow(BaseModel):
    title: str
    kind: str
    status: str
    created_at: datetime


def session(slug: str, x_customer_token: str | None = Header(default=None), db: Session = Depends(get_db)) -> Customer:
    company = _company(db, slug)
    return svc.customer_from_token(db, company, x_customer_token)


def _phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if phone is None:
        raise HTTPException(422, "Write your WhatsApp number with the country code, for example +968 9123 4567")
    return phone


@router.post(f"{BASE}/code", status_code=202)
def ask_code(slug: str, body: PhoneIn, request: Request, db: Session = Depends(get_db)):
    company = _company(db, slug)
    phone = _phone(body.phone)
    ip = client_ip(request)
    limiter.check(f"portal-code-ip:{ip}", 10, "Too many requests, please wait a few minutes", window=900)
    # Per number: a few codes per 15 minutes, and the same answer whether the number is known or not.
    if limiter.allow(f"portal-code:{company.id}:{phone}", 3, window=900):
        customer = svc.find_whatsapp_customer(db, company, phone)
        if customer is not None:
            svc.send_code(db, company, customer)
    return {"sent": True}


@router.post(f"{BASE}/verify", response_model=SessionOut)
def verify(slug: str, body: CodeIn, request: Request, db: Session = Depends(get_db)):
    company = _company(db, slug)
    limiter.check(f"portal-verify-ip:{client_ip(request)}", 20, "Too many tries, please wait a few minutes", window=900)
    customer = svc.verify_code(db, company, _phone(body.phone), body.code)
    return SessionOut(token=svc.create_token(customer))


@router.post(f"{BASE}/link", response_model=SessionOut)
def open_link(slug: str, body: LinkIn, request: Request, db: Session = Depends(get_db)):
    company = _company(db, slug)
    limiter.check(f"portal-link-ip:{client_ip(request)}", 20, "Too many tries, please wait a few minutes", window=900)
    return SessionOut(token=svc.create_token(svc.use_link(db, company, body.key)))


@router.get(BASE, response_model=Me)
def me(me: Customer = Depends(session), db: Session = Depends(get_db)):
    company = db.get(Company, me.company_id)
    member = None
    level = level_of(company, me.member_level) if has_addon(company, "members") else None
    if level is not None:
        member = {"key": me.member_level, "name_en": level.name_en, "name_ar": level.name_ar,
                  "perks_en": level.perks("en"), "perks_ar": level.perks("ar"),
                  "since": me.member_since.isoformat() if me.member_since else None}
    return Me(name=me.name, phone=me.phone, company_name=company.name, member=member)


@router.post(f"{BASE}/logout-everywhere", status_code=204)
def logout_everywhere(me: Customer = Depends(session), db: Session = Depends(get_db)):
    me.portal_valid_after = utcnow()
    db.commit()


def _trips(db: Session, customer: Customer) -> list[TripOut]:
    today = local_today()
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == customer.company_id,
                                              Ticket.customer_id == customer.id).order_by(Ticket.created_at.desc())).all()
    feedback = {f.ticket_id: f for f in db.scalars(select(TripFeedback).where(TripFeedback.customer_id == customer.id)).all()}
    out = []
    for t in tickets:
        fb = feedback.get(t.id)
        out.append(TripOut(
            id=t.id, reference=t.reference, title=t.package_title, departure_date=t.departure_date,
            end_date=svc.trip_end(t), adults=t.adults, children=t.children, total_price=round(float(t.total_price), 3),
            currency=t.currency, status=t.status, phase=svc.phase(t, today),
            steps=[TripStep(**s) for s in svc.customer_steps(db, t)],
            rating=fb.rating if fb else None, comment=fb.comment if fb else None,
            can_rate=svc.can_give_feedback(t, today, fb is not None)))
    return out


@router.get(f"{BASE}/trips", response_model=list[TripOut])
def trips(me: Customer = Depends(session), db: Session = Depends(get_db)):
    return _trips(db, me)


@router.post(f"{BASE}/trips/{{ticket_id}}/feedback", response_model=list[TripOut])
def give_feedback(ticket_id: int, body: FeedbackIn, me: Customer = Depends(session), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.customer_id != me.id or ticket.company_id != me.company_id:
        raise HTTPException(404, "Trip not found")
    svc.save_feedback(db, me, ticket, body.rating, body.comment, "portal", local_today())
    db.commit()
    return _trips(db, me)


@router.get(f"{BASE}/chats", response_model=list[ChatOut])
def chats(me: Customer = Depends(session), db: Session = Depends(get_db)):
    convs = db.scalars(select(Conversation).where(Conversation.company_id == me.company_id,
                                                  Conversation.customer_id == me.id)
                       .order_by(Conversation.last_message_at.desc()).limit(30)).all()
    out = []
    for c in convs:
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.id.desc()).limit(300)).all()
        out.append(ChatOut(id=c.id, channel=c.channel, created_at=c.created_at, last_message_at=c.last_message_at,
                           messages=[ChatMessage(sender=m.sender, content=m.content, created_at=m.created_at)
                                     for m in reversed(msgs) if is_customer_visible(m)]))
    return out


@router.get(f"{BASE}/requests", response_model=list[RequestRow])
def member_requests(me: Customer = Depends(session), db: Session = Depends(get_db)):
    reqs = db.scalars(select(MemberRequest).where(MemberRequest.company_id == me.company_id,
                                                  MemberRequest.customer_id == me.id)
                      .order_by(MemberRequest.created_at.desc()).limit(100)).all()
    return [RequestRow(title=r.title, kind=r.kind, status=r.status, created_at=r.created_at) for r in reqs]


# --- Staff: what customers said after their trips -------------------------------------------------

class FeedbackRow(BaseModel):
    id: int
    customer_id: int
    customer_name: str | None
    ticket_id: int
    reference: str
    title: str
    rating: int
    comment: str | None
    source: str
    created_at: datetime


class FeedbackList(BaseModel):
    average: float | None
    count: int
    by_rating: dict[int, int]
    feedback: list[FeedbackRow]


@router.get("/api/feedback", response_model=FeedbackList)
def staff_feedback(me: User = Depends(require_permission("reports.view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(TripFeedback).where(TripFeedback.company_id == me.company_id)
                      .order_by(TripFeedback.created_at.desc()).limit(500)).all()
    by = dict(db.execute(select(TripFeedback.rating, func.count(TripFeedback.id))
                         .where(TripFeedback.company_id == me.company_id).group_by(TripFeedback.rating)).all())
    count = sum(by.values())
    avg = round(sum(r * n for r, n in by.items()) / count, 2) if count else None
    return FeedbackList(average=avg, count=count, by_rating={r: by.get(r, 0) for r in range(1, 6)}, feedback=[
        FeedbackRow(id=f.id, customer_id=f.customer_id, customer_name=f.customer.name, ticket_id=f.ticket_id,
                    reference=f.ticket.reference, title=f.ticket.package_title, rating=f.rating, comment=f.comment,
                    source=f.source, created_at=f.created_at) for f in rows])
