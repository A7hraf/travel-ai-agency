"""Customer messages in, replies out, for every channel."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.agent import run_agent
from ..ai.prompts import FALLBACK_REPLY
from ..config import get_settings
from ..models import (
    Channel,
    Company,
    CompanyStatus,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageKind,
    Sender,
    utcnow,
)
from ..ratelimit import limiter
from .whatsapp import WhatsAppError, get_whatsapp_sender, parse_webhook

log = logging.getLogger(__name__)

# One AI run at a time per conversation (per process), so two quick messages from the
# same customer don't produce two overlapping answers.
_locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(conversation_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks[conversation_id]


def is_customer_visible(m: Message) -> bool:
    return m.kind == MessageKind.TEXT and m.sender in (Sender.CUSTOMER, Sender.AI, Sender.AGENT)


def handle_customer_message(db: Session, conversation: Conversation, text: str,
                            external_id: str | None = None) -> list[Message] | None:
    """Store the customer's message and let the AI answer if it is in charge.

    Returns the new replies for the customer ([] while a human handles the chat),
    or None when the message was a duplicate delivery.
    """
    with _lock_for(conversation.id):
        db.refresh(conversation)
        now = utcnow()
        if conversation.status == ConversationStatus.CLOSED:
            conversation.status = ConversationStatus.AI
            conversation.handover_reason = None
            db.add(Message(conversation_id=conversation.id, sender=Sender.SYSTEM, kind=MessageKind.TEXT,
                           content="The customer wrote again: conversation reopened with the AI"))
        conversation.last_message_at = now
        conversation.last_customer_message_at = now
        db.add(Message(conversation_id=conversation.id, sender=Sender.CUSTOMER, content=text,
                       external_id=external_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None

        if conversation.status != ConversationStatus.AI:
            return []

        hourly_cap = get_settings().ai_max_replies_per_company_per_hour
        if not limiter.allow(f"ai-replies:{conversation.company_id}", hourly_cap, window=3600):
            log.warning("Company %s reached %s AI replies this hour", conversation.company_id, hourly_cap)
            conversation.status = ConversationStatus.HUMAN
            conversation.was_handed_over = True
            conversation.handover_reason = "AI hourly limit reached, please answer the customer"
            db.add(Message(conversation_id=conversation.id, sender=Sender.SYSTEM, kind=MessageKind.TEXT,
                           content=f"Handed over to the team: the AI reached its limit of {hourly_cap} "
                                   "replies this hour"))
            reply = Message(conversation_id=conversation.id, sender=Sender.AI, content=FALLBACK_REPLY)
            db.add(reply)
            db.commit()
            return [reply]

        try:
            reply = run_agent(db, conversation)
            conversation.last_message_at = utcnow()
            db.commit()
        except Exception:
            log.exception("AI agent crashed for conversation %s", conversation.id)
            db.rollback()
            conversation.status = ConversationStatus.HUMAN
            conversation.was_handed_over = True
            conversation.handover_reason = "AI error, please answer the customer"
            reply = Message(conversation_id=conversation.id, sender=Sender.AI, content=FALLBACK_REPLY)
            db.add(reply)
            db.commit()
        return [reply]


def deliver(db: Session, conversation: Conversation, message: Message) -> None:
    """Send a reply over the conversation's channel (web chat replies are picked up by polling)."""
    if conversation.channel != Channel.WHATSAPP:
        return
    company = db.get(Company, conversation.company_id)
    try:
        wamid = get_whatsapp_sender().send_text(company, conversation.customer.whatsapp_id, message.content)
        message.delivery_status = "sent"
        if wamid:
            message.external_id = wamid
    except WhatsAppError as exc:
        log.warning("WhatsApp delivery failed for conversation %s: %s", conversation.id, exc)
        message.delivery_status = "failed"
    db.commit()


def _whatsapp_conversation(db: Session, company: Company, wa_id: str, profile_name: str | None) -> Conversation:
    customer = db.scalar(select(Customer).where(Customer.company_id == company.id, Customer.whatsapp_id == wa_id))
    if customer is None:
        customer = Customer(company_id=company.id, whatsapp_id=wa_id, phone=f"+{wa_id}", name=profile_name)
        db.add(customer)
        db.flush()
    elif profile_name and not customer.name:
        customer.name = profile_name

    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.customer_id == customer.id,
            Conversation.channel == Channel.WHATSAPP,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.id.desc())
    )
    if conversation is None:
        conversation = Conversation(company_id=company.id, customer_id=customer.id, channel=Channel.WHATSAPP)
        db.add(conversation)
    db.commit()
    return conversation


def process_whatsapp_payload(payload: dict, only_company_id: int | None = None) -> None:
    """Runs after the webhook has already answered 200 to Meta.

    only_company_id: the payload came through that company's own webhook (signed with its own
    Meta app secret), so it may only touch that company's number and messages.
    """
    from ..database import SessionLocal

    incoming, statuses = parse_webhook(payload)
    max_len = get_settings().public_chat_max_message_length
    db = SessionLocal()
    try:
        for status in statuses:
            stmt = select(Message).where(Message.external_id == status.message_id)
            if only_company_id is not None:
                stmt = stmt.join(Conversation, Conversation.id == Message.conversation_id).where(
                    Conversation.company_id == only_company_id
                )
            msg = db.scalar(stmt)
            if msg is not None and msg.delivery_status != "failed":
                msg.delivery_status = status.status
        db.commit()

        for item in incoming:
            company = db.scalar(select(Company).where(Company.whatsapp_phone_number_id == item.phone_number_id))
            if company is None or company.status != CompanyStatus.ACTIVE:
                log.info("Ignoring WhatsApp message for unknown/suspended number %s", item.phone_number_id)
                continue
            if only_company_id is not None and company.id != only_company_id:
                log.warning("Company %s webhook sent a message for another company's number; ignored",
                            only_company_id)
                continue
            if db.scalar(select(Message.id).where(Message.external_id == item.message_id)):
                continue  # Meta retried a delivery we already handled
            conversation = _whatsapp_conversation(db, company, item.wa_id, item.profile_name)
            get_whatsapp_sender().mark_read(company, item.message_id)
            replies = handle_customer_message(db, conversation, item.text[:max_len], external_id=item.message_id)
            for reply in replies or []:
                deliver(db, conversation, reply)
    finally:
        db.close()
