"""The agent loop: model -> tools -> model ... -> reply to the customer."""

from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Company, Conversation, Message, MessageKind, Sender
from ..timeutil import local_today
from .llm import LLMClient, LLMError, get_llm_client, looks_like_tool_call
from .prompts import FALLBACK_REPLY, build_system_prompt
from .tools import TOOL_DEFINITIONS, ToolContext, run_tool
from .training import relevant_examples

log = logging.getLogger(__name__)


OLD_TOOL_RESULT_CHARS = 600
MAX_REPLY_CHARS = 4000


def build_history(db: Session, conversation: Conversation, max_messages: int) -> list[dict]:
    """Rebuild the chat in OpenAI format from stored messages.

    ``max_messages`` counts the conversation's text messages (customer and agency), so tool calls
    don't push the customer's earlier details out of the window; tool results of earlier turns
    are shortened to keep the prompt small.
    """
    text_ids = db.scalars(
        select(Message.id)
        .where(Message.conversation_id == conversation.id, Message.sender != Sender.SYSTEM,
               Message.kind == MessageKind.TEXT)
        .order_by(Message.id.desc())
        .limit(max_messages)
    ).all()
    if not text_ids:
        return []
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.sender != Sender.SYSTEM,
               Message.id >= min(text_ids))
        .order_by(Message.id)
    ).all()
    last_customer = max((m.id for m in rows if m.sender == Sender.CUSTOMER), default=0)

    history: list[dict] = []
    for m in rows:
        if m.kind == MessageKind.TOOL_CALL:
            history.append({"role": "assistant", "content": m.content or "", "tool_calls": (m.meta or {}).get("tool_calls", [])})
        elif m.kind == MessageKind.TOOL_RESULT:
            content = m.content or ""
            if m.id < last_customer and len(content) > OLD_TOOL_RESULT_CHARS:
                content = content[:OLD_TOOL_RESULT_CHARS] + "…(shortened)"
            history.append({"role": "tool", "tool_call_id": (m.meta or {}).get("tool_call_id", ""), "content": content})
        elif m.sender == Sender.CUSTOMER:
            history.append({"role": "user", "content": m.content})
        else:  # AI or employee replies are both "the agency speaking"
            history.append({"role": "assistant", "content": m.content})
    return _repair(history)


def _repair(history: list[dict]) -> list[dict]:
    """Make sure the history is valid for chat APIs: it starts with the customer, and every
    assistant tool call is followed by exactly its tool results."""
    while history and history[0]["role"] != "user":
        history.pop(0)
    out: list[dict] = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            ids = {tc.get("id") for tc in msg["tool_calls"]}
            j = i + 1
            results = []
            while j < len(history) and history[j]["role"] == "tool":
                results.append(history[j])
                j += 1
            if ids and ids == {r["tool_call_id"] for r in results}:
                out.append(msg)
                out.extend(results)
            i = j
            continue
        if msg["role"] == "tool":  # orphan result
            i += 1
            continue
        out.append(msg)
        i += 1
    return out


def _closing_text(ctx: ToolContext) -> str:
    if ctx.ticket_reference:
        return (
            f"Your booking request is registered with reference {ctx.ticket_reference}. "
            f"A {ctx.company.name} consultant will contact you shortly to complete the payment.\n"
            f"تم تسجيل طلب الحجز برقم {ctx.ticket_reference}. "
            f"سيتواصل معك أحد مستشاري {ctx.company.name} قريباً لإتمام الدفع."
        )
    return (
        "Thank you! One of our travel consultants will reply to you here shortly.\n"
        "شكراً لك! سيرد عليك أحد مستشاري السفر هنا قريباً."
    )


def _latest_customer_texts(db: Session, conversation: Conversation) -> tuple[str, str]:
    """The customer's last message and the one before it."""
    texts = db.scalars(
        select(Message.content)
        .where(Message.conversation_id == conversation.id, Message.sender == Sender.CUSTOMER)
        .order_by(Message.id.desc())
        .limit(2)
    ).all()
    return (texts[0] if texts else "") or "", (texts[1] if len(texts) > 1 else "") or ""


def run_agent(db: Session, conversation: Conversation, llm: LLMClient | None = None,
              today: date | None = None) -> Message:
    """Generate the AI reply to the latest customer message.

    New messages (tool calls, tool results, the reply) are added to the session; the
    caller commits. Model failures never raise: the customer always gets an answer
    and the conversation is handed to a human when the AI cannot continue.
    """
    settings = get_settings()
    llm = llm or get_llm_client()
    company = db.get(Company, conversation.company_id)
    ctx = ToolContext(db=db, company=company, conversation=conversation, customer=conversation.customer,
                      today=today or local_today())

    customer_text, previous_text = _latest_customer_texts(db, conversation)
    training = relevant_examples(db, company.id, customer_text, previous_text)
    system = build_system_prompt(company, ctx.customer, conversation.channel, ctx.today, training, customer_text)
    messages = [{"role": "system", "content": system}]
    messages += build_history(db, conversation, settings.llm_max_history_messages)

    final: str | None = None
    for _ in range(settings.llm_max_tool_rounds):
        try:
            resp = llm.chat(messages, TOOL_DEFINITIONS)
        except LLMError as exc:
            log.warning("LLM failed for conversation %s: %s", conversation.id, exc)
            if not ctx.handed_over:
                run_tool(ctx, "request_human_agent", {"reason": "AI unavailable, please answer the customer"})
                final = FALLBACK_REPLY
            break

        if resp.tool_calls:
            calls = [tc.to_openai() for tc in resp.tool_calls]
            db.add(Message(conversation_id=conversation.id, sender=Sender.AI, kind=MessageKind.TOOL_CALL,
                           content=resp.content or "", meta={"tool_calls": calls}))
            messages.append({"role": "assistant", "content": resp.content or "", "tool_calls": calls})
            for tc in resp.tool_calls:
                result = run_tool(ctx, tc.name, tc.arguments)
                content = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
                db.add(Message(conversation_id=conversation.id, sender=Sender.AI, kind=MessageKind.TOOL_RESULT,
                               content=content, meta={"tool_call_id": tc.id, "name": tc.name}))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            continue

        final = (resp.content or "").strip() or None
        if final and looks_like_tool_call(final):
            log.warning("Model wrote a tool call as text in conversation %s; not sent", conversation.id)
            final = None
        if final and len(final) > MAX_REPLY_CHARS:
            final = final[:MAX_REPLY_CHARS].rsplit("\n", 1)[0] + "…"
        break

    if not final:
        if not ctx.handed_over:
            run_tool(ctx, "request_human_agent", {"reason": "AI could not produce an answer"})
        final = _closing_text(ctx)

    reply = Message(conversation_id=conversation.id, sender=Sender.AI, kind=MessageKind.TEXT, content=final)
    db.add(reply)
    return reply
