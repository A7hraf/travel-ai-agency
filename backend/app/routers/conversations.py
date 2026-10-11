"""Employee view of customer conversations: watch the AI, take over, reply, hand back."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_permission
from ..models import Conversation, ConversationStatus, Customer, Message, MessageKind, Sender, User, utcnow
from ..schemas import AgentMessageIn, ConversationDetail, ConversationSummary, MessageOut
from ..serializers import conversation_detail, conversation_summary, message_out
from ..services.conversations import deliver

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

can_view = require_permission("conversations.view")
can_reply = require_permission("conversations.reply")


def _get(db: Session, me: User, conversation_id: int) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.company_id != me.company_id:
        raise HTTPException(404, "Conversation not found")
    return conv


def _event(db: Session, conv: Conversation, text: str) -> None:
    db.add(Message(conversation_id=conv.id, sender=Sender.SYSTEM, kind=MessageKind.TEXT, content=text))


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    status: str | None = None,
    channel: str | None = None,
    mine: bool = False,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, le=500),
    me: User = Depends(can_view),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Conversation)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Conversation.company_id == me.company_id)
    )
    if status:
        stmt = stmt.where(Conversation.status == status)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if mine:
        stmt = stmt.where(Conversation.assigned_to_id == me.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    rows = db.scalars(stmt.order_by(Conversation.last_message_at.desc()).limit(limit)).all()
    return [conversation_summary(db, c) for c in rows]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int, me: User = Depends(can_view), db: Session = Depends(get_db)):
    return conversation_detail(db, _get(db, me, conversation_id))


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
def reply(conversation_id: int, body: AgentMessageIn, me: User = Depends(can_reply), db: Session = Depends(get_db)):
    """An employee writes to the customer. This pauses the AI on this conversation."""
    conv = _get(db, me, conversation_id)
    if conv.status != ConversationStatus.HUMAN:
        conv.status = ConversationStatus.HUMAN
        conv.handover_reason = conv.handover_reason or f"Taken over by {me.full_name}"
    if conv.assigned_to_id is None:
        conv.assigned_to_id = me.id
    msg = Message(conversation_id=conv.id, sender=Sender.AGENT, kind=MessageKind.TEXT,
                  content=body.content.strip(), author_user_id=me.id)
    conv.last_message_at = utcnow()
    db.add(msg)
    db.commit()
    deliver(db, conv, msg)
    db.refresh(msg)
    return message_out(msg)


@router.post("/{conversation_id}/takeover", response_model=ConversationDetail)
def take_over(conversation_id: int, me: User = Depends(can_reply), db: Session = Depends(get_db)):
    conv = _get(db, me, conversation_id)
    conv.status = ConversationStatus.HUMAN
    conv.assigned_to_id = me.id
    conv.handover_reason = conv.handover_reason or f"Taken over by {me.full_name}"
    _event(db, conv, f"{me.full_name} took over the conversation")
    db.commit()
    return conversation_detail(db, conv)


@router.post("/{conversation_id}/release", response_model=ConversationDetail)
def release_to_ai(conversation_id: int, me: User = Depends(can_reply), db: Session = Depends(get_db)):
    """Give the conversation back to the AI agent."""
    conv = _get(db, me, conversation_id)
    conv.status = ConversationStatus.AI
    conv.handover_reason = None
    conv.assigned_to_id = None
    _event(db, conv, f"{me.full_name} handed the conversation back to the AI")
    db.commit()
    return conversation_detail(db, conv)


@router.post("/{conversation_id}/close", response_model=ConversationDetail)
def close(conversation_id: int, me: User = Depends(can_reply), db: Session = Depends(get_db)):
    conv = _get(db, me, conversation_id)
    conv.status = ConversationStatus.CLOSED
    _event(db, conv, f"{me.full_name} closed the conversation")
    db.commit()
    return conversation_detail(db, conv)
