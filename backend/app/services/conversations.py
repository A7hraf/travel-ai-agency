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
from . import plans
from .instagram import (
    IncomingDM,
    InstagramError,
    ReadReceipt,
    get_instagram_sender,
    profile_name as instagram_profile_name,
)
from .instagram import refresh_token_if_due as refresh_instagram_token
from .instagram import parse_webhook as parse_instagram_webhook
from .whatsapp import IncomingMessage, StatusUpdate, WhatsAppError, get_whatsapp_sender, parse_webhook

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

        # The plan: the AI pauses after the subscription's grace period, and once the month's AI
        # conversations are used up new chats go to the team (chats already running continue).
        gate = plans.ai_gate(db, conversation)
        if gate is not None:
            reason, note = gate
            conversation.status = ConversationStatus.HUMAN
            conversation.was_handed_over = True
            conversation.handover_reason = reason
            db.add(Message(conversation_id=conversation.id, sender=Sender.SYSTEM, kind=MessageKind.TEXT, content=note))
            reply = Message(conversation_id=conversation.id, sender=Sender.AI, content=plans.TEAM_WILL_REPLY)
            db.add(reply)
            db.commit()
            return [reply]

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
    if conversation.channel == Channel.INSTAGRAM:
        _deliver_instagram(db, conversation, message)
        return
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


def _deliver_instagram(db: Session, conversation: Conversation, message: Message) -> None:
    company = db.get(Company, conversation.company_id)
    try:
        mid = get_instagram_sender().send_text(company, conversation.customer.instagram_id or "", message.content)
        message.delivery_status = "sent"
        if mid:
            message.external_id = mid
        db.commit()
    except InstagramError as exc:
        log.warning("Instagram delivery failed for conversation %s: %s", conversation.id, exc)
        message.delivery_status = "failed"
        db.commit()
    except IntegrityError:
        # The id Instagram gave back is already stored (should never happen): keep the message without it.
        db.rollback()
        message.delivery_status = "sent"
        db.commit()


def _channel_customer(db: Session, company: Company, column, external_id: str, **new_fields) -> Customer:
    """The company's customer with this WhatsApp/Instagram id, created on their first message."""
    stmt = select(Customer).where(Customer.company_id == company.id, column == external_id)
    customer = db.scalar(stmt)
    if customer is None:
        try:
            with db.begin_nested():
                customer = Customer(company_id=company.id, **new_fields)
                db.add(customer)
        except IntegrityError:
            # A second message from this new customer arrived at the same moment and created
            # them first: use that record instead of losing this message.
            customer = db.scalar(stmt)
            if customer is None:
                raise
    return customer


def _whatsapp_customer(db: Session, company: Company, wa_id: str, profile_name: str | None) -> Customer:
    customer = _channel_customer(db, company, Customer.whatsapp_id, wa_id,
                                 whatsapp_id=wa_id, phone=f"+{wa_id}", name=profile_name)
    if profile_name and not customer.name:
        customer.name = profile_name
    # A number linked to one of the company's business clients: the team sees which business writes.
    from .partners import partner_for_whatsapp  # noqa: PLC0415

    partner_id = partner_for_whatsapp(db, company.id, wa_id)
    if partner_id != customer.partner_id:
        customer.partner_id = partner_id
    return customer


def _open_channel_conversation(db: Session, customer: Customer, channel: str) -> Conversation | None:
    return db.scalar(
        select(Conversation)
        .where(
            Conversation.customer_id == customer.id,
            Conversation.channel == channel,
            Conversation.status != ConversationStatus.CLOSED,
        )
        .order_by(Conversation.id)
        .limit(1)
    )


def _open_whatsapp_conversation(db: Session, customer: Customer) -> Conversation | None:
    return _open_channel_conversation(db, customer, Channel.WHATSAPP)


def _open_instagram_conversation(db: Session, customer: Customer) -> Conversation | None:
    return _open_channel_conversation(db, customer, Channel.INSTAGRAM)


def _find_open(channel: str):
    # Looked up at call time (tests replace these functions to simulate a second message racing in).
    return _open_instagram_conversation if channel == Channel.INSTAGRAM else _open_whatsapp_conversation


def _channel_conversation(db: Session, company: Company, customer: Customer, channel: str) -> Conversation:
    """The customer's open conversation on this channel (a new one when there is none)."""
    # Lock the customer so two messages arriving together pick the same open conversation
    # (PostgreSQL waits here; SQLite already allows one writer at a time and ignores it).
    db.execute(select(Customer.id).where(Customer.id == customer.id).with_for_update())

    conversation = _find_open(channel)(db, customer)
    if conversation is None:
        conversation = Conversation(company_id=company.id, customer_id=customer.id, channel=channel)
        db.add(conversation)
        db.flush()
        # Another message may have opened one in the meantime: keep the oldest, so the
        # customer has a single open conversation.
        first = _find_open(channel)(db, customer)
        if first is not None and first.id != conversation.id:
            db.delete(conversation)
            conversation = first
    db.commit()
    return conversation


