"""Customers page: everyone who contacted the company, with their chats, bookings and amounts.

Staff with conversations.view see the list and the details; customers.manage edits contact details,
notes and labels and downloads the list as CSV. Every query is limited to the employee's company.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..csvutil import csv_response
from ..database import get_db
from ..deps import require_permission
from ..models import Conversation, Customer, Ticket, TicketStatus, User
from ..permissions import effective_permissions
from ..timeutil import local_today

router = APIRouter(prefix="/api/customers", tags=["customers"])

can_view = require_permission("conversations.view")
can_manage = require_permission("conversations.view", "customers.manage")

PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)
SORTS = ("last_contact", "first_contact", "name", "bookings", "booked", "conversations")
MAX_TAGS = 10
_EMAIL = TypeAdapter(EmailStr)


class CustomerRow(BaseModel):
    id: int
    name: str | None
    phone: str | None
    email: str | None
    channels: list[str]
    first_contact: datetime | None
    last_contact: datetime | None
    conversations: int
    bookings: int
    total_booked: float
    total_paid: float
    tags: list[str]


class CustomerList(BaseModel):
    customers: list[CustomerRow]
    total: int
    currency: str


class CustomerConversation(BaseModel):
    id: int
    channel: str
    status: str
    created_at: datetime
    last_message_at: datetime


class CustomerTicket(BaseModel):
    id: int
    reference: str
    package_title: str
    departure_date: str | None
    status: str
    total_price: float
    currency: str
    created_at: datetime


class CustomerDetail(CustomerRow):
    notes: str
    whatsapp_id: str | None
    instagram: bool
    created_at: datetime
    conversation_list: list[CustomerConversation]
    ticket_list: list[CustomerTicket]
    can_see_tickets: bool
    currency: str


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)  # empty clears it
    notes: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return str(_EMAIL.validate_python(v)).lower() if v else v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for tag in v:
            tag = " ".join(str(tag).split())[:40]
            if tag and tag.lower() not in {t.lower() for t in out}:
                out.append(tag)
        return out


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _rows(db: Session, me: User, q: str | None, channel: str | None, has_booking: bool | None, sort: str,
          limit: int | None) -> tuple[list[CustomerRow], int]:
    cid = me.company_id
    currency = me.company.currency
    convs = (
        select(Conversation.customer_id.label("customer_id"), func.count(Conversation.id).label("n"),
               func.min(Conversation.created_at).label("first"), func.max(Conversation.last_message_at).label("last"))
        .where(Conversation.company_id == cid).group_by(Conversation.customer_id).subquery()
    )
    booked = Ticket.status != TicketStatus.CANCELLED
    same_currency = Ticket.currency == currency
    tickets = (
        select(
            Ticket.customer_id.label("customer_id"),
            func.sum(case((booked, 1), else_=0)).label("n"),
            func.sum(case((booked & same_currency, Ticket.total_price), else_=0)).label("booked"),
            func.sum(case((Ticket.status.in_(PAID) & same_currency, Ticket.total_price), else_=0)).label("paid"),
        ).where(Ticket.company_id == cid).group_by(Ticket.customer_id).subquery()
    )
    n_bookings = func.coalesce(tickets.c.n, 0)
    n_convs = func.coalesce(convs.c.n, 0)
    total_booked = func.coalesce(tickets.c.booked, 0)
    first = func.coalesce(convs.c.first, Customer.created_at)
    last = func.coalesce(convs.c.last, Customer.created_at)
    stmt = (
        select(Customer, n_convs, first, last, n_bookings, total_booked, func.coalesce(tickets.c.paid, 0))
        .outerjoin(convs, convs.c.customer_id == Customer.id)
        .outerjoin(tickets, tickets.c.customer_id == Customer.id)
        .where(Customer.company_id == cid)
    )
    if q and q.strip():
        like = _like(q.strip())
        stmt = stmt.where(or_(Customer.name.ilike(like, escape="\\"), Customer.phone.ilike(like, escape="\\"),
                              Customer.email.ilike(like, escape="\\"), Customer.whatsapp_id.ilike(like, escape="\\")))
    if channel:
        stmt = stmt.where(Customer.id.in_(select(Conversation.customer_id).where(
            Conversation.company_id == cid, Conversation.channel == channel)))
    if has_booking is True:
        stmt = stmt.where(n_bookings > 0)
    elif has_booking is False:
        stmt = stmt.where(n_bookings == 0)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {
        "last_contact": [last.desc()],
        "first_contact": [first.asc()],
        "name": [func.lower(func.coalesce(Customer.name, "")).asc()],
        "bookings": [n_bookings.desc(), last.desc()],
        "booked": [total_booked.desc(), last.desc()],
        "conversations": [n_convs.desc(), last.desc()],
    }[sort]
    stmt = stmt.order_by(*order, Customer.id.desc())
    if limit:
        stmt = stmt.limit(limit)
    result = db.execute(stmt).all()
    ids = [r[0].id for r in result]
    channels: dict[int, set[str]] = {}
    if ids:
        for customer_id, ch in db.execute(select(Conversation.customer_id, Conversation.channel).where(
                Conversation.company_id == cid, Conversation.customer_id.in_(ids)).distinct()):
            channels.setdefault(customer_id, set()).add(ch)
    rows = [
        CustomerRow(id=c.id, name=c.name, phone=c.phone, email=c.email, channels=sorted(channels.get(c.id, set())),
                    first_contact=f, last_contact=lst, conversations=int(nc or 0), bookings=int(nb or 0),
                    total_booked=round(float(tb or 0), 3), total_paid=round(float(tp or 0), 3), tags=list(c.tags or []))
        for c, nc, f, lst, nb, tb, tp in result
    ]
    return rows, total


def _filters(q: str | None = Query(default=None, max_length=100),
             channel: str | None = Query(default=None, pattern="^(web|whatsapp|instagram)$"),
             has_booking: bool | None = None,
             sort: str = Query(default="last_contact", pattern="^(" + "|".join(SORTS) + ")$")) -> dict:
    return {"q": q, "channel": channel, "has_booking": has_booking, "sort": sort}


@router.get("", response_model=CustomerList)
def list_customers(f: dict = Depends(_filters), limit: int = Query(default=200, ge=1, le=1000),
                   me: User = Depends(can_view), db: Session = Depends(get_db)):
    rows, total = _rows(db, me, limit=limit, **f)
    return CustomerList(customers=rows, total=total, currency=me.company.currency)


@router.get("/export.csv")
def export_customers(f: dict = Depends(_filters), me: User = Depends(can_manage), db: Session = Depends(get_db)):
    rows, _ = _rows(db, me, limit=None, **f)
    cur = me.company.currency
    header = ["Name", "Phone", "Email", "Channels", "First contact", "Last contact", "Conversations", "Bookings",
              f"Total booked ({cur})", f"Total paid ({cur})", "Labels"]
    return csv_response(
        f"customers-{local_today().isoformat()}.csv", header,
        ([r.name, r.phone, r.email, " ".join(r.channels), r.first_contact, r.last_contact, r.conversations,
          r.bookings, f"{r.total_booked:.3f}", f"{r.total_paid:.3f}", ", ".join(r.tags)] for r in rows),
    )


def _get(db: Session, me: User, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.company_id != me.company_id:
        raise HTTPException(404, "Customer not found")
    return customer


def _detail(db: Session, me: User, customer: Customer) -> CustomerDetail:
    cid = me.company_id
    convs = db.scalars(select(Conversation).where(Conversation.company_id == cid,
                                                  Conversation.customer_id == customer.id)
                       .order_by(Conversation.last_message_at.desc())).all()
    tickets = db.scalars(select(Ticket).where(Ticket.company_id == cid, Ticket.customer_id == customer.id)
                         .order_by(Ticket.id.desc())).all()
    currency = me.company.currency
    live = [t for t in tickets if t.status != TicketStatus.CANCELLED]
    can_tickets = "tickets.view" in effective_permissions(me)
    return CustomerDetail(
        id=customer.id, name=customer.name, phone=customer.phone, email=customer.email,
        channels=sorted({c.channel for c in convs}),
        first_contact=min([c.created_at for c in convs], default=customer.created_at),
        last_contact=max([c.last_message_at for c in convs], default=customer.created_at),
        conversations=len(convs), bookings=len(live),
        total_booked=round(float(sum(t.total_price for t in live if t.currency == currency)), 3),
        total_paid=round(float(sum(t.total_price for t in live if t.currency == currency and t.status in PAID)), 3),
        tags=list(customer.tags or []), notes=customer.notes or "", whatsapp_id=customer.whatsapp_id,
        instagram=bool(customer.instagram_id), created_at=customer.created_at,
        conversation_list=[CustomerConversation(id=c.id, channel=c.channel, status=c.status, created_at=c.created_at,
                                                last_message_at=c.last_message_at) for c in convs],
        ticket_list=[CustomerTicket(id=t.id, reference=t.reference, package_title=t.package_title,
                                    departure_date=t.departure_date, status=t.status,
                                    total_price=round(float(t.total_price), 3), currency=t.currency,
                                    created_at=t.created_at) for t in tickets] if can_tickets else [],
        can_see_tickets=can_tickets,
        currency=currency,
    )


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: int, me: User = Depends(can_view), db: Session = Depends(get_db)):
    return _detail(db, me, _get(db, me, customer_id))


@router.patch("/{customer_id}", response_model=CustomerDetail)
def update_customer(customer_id: int, body: CustomerUpdate, me: User = Depends(can_manage),
                    db: Session = Depends(get_db)):
    customer = _get(db, me, customer_id)
    changed = []
    data = body.model_dump(exclude_unset=True)
    for key in ("name", "phone", "email", "notes"):
        if key in data:
            value = " ".join(str(data[key] or "").split()) if key != "notes" else (data[key] or "").strip()
            value = value or None
            if key == "email" and value:
                value = value.lower()
            if value != getattr(customer, key):
                setattr(customer, key, value)
                changed.append(key)
    if "tags" in data and (data["tags"] or []) != list(customer.tags or []):
        customer.tags = data["tags"] or []
        changed.append("labels")
    if changed:
        audit(db, me, "customer.updated", target=customer.name or f"#{customer.id}",
              detail=", ".join(changed))
    db.commit()
    db.refresh(customer)
    return _detail(db, me, customer)
