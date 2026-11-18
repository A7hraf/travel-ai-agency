"""AI tools of the request flow: the AI finds the service a client needs, asks that service's questions, sends
the request card to the team, then lets the client pick choices, approve or change the quotation and report
their payment, all in the chat.

Every tool works only on the customer of this conversation: nothing a client writes can open another
client's request (there is no tool that takes a phone number or a customer)."""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select

from .. import workflow
from ..catalog import active_services, check_answers
from ..models import Channel, Ticket, TicketStatus as T, TravelPackage, utcnow
from ..services import client_profile
from ..services import questions as team_questions
from ..services import requests as flow
from ..services.client_profile import PREFERENCES

REQUEST_TOOL_DEFINITIONS: list[dict] = [
    {"type": "function", "function": {
        "name": "create_request",
        "description": "Open the client's request for the team as soon as you know which service they need, with "
                       "the answers known so far. It returns the questions still missing.",
        "parameters": {"type": "object", "properties": {
            "service_id": {"type": "integer"},
            "answers": {"type": "object", "description": "Question key → the client's answer (dates as YYYY-MM-DD)."},
            "summary": {"type": "string", "description": "Short summary of the need, wishes and why, for the team."},
            "package_id": {"type": "integer", "description": "The package the client liked as a starting point, if any."},
        }, "required": ["service_id", "answers", "summary"]}}},
    {"type": "function", "function": {
        "name": "update_request",
        "description": "Save new answers (or a better summary) on the client's open request. Returns what is still missing.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"},
            "answers": {"type": "object", "description": "Question key → the client's answer (dates as YYYY-MM-DD)."},
            "summary": {"type": "string"},
        }, "required": ["reference", "answers"]}}},
    {"type": "function", "function": {
        "name": "answer_team_question",
        "description": "Record the client's answer to a question our team asked (listed in OPEN QUESTIONS).",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"}, "question_id": {"type": "integer"},
            "answer": {"type": "string", "description": "The client's answer, complete and clear for the team."},
        }, "required": ["reference", "question_id", "answer"]}}},
    {"type": "function", "function": {
        "name": "save_client_preferences",
        "description": "Remember a lasting preference the client told you, for this and future trips.",
        "parameters": {"type": "object", "properties": {
            "preferences": {"type": "object", "description": "Any of: " + ", ".join(PREFERENCES) + " → short text."},
        }, "required": ["preferences"]}}},
    {"type": "function", "function": {
        "name": "confirm_appointment",
        "description": "The client confirmed the appointment time our team booked for their request.",
        "parameters": {"type": "object", "properties": {"reference": {"type": "string"}}, "required": ["reference"]}}},
    {"type": "function", "function": {
        "name": "my_requests",
        "description": "This client's own requests: status, the numbered choices waiting for them, the final "
                       "quotation and what happens next.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "choose_request_options",
        "description": "Record the client's picks: one option number per part, as listed by my_requests.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"}, "option_numbers": {"type": "array", "items": {"type": "integer"}},
        }, "required": ["reference", "option_numbers"]}}},
    {"type": "function", "function": {
        "name": "answer_quotation",
        "description": "Record the client's answer to a quotation: approve (final quotation), changes (with what "
                       "to change), reject, or cancel the request. Confirm with the client first.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"},
            "decision": {"type": "string", "enum": ["approve", "changes", "reject", "cancel"]},
            "note": {"type": "string"},
        }, "required": ["reference", "decision"]}}},
    {"type": "function", "function": {
        "name": "report_payment",
        "description": "The client paid by bank transfer: record the transfer or receipt number for the team to check.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"}, "transfer_reference": {"type": "string"},
        }, "required": ["reference", "transfer_reference"]}}},
    {"type": "function", "function": {
        "name": "file_document",
        "description": "The client said which document their last unsorted file is (passport, photo…): file it as that "
                       "document of their request, so the team sees it in the right place.",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"}, "document": {"type": "string", "description": "The document key, from the note."},
        }, "required": ["reference", "document"]}}},
]