def _whatsapp_conversation(db: Session, company: Company, wa_id: str, profile_name: str | None) -> Conversation:
    customer = _whatsapp_customer(db, company, wa_id, profile_name)
    return _channel_conversation(db, company, customer, Channel.WHATSAPP)


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
        try:
            _apply_statuses(db, statuses, only_company_id)
        except Exception:
            log.exception("Could not store WhatsApp delivery statuses")
            db.rollback()

        for item in incoming:
            # Meta already got its 200: one broken message must not drop the others in the payload.
            try:
                _process_whatsapp_message(db, item, only_company_id, max_len)
            except Exception:
                log.exception("Could not process WhatsApp message %s", item.message_id)
                db.rollback()
    finally:
        db.close()


def _apply_statuses(db: Session, statuses: list[StatusUpdate], only_company_id: int | None) -> None:
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


def _process_whatsapp_message(db: Session, item: IncomingMessage, only_company_id: int | None, max_len: int) -> None:
    company = db.scalar(select(Company).where(Company.whatsapp_phone_number_id == item.phone_number_id))
    if company is None or company.status != CompanyStatus.ACTIVE:
        log.info("Ignoring WhatsApp message for unknown/suspended number %s", item.phone_number_id)
        return
    if only_company_id is not None and company.id != only_company_id:
        log.warning("Company %s webhook sent a message for another company's number; ignored", only_company_id)
        return
    if not plans.entitlements(db, company.id).whatsapp:
        log.info("Ignoring WhatsApp message for company %s: its plan does not include WhatsApp", company.id)
        return
    if db.scalar(select(Message.id).where(Message.external_id == item.message_id)):
        return  # Meta retried a delivery we already handled
    conversation = _whatsapp_conversation(db, company, item.wa_id, item.profile_name)
    get_whatsapp_sender().mark_read(company, item.message_id)
    replies = handle_customer_message(db, conversation, item.text[:max_len], external_id=item.message_id)
    for reply in replies or []:
        deliver(db, conversation, reply)


# --- Instagram Direct ------------------------------------------------------------------------------


def process_instagram_payload(payload: dict, company_id: int) -> None:
    """Runs after the company's Instagram webhook has already answered 200 to Meta.

    The payload was signed with this company's own app secret, so it may only touch this
    company's Instagram account: messages for any other account are ignored.
    """
    from ..database import SessionLocal

    incoming, reads = parse_instagram_webhook(payload)
    max_len = get_settings().public_chat_max_message_length
    db = SessionLocal()
    try:
        company = db.get(Company, company_id)
        if company is None or company.status != CompanyStatus.ACTIVE or not company.instagram_account_id:
            log.info("Ignoring Instagram webhook for company %s (unknown, suspended or not connected)", company_id)
            return
        if not plans.entitlements(db, company.id).instagram:
            log.info("Ignoring Instagram webhook for company %s: its plan does not include Instagram", company.id)
            return
        try:
            _apply_instagram_reads(db, company, reads)
        except Exception:
            log.exception("Could not store Instagram read receipts")
            db.rollback()
        for item in incoming:
            # Meta already got its 200: one broken message must not drop the others in the payload.
            try:
                _process_instagram_message(db, company, item, max_len)
            except Exception:
                log.exception("Could not process Instagram message %s", item.message_id)
                db.rollback()
        try:
            if incoming and refresh_instagram_token(company):
                db.commit()
        except Exception:
            log.exception("Could not renew the Instagram token of company %s", company.id)
            db.rollback()
    finally:
        db.close()


def _apply_instagram_reads(db: Session, company: Company, reads: list[ReadReceipt]) -> None:
    for read in reads:
        if read.account_id != company.instagram_account_id:
            continue
        msg = db.scalar(
            select(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(Customer, Customer.id == Conversation.customer_id)
            .where(Message.external_id == read.message_id, Conversation.company_id == company.id,
                   Customer.instagram_id == read.igsid)
        )
        if msg is not None and msg.delivery_status != "failed":
            msg.delivery_status = "read"
    db.commit()


def _process_instagram_message(db: Session, company: Company, item: IncomingDM, max_len: int) -> None:
    if item.account_id != company.instagram_account_id:
        log.warning("Company %s Instagram webhook sent a message for another account; ignored", company.id)
        return
    if db.scalar(select(Message.id).where(Message.external_id == item.message_id)):
        return  # Meta retried a delivery we already handled
    customer = _channel_customer(db, company, Customer.instagram_id, item.igsid, instagram_id=item.igsid)
    conversation = _channel_conversation(db, company, customer, Channel.INSTAGRAM)
    replies = handle_customer_message(db, conversation, item.text[:max_len], external_id=item.message_id)
    for reply in replies or []:
        deliver(db, conversation, reply)
    if replies is not None and not customer.name:
        # Best effort and only after the reply went out: the customer never waits for it.
        try:
            name = instagram_profile_name(get_instagram_sender().profile(company, item.igsid))
            if name:
                db.refresh(customer)
                customer.name = customer.name or name
                db.commit()
        except Exception:
            log.info("Could not read the Instagram name of customer %s", customer.id)
            db.rollback()
