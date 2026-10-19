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
    tool_results: list[tuple[str, dict]] = []
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
                tool_results.append((tc.name, result))
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

    cards = chat_cards(tool_results, final)
    reply = Message(conversation_id=conversation.id, sender=Sender.AI, kind=MessageKind.TEXT, content=final,
                    meta={"cards": cards} if cards else None)
    db.add(reply)
    return reply


CARD_PACKAGE_FIELDS = ("id", "title", "destination", "country", "duration_days", "price_per_person", "currency",
                       "image_url")
MAX_PACKAGE_CARDS = 3


def chat_cards(tool_results: list[tuple[str, dict]], reply_text: str) -> list[dict]:
    """Rich cards shown under the AI's reply in the customer chat: the trips the reply talks about,
    the booking summary to confirm, and the booking ticket once it exists. Built only from tool
    results (data from the system), never from the model's text."""
    cards: list[dict] = []
    ticket = next((r for name, r in reversed(tool_results)
                   if name == "create_booking_ticket" and r.get("ticket_reference")), None)
    if ticket:
        cards.append({"type": "ticket", **{k: ticket.get(k) for k in (
            "ticket_reference", "package", "departure_date", "travelers", "total_price", "currency", "destination")}})
        return cards
    quote = next((r for name, r in reversed(tool_results) if name == "quote_booking" and "total_price" in r), None)
    if quote:
        cards.append({"type": "quote", **{k: quote.get(k) for k in (
            "package", "departure_date", "travelers", "total_price", "currency", "destination")}})
        return cards
    found: dict[int, dict] = {}
    for name, result in tool_results:
        if name == "search_packages":
            for p in (result.get("results") or []) + (result.get("alternatives") or []):
                found.setdefault(p["id"], p)
        elif name == "get_package_details" and "id" in result:
            found[result["id"]] = result
    text = (reply_text or "").lower()
    mentioned = [p for p in found.values() if p.get("title") and p["title"].lower() in text]
    if not mentioned and len(found) == 1:
        mentioned = list(found.values())
    for p in mentioned[:MAX_PACKAGE_CARDS]:
        cards.append({"type": "package", **{k: p.get(k) for k in CARD_PACKAGE_FIELDS}})
    return cards


SANDBOX_MAX_HISTORY = 12


def run_sandbox(db: Session, company: Company, message: str, history: list[dict] | None = None,
                llm: LLMClient | None = None, today: date | None = None) -> dict:
    """"Try your AI": the real prompt, tools and model for one test question, without a conversation.

    Nothing is added to the session: the conversation and customer only exist in memory, searching
    and quoting just read the catalog, and booking and handover are simulated (ToolContext.dry_run).
    ``history`` is the earlier turns of the test chat ([{"role": "user"|"assistant", "content"}]).
    """
    from ..models import Channel, Customer

    settings = get_settings()
    llm = llm or get_llm_client()
    conversation = Conversation(company_id=company.id, channel=Channel.WEB)  # never added to the session
    customer = Customer(company_id=company.id)
    ctx = ToolContext(db=db, company=company, conversation=conversation, customer=customer,
                      today=today or local_today(), dry_run=True, simulated=[])

    turns = [{"role": t["role"], "content": str(t.get("content") or "")[:MAX_REPLY_CHARS]}
             for t in (history or []) if t.get("role") in ("user", "assistant") and t.get("content")]
    turns = turns[-SANDBOX_MAX_HISTORY:]
    previous = next((t["content"] for t in reversed(turns) if t["role"] == "user"), "")
    training = relevant_examples(db, company.id, message, previous)
    system = build_system_prompt(company, customer, Channel.WEB, ctx.today, training, message)
    messages = [{"role": "system", "content": system}, *_repair(turns + [{"role": "user", "content": message}])]

    final: str | None = None
    error: str | None = None
    tool_results: list[tuple[str, dict]] = []
    for _ in range(settings.llm_max_tool_rounds):
        try:
            resp = llm.chat(messages, TOOL_DEFINITIONS)
        except LLMError as exc:
            log.warning("LLM failed in the test chat of company %s: %s", company.id, exc)
            error = str(exc) or "The AI is not available right now."
            break
        if resp.tool_calls:
            calls = [tc.to_openai() for tc in resp.tool_calls]
            messages.append({"role": "assistant", "content": resp.content or "", "tool_calls": calls})
            for tc in resp.tool_calls:
                result = run_tool(ctx, tc.name, tc.arguments)
                tool_results.append((tc.name, result))
                content = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
            continue
        final = (resp.content or "").strip() or None
        if final and looks_like_tool_call(final):
            final = None
        if final and len(final) > MAX_REPLY_CHARS:
            final = final[:MAX_REPLY_CHARS].rsplit("\n", 1)[0] + "…"
        break

    if not final and not error:
        final = _closing_text(ctx) if ctx.simulated else None
        if not final:
            error = "The AI could not produce an answer. In a real chat the customer would be handed to your team."

    packages: dict[int, dict] = {}
    for name, result in tool_results:
        if name == "search_packages":
            for p in (result.get("results") or []) + (result.get("alternatives") or []):
                packages.setdefault(p["id"], {k: p.get(k) for k in CARD_PACKAGE_FIELDS})
        elif name in ("get_package_details",) and "id" in result:
            packages.setdefault(result["id"], {k: result.get(k) for k in CARD_PACKAGE_FIELDS})
    return {
        "ok": error is None,
        "reply": final,
        "error": error,
        "used_answers": [{"id": t.id, "question": t.question, "answer": t.answer} for t in training],
        "packages": list(packages.values())[:6],
        "tools": [name for name, _ in tool_results],
        "simulated": list(dict.fromkeys(ctx.simulated or [])),
        "cards": chat_cards(tool_results, final or ""),
    }