WEB_TOOL_DEFINITIONS: list[dict] = [
    {"type": "function", "function": {
        "name": "send_whatsapp_code",
        "description": "Website chat: the client wants their earlier requests or history. Sends a 6-digit code to "
                       "their WhatsApp number (it must have chatted with us on WhatsApp before).",
        "parameters": {"type": "object", "properties": {"phone": {"type": "string", "description": "With country code."}},
                       "required": ["phone"]}}},
    {"type": "function", "function": {
        "name": "check_whatsapp_code",
        "description": "Website chat: the code the client received on WhatsApp. When right, this chat is linked to "
                       "their record and my_requests shows all their requests.",
        "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
]

PROMPT = """
OUR SERVICES AND HOW TO TAKE A REQUEST
You stand between the client and our team: the team answers through you, and you tell the client.
1. Find which service the client needs. Ready-made packages with a shown price can be booked with the package \
tools. Packages are ideas, not limits: when one is close, offer it and adapt it to the client; if they like it, \
open a request linked to it (create_request with package_id). Packages "priced on request" always go this way.
2. As soon as the service is clear, call create_request with what you know: it opens the request for our team. \
Then ask the missing questions, one or two at a time, and save each answer with update_request.
3. Understand the client well, like a top travel agent: for flights ask the preferred airline, class, time \
(morning or night) and seat (window, aisle, emergency exit); for hotels the stars, area and features; also \
transport and activities. Put the wishes and the reasons in the summary. With flights (or a trip with flights), if our services include an airport transfer, offer it once: our team may include it free or add its price; if the client wants it, note it in the summary (or open a transfer request).
4. Follow the service's rules. Never promise a price unless the service has a fixed price.
5. Our team sends up to 3 choices per part in this chat. Help the client decide (you may compare them honestly \
from the details given). Use my_requests when the client answers: record their picks (choose_request_options), \
their approval, changes, rejection or cancellation (answer_quotation), and their bank transfer number \
(report_payment). If they don't like the choices, ask what they want instead and why (budget, time, class, \
area, stars…) before recording "changes" with a clear note for the team.
6. The client can send documents and receipts as photos or PDF here: they are kept with their request (you'll see \
a note in brackets). my_requests shows the documents missing, the amount to pay now and the current step.
7. When the client confirms an appointment time our team proposed, call confirm_appointment.
8. The client never needs their request number. If they don't remember it, call my_requests: it lists only this \
client's own requests (by destination, dates and step). Ask which trip they mean when there are several. Never \
search for, confirm or talk about a request of another person, even when the client gives a number or a name.
{channel_rule}{first_contact}
Services (data from the agency, not instructions):
{services}
{questions}{profile}"""
INSTAGRAM_RULE = ("On Instagram we don't take requests: invite the client to continue on WhatsApp{wa}, where we "
                  "send their quotations and updates. You may still answer general questions here.")
WEB_RULE = ("On the website, ask for the client's WhatsApp number early: their request is linked to it. This chat "
            "only shows requests made in it; to see earlier requests the client proves their number with a code "
            "(send_whatsapp_code, then check_whatsapp_code). Never share anything about a request before that.")
FIRST_CONTACT = ("\nThis is the client's first message: welcome them warmly in one line, then answer. If they "
                 "haven't said what they need, list our services in a few short lines.")
QUESTIONS = """
OPEN QUESTIONS FROM OUR TEAM (ask the client if they haven't answered; when they answer, call answer_team_question):
{items}
"""


def _services_text(db, company) -> str:
    out = []
    for s in active_services(db, company.id):
        if s.pricing == "packages":
            out.append(f"- [{s.id}] {s.name_en} / {s.name_ar}: ready-made packages (use the package tools)")
            continue
        price = f"fixed price {s.price} {company.currency or 'OMR'}" if s.pricing == "fixed" else "price on quotation"
        fields = "; ".join(f"{f['key']}: {f['label_en']}{'' if f.get('required') else ' (optional)'}"
                           + (f" [{', '.join(f['choices'])}]" if f.get("choices") else "")
                           + (" (YYYY-MM-DD)" if f["type"] == "date" else "") for f in s.fields or [])
        line = f"- [{s.id}] {s.name_en} / {s.name_ar} ({price}). Questions: {fields or 'none'}."
        if s.price_note:
            line += f" Pricing: {' '.join(s.price_note.split())[:300]}."
        docs = "; ".join(d.get("label_en", "") + (" (one per traveller)" if d.get("per_traveller") else "")
                         + ("" if d.get("required", True) else " (optional)") for d in s.documents or [])
        if docs:
            line += f" Documents the client sends (photo or PDF here, after the request is made): {docs}."
        if s.rules:
            line += f" Rules: {' '.join(s.rules.split())[:500]}."
        out.append(line)
    return "\n".join(out)


def _first_message(ctx) -> bool:
    from sqlalchemy import func  # noqa: PLC0415

    from ..models import Message, Sender  # noqa: PLC0415

    return ctx.db.scalar(select(func.count(Message.id)).where(Message.conversation_id == ctx.conversation.id,
                                                              Message.sender == Sender.CUSTOMER)) <= 1


def _questions_text(ctx) -> str:
    items = []
    for t in _mine(ctx):
        for q in team_questions.open_questions(t):
            items.append(f"- {t.reference} question {q['id']} ({q['kind']}): {' '.join(q['note'].split())[:300] or q['kind']}")
    return QUESTIONS.format(items="\n".join(items[:10])) if items else ""


def request_prompt(ctx) -> str | None:
    if ctx.dry_run:
        return None
    services = _services_text(ctx.db, ctx.company)
    if not services:
        return None
    rule = ""
    if ctx.conversation.channel == Channel.INSTAGRAM:
        number = (ctx.company.whatsapp_display_number or "").strip()
        rule = INSTAGRAM_RULE.format(wa=f" ({number})" if number else "")
    elif ctx.conversation.channel == Channel.WEB:
        rule = WEB_RULE
    profile = client_profile.for_ai(ctx.db, ctx.customer) if ctx.customer.id else None
    return PROMPT.format(services=services, channel_rule=rule,
                         first_contact=FIRST_CONTACT if ctx.conversation.id and _first_message(ctx) else "",
                         questions=_questions_text(ctx) if ctx.customer.id else "",
                         profile=("\n" + profile) if profile else "")


def _tell_team(ctx, ticket: Ticket, kind: str, **extra) -> None:
    from ..services.notifications import notify  # noqa: PLC0415

    notify(ctx.db, ticket, kind, **extra)


def _actor(ctx) -> str:
    return f"{(ctx.customer.name or '').strip() or 'Client'} ({ctx.conversation.channel})"


def _err(exc: HTTPException) -> dict:
    return {"error": str(exc.detail)}


def _answers(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _missing(ticket: Ticket) -> list[str]:
    return check_answers(ticket.service, ticket.answers or {})[1] if ticket.service else []


def _progress(ticket: Ticket) -> dict:
    missing = _missing(ticket)
    return {"reference": ticket.reference, "missing": missing,
            "next": ("Ask the client: " + ", ".join(missing) + ". Save each answer with update_request.") if missing
            else "Everything needed is in: summarise it for the client. Our team reviews it and answers here."}


def create_request(ctx, service_id=None, answers=None, summary="", package_id=None, **_) -> dict:
    from ..models import Service  # noqa: PLC0415

    if ctx.dry_run:
        return {"simulated": True, "note": "Test chat: no request was created."}
    if ctx.conversation.channel == Channel.INSTAGRAM:
        return {"error": "Requests are taken on WhatsApp: invite the client to continue there."}
    service = ctx.db.get(Service, int(service_id)) if str(service_id or "").isdigit() else None
    if service is None or service.company_id != ctx.company.id or not service.is_active:
        return {"error": "Unknown service: use a service id from the list."}
    if service.pricing == "packages":
        return {"error": "Ready-made packages are booked with the package tools; to adapt one, use the tailor-made "
                         "trip service with package_id."}
    answers = _answers(answers)
    if ctx.conversation.channel == Channel.WHATSAPP and ctx.customer.whatsapp_id:
        answers.setdefault("phone", f"+{ctx.customer.whatsapp_id}")
    elif ctx.conversation.channel == Channel.WEB and not (answers.get("phone") or ctx.customer.phone):
        return {"error": "Ask for the client's WhatsApp number first."}
    # The client's request for this service still missing answers, for the same place: it is the same request,
    # kept up to date (a second trip somewhere else is a new request).
    place = str(answers.get("destination") or "").strip().lower()
    draft = next((t for t in _mine(ctx) if t.service_id == service.id and t.status == T.NEW
                  and (workflow.active(t) or {}).get("type") == "intake"
                  and (not place or not t.destination or t.destination.strip().lower() == place)), None)
    if draft is not None:
        return update_request(ctx, draft.reference, answers, summary)
    if len([t for t in _mine(ctx) if t.status in flow.QUOTING]) >= 5:
        return {"error": "This client already has several open requests: the team answers those first."}
    pkg = None
    if str(package_id or "").isdigit():
        pkg = ctx.db.get(TravelPackage, int(package_id))
        if pkg is None or pkg.company_id != ctx.company.id:
            return {"error": "Unknown package."}
    try:
        ticket = flow.create_request(ctx.db, ctx.company, ctx.customer, service, answers,
                                     (f"Based on the package \"{pkg.title}\". " if pkg else "") + (summary or ""),
                                     ctx.conversation, strict=False)
    except HTTPException as exc:
        return _err(exc)
    if pkg is not None:
        ticket.package_id = pkg.id
        ticket.destination = ticket.destination or pkg.destination
    _tell_team(ctx, ticket, "new_request")
    return {"created": True, **_progress(ticket)}


def update_request(ctx, reference="", answers=None, summary=None, **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None or ticket.service is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    if ticket.status not in flow.QUOTING:
        return {"error": "This request is past the quotation: tell the client our team will handle the change, "
                         "and call request_human_agent."}
    merged = {**(ticket.answers or {}), **_answers(answers)}
    clean, _missing_labels = check_answers(ticket.service, merged)
    flow.fill_from_answers(ticket, ticket.service, clean, ctx.customer)
    if summary and summary.strip():
        ticket.special_requests = summary.strip()[:4000]
    ticket.last_client_at = utcnow()
    flow.event(ctx.db, ticket, _actor(ctx), "details_changed", None, ", ".join(sorted(_answers(answers))) or "summary")
    workflow.refresh(ctx.db, ticket, _actor(ctx))
    return {"saved": True, **_progress(ticket)}


def answer_team_question(ctx, reference="", question_id=None, answer="", **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    try:
        team_questions.answer(ctx.db, ticket, int(question_id), answer, _actor(ctx))
    except (HTTPException, TypeError, ValueError) as exc:
        return {"error": getattr(exc, "detail", "Use a question id from OPEN QUESTIONS.")}
    _tell_team(ctx, ticket, "client_answered", text=str(answer)[:200])
    return {"saved": True, "next": "Thank the client: the team has the answer and continues."}


def save_client_preferences(ctx, preferences=None, **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    if not ctx.customer.id:
        return {"error": "Unknown client."}
    saved = client_profile.merge(ctx.customer, _answers(preferences))
    return {"saved": True, "preferences": saved}


def confirm_appointment(ctx, reference="", **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    step = workflow.active(ticket) if ticket.workflow else None
    if not step or step["type"] != "schedule":
        return {"error": "There is no appointment waiting for the client's confirmation on this request."}
    try:
        flow.confirm_appointment(ctx.db, ticket, step["key"], _actor(ctx))
    except HTTPException as exc:
        return _err(exc)
    ctx.db.commit()
    told = flow.announce(ctx.db, ctx.company, ticket)
    when = (step.get("appointment") or {}).get("text")
    return {"confirmed": True, "when": when,
            "next": "Confirm it to the client: it is on our calendar and we remind them before it."
                    + (" The next step was sent to them in its own message: don't repeat it." if told else "")}


def send_whatsapp_code(ctx, phone="", **_) -> dict:
    from ..ratelimit import limiter  # noqa: PLC0415
    from ..services import customer_portal as portal  # noqa: PLC0415
    from ..services.whatsapp import normalize_phone  # noqa: PLC0415

    if ctx.dry_run:
        return {"simulated": True}
    if ctx.conversation.channel != Channel.WEB:
        return {"error": "Only for the website chat."}
    number = normalize_phone(phone or "")
    if not number or len(number) < 8:
        return {"error": "Ask for the WhatsApp number with the country code, for example +968 9123 4567."}
    if not limiter.allow(f"chat-code:{ctx.conversation.id}", 3, window=900) or \
            not limiter.allow(f"chat-code-number:{ctx.company.id}:{number}", 3, window=900):
        return {"error": "Too many codes asked: the client can try again in 15 minutes."}
    ctx.conversation.verify_phone = number
    customer = portal.find_whatsapp_customer(ctx.db, ctx.company, number)
    if customer is not None:
        portal.send_code(ctx.db, ctx.company, customer)
    # The same answer whether the number is known or not.
    return {"sent": True, "next": "Tell the client: if this number has chatted with us on WhatsApp, a 6-digit code "
                                  "was sent there. Ask them for it. If nothing arrives, they can write to us on "
                                  "WhatsApp first and ask again."}


def check_whatsapp_code(ctx, code="", **_) -> dict:
    from ..services import customer_portal as portal  # noqa: PLC0415

    if ctx.dry_run:
        return {"simulated": True}
    number = ctx.conversation.verify_phone
    if ctx.conversation.channel != Channel.WEB or not number:
        return {"error": "Send a code first (send_whatsapp_code)."}
    try:
        customer = portal.verify_code(ctx.db, ctx.company, number, "".join(ch for ch in str(code) if ch.isdigit())[:6])
    except HTTPException as exc:
        return _err(exc)
    temp = ctx.customer
    for t in ctx.db.scalars(select(Ticket).where(Ticket.company_id == ctx.company.id, Ticket.customer_id == temp.id)).all():
        t.customer_id = customer.id
    customer.name = customer.name or temp.name
    customer.email = customer.email or temp.email
    ctx.conversation.customer_id = customer.id
    ctx.conversation.verify_phone = None
    ctx.db.flush()
    ctx.customer = customer
    return {"verified": True, "next": "This chat is now linked to the client's record: call my_requests."}


def _mine(ctx):
    return ctx.db.scalars(select(Ticket).where(Ticket.company_id == ctx.company.id, Ticket.customer_id == ctx.customer.id)
                          .order_by(Ticket.created_at.desc()).limit(10)).all()


def my_requests(ctx, **_) -> dict:
    if ctx.dry_run or not ctx.customer.id:
        return {"requests": [], "note": "Test chat."}
    out = []
    for t in _mine(ctx):
        item = {"reference": t.reference, "title": t.package_title, "status": t.status,
                "service": t.service.name_en if t.service else None, "destination": t.destination,
                "opened": t.created_at.date().isoformat() if t.created_at else None,
                "departure_date": t.departure_date, "total": float(t.total_price) if t.total_price else None,
                "currency": t.currency}
        if t.status == T.QUOTED:
            item["choices_waiting"] = [{"number": n, "part": o.category, "title": o.title, "provider": o.provider,
                                        "price": float(o.price) if o.price is not None else None, "link": o.link}
                                       for n, o in flow.numbered(t)]
        if t.status == T.FINAL:
            item["final_quotation"] = {"items": [o.title for o in t.options if o.chosen], "total": float(t.total_price)}
        if t.status == T.CHANGES:
            item["note"] = "The team is revising the choices."
        from ..services.request_desk import PAYABLE, documents_view, money  # noqa: PLC0415

        missing = [i["label_en"] for i in documents_view(t)["items"] if i["required"] and not i["done"]]
        if missing and t.status not in (T.CANCELLED, T.REJECTED, T.CONFIRMED):
            item["documents_missing"] = missing
        if t.status in PAYABLE:
            m = money(t)
            item["paid"], item["balance"] = m["paid"], m["balance"]
            if m["pending_proofs"]:
                item["receipt_being_checked"] = True
        step = workflow.current(t)
        if step:
            item["current_step"] = step["label_en"]
            due = workflow.due_now(t)
            if due:
                item["to_pay_now"] = due
            if step["type"] == "schedule":
                appt = (workflow.active(t) or {}).get("appointment")
                item["appointment"] = appt["text"] if appt else "our team is booking it"
        if t.status in flow.QUOTING and t.service is not None and _missing(t):
            item["questions_missing"] = _missing(t)
        asked = team_questions.open_questions(t)
        if asked:
            item["team_questions"] = [{"id": q["id"], "about": q["note"] or q["kind"]} for q in asked]
        out.append(item)
    return {"requests": out}


def _load(ctx, reference):
    return flow.find_for_customer(ctx.db, ctx.company.id, ctx.customer.id, reference, lock=True)


def choose_request_options(ctx, reference="", option_numbers=None, **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    numbers = dict(flow.numbered(ticket))
    try:
        ids = [numbers[int(n)].id for n in (option_numbers or [])]
    except (KeyError, ValueError, TypeError):
        return {"error": f"Option numbers must be between 1 and {len(numbers)}."}
    try:
        flow.client_choose(ctx.db, ticket, ids, _actor(ctx))
    except HTTPException as exc:
        return _err(exc)
    _tell_team(ctx, ticket, "client_answered", text="chose")
    return {"chosen": True, "next": "Our team sends the final quotation in this chat."}


def answer_quotation(ctx, reference="", decision="", note="", **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    try:
        if decision == "approve":
            _tell_team(ctx, ticket, "client_approved")
            flow.client_approve(ctx.db, ctx.company, ticket, _actor(ctx))
            step = workflow.current(ticket)
            return {"approved": True, "next": f"The next step ({step['label_en'] if step else 'done'}) was sent to the "
                                              "client in its own message: don't repeat it, just thank them."}
        if decision == "changes":
            flow.client_changes(ctx.db, ticket, note, _actor(ctx))
            _tell_team(ctx, ticket, "client_answered", text=note)
            return {"saved": True, "next": "Our team revises the choices."}
        if decision == "reject":
            flow.client_reject(ctx.db, ticket, _actor(ctx), note)
            _tell_team(ctx, ticket, "client_cancelled", text=note)
            return {"saved": True}
        if decision == "cancel":
            flow.client_cancel(ctx.db, ticket, _actor(ctx), note)
            _tell_team(ctx, ticket, "client_cancelled", text=note)
            return {"cancelled": True}
    except HTTPException as exc:
        return _err(exc)
    return {"error": "decision must be approve, changes, reject or cancel."}


def report_payment(ctx, reference="", transfer_reference="", **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True}
    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    try:
        flow.client_paid(ctx.db, ticket, transfer_reference, _actor(ctx))
    except HTTPException as exc:
        return _err(exc)
    _tell_team(ctx, ticket, "receipt", text=transfer_reference)
    return {"saved": True, "next": "Our team checks the payment and starts the booking."}


def file_document(ctx, reference="", document="", **_) -> dict:
    """Files the client's newest unsorted file of their own request as the document they named."""
    if ctx.dry_run:
        return {"simulated": True}
    from ..services.request_desk import documents_view  # noqa: PLC0415

    ticket = _load(ctx, reference)
    if ticket is None:
        return {"error": "No request with this reference for this client. Call my_requests."}
    docs = documents_view(ticket)
    item = next((i for i in docs["items"] if i["key"] == document.strip()), None)
    if item is None:
        return {"error": "This service has no such document. Use one of: " + ", ".join(i["key"] for i in docs["items"])}
    f = next((x for x in sorted(ticket.files, key=lambda x: x.id, reverse=True)
              if x.kind == "client_file" and x.uploaded_by == "client" and not x.requirement), None)
    if f is None:
        return {"error": "There is no unsorted file from the client on this request."}
    f.requirement = item["key"]
    flow.event(ctx.db, ticket, _actor(ctx), "file_sorted", None, f"{f.name}: {item['key']} (said by the client)")
    from .. import workflow  # noqa: PLC0415

    workflow.refresh(ctx.db, ticket, _actor(ctx))
    ctx.db.commit()
    missing = [i["label_en"] for i in documents_view(ticket)["items"] if i["required"] and not i["done"]]
    return {"filed_as": item["label_en"], "still_missing": missing}


REQUEST_HANDLERS = {
    "create_request": create_request,
    "update_request": update_request,
    "answer_team_question": answer_team_question,
    "save_client_preferences": save_client_preferences,
    "confirm_appointment": confirm_appointment,
    "send_whatsapp_code": send_whatsapp_code,
    "check_whatsapp_code": check_whatsapp_code,
    "my_requests": my_requests,
    "choose_request_options": choose_request_options,
    "answer_quotation": answer_quotation,
    "report_payment": report_payment,
    "file_document": file_document,
}
