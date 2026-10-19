"""Customer-facing API: a company's offers page and web chat with the AI agent."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.prompts import welcome_message
from ..ai.tools import is_bookable
from ..branding import public_branding
from ..config import get_settings
from ..database import get_db
from ..models import (
    Channel,
    Company,
    CompanyStatus,
    Conversation,
    Customer,
    Message,
    Sender,
    TravelPackage,
    utcnow,
)
from ..ratelimit import limiter
from ..schemas import (
    ChatMessagesOut,
    CustomerMessageIn,
    PublicCompanyOut,
    PublicPackageOut,
    StartChatIn,
    StartChatOut,
)
from ..security import random_token
from ..serializers import public_message_out
from ..services.conversations import handle_customer_message, is_customer_visible
from ..timeutil import local_today

router = APIRouter(prefix="/api/public/companies/{slug}", tags=["public"])


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _company(db: Session, slug: str) -> Company:
    company = db.scalar(select(Company).where(Company.slug == slug))
    if company is None or company.status != CompanyStatus.ACTIVE:
        raise HTTPException(404, "Travel agency not found")
    return company


def _conversation(db: Session, company: Company, token: str) -> Conversation:
    conv = db.scalar(select(Conversation).where(Conversation.public_token == token))
    if conv is None or conv.company_id != company.id:
        raise HTTPException(404, "Chat not found")
    # A chat link left on a shared device must not open an old chat forever: after a quiet
    # month it behaves like an unknown link and the page starts a new chat.
    if conv.last_message_at < utcnow() - timedelta(days=get_settings().public_chat_resume_days):
        raise HTTPException(404, "Chat not found")
    return conv


@router.get("", response_model=PublicCompanyOut)
def company_info(slug: str, db: Session = Depends(get_db)):
    c = _company(db, slug)
    return PublicCompanyOut(
        name=c.name,
        slug=c.slug,
        ai_agent_name=c.ai_agent_name,
        welcome_message=welcome_message(c),
        currency=c.currency,
        whatsapp_number=c.whatsapp_display_number,
        contact_email=c.contact_email,
        contact_phone=c.contact_phone,
        branding=public_branding(c),
    )


@router.get("/packages", response_model=list[PublicPackageOut])
def packages(slug: str, db: Session = Depends(get_db)):
    company = _company(db, slug)
    rows = db.scalars(select(TravelPackage).where(TravelPackage.company_id == company.id)).all()
    today = local_today()
    visible = [p for p in rows if is_bookable(p, today)]
    visible.sort(key=lambda p: (not p.is_featured, p.price_per_person))
    out = []
    for p in visible:  # customers only need the dates still ahead
        item = PublicPackageOut.model_validate(p)
        item.departure_dates = [d for d in item.departure_dates if d >= today.isoformat()]
        out.append(item)
    return out


@router.post("/chats", response_model=StartChatOut, status_code=201)
def start_chat(slug: str, body: StartChatIn, request: Request, db: Session = Depends(get_db)):
    company = _company(db, slug)
    limiter.check(f"start:{client_ip(request)}", 10)
    # Limits that don't depend on the visitor's address: one sender can't flood a company with chats.
    limiter.check(f"start-company:{company.id}", 60, "Too many new chats right now, please try again in a minute")
    limiter.check(f"start-company-hour:{company.id}", 1000, "Too many new chats right now, please try again later",
                  window=3600)
    customer = Customer(
        company_id=company.id,
        name=(body.name or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        email=body.email,
    )
    db.add(customer)
    db.flush()
    conv = Conversation(company_id=company.id, customer_id=customer.id, channel=Channel.WEB,
                        public_token=random_token())
    db.add(conv)
    db.flush()
    welcome = Message(conversation_id=conv.id, sender=Sender.AI, content=welcome_message(company, body.lang))
    db.add(welcome)
    db.commit()
    return StartChatOut(token=conv.public_token, status=conv.status, messages=[public_message_out(welcome)])


@router.post("/chats/{token}/messages", response_model=ChatMessagesOut)
def send_message(slug: str, token: str, body: CustomerMessageIn, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    company = _company(db, slug)
    conv = _conversation(db, company, token)
    text = body.content.strip()
    if not text:
        raise HTTPException(422, "Message is empty")
    if len(text) > settings.public_chat_max_message_length:
        raise HTTPException(413, "Message is too long")
    limiter.check(f"chat:{token}", settings.public_chat_max_messages_per_minute,
                  "Too many messages, please wait a moment")
    limiter.check(f"chat-ip:{client_ip(request)}", settings.public_chat_max_messages_per_ip_per_minute,
                  "Too many messages, please wait a moment")
    limiter.check(f"chat-hour:{token}", 120, "This chat has too many messages, please call us", window=3600)

    last_id = db.scalar(select(Message.id).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(1)) or 0
    handle_customer_message(db, conv, text)
    return _messages_after(db, conv, last_id)


@router.get("/chats/{token}/messages", response_model=ChatMessagesOut)
def poll_messages(slug: str, token: str, after_id: int = 0, db: Session = Depends(get_db)):
    company = _company(db, slug)
    return _messages_after(db, _conversation(db, company, token), after_id)


def _messages_after(db: Session, conv: Conversation, after_id: int) -> ChatMessagesOut:
    db.refresh(conv)
    rows = db.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.id > after_id).order_by(Message.id)
    ).all()
    return ChatMessagesOut(
        status=conv.status, messages=[public_message_out(m) for m in rows if is_customer_visible(m)]
    )
