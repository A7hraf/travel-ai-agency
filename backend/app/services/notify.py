"""Posting an update into a client's own chat (WhatsApp, Instagram or the website), as the AI consultant."""

import logging

from sqlalchemy.orm import Session

from ..models import Conversation, Message, MessageKind, Sender

log = logging.getLogger(__name__)


def say_in_chat(db: Session, company_id: int, conversation_id: int | None, text: str) -> bool:
    """Sends `text` in that chat. Never fails the step that called it (the update stays in the history)."""
    if conversation_id is None:
        return False
    try:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.company_id != company_id:
            return False
        message = Message(conversation_id=conv.id, sender=Sender.AI, kind=MessageKind.TEXT, content=text)
        db.add(message)
        db.commit()
        from .conversations import deliver  # noqa: PLC0415 (conversations imports the AI, which imports us)

        deliver(db, conv, message)
        return True
    except Exception:  # noqa: BLE001
        log.exception("Could not post an update in conversation %s", conversation_id)
        db.rollback()
        return False
