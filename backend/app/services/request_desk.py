"""What the team needs on a request beyond the quotation steps:

- the stage of the pipeline it is in (to quote, with the client, payment, booking, confirmed, closed);
- the money: client price, cost, profit and margin, what was paid and what is left;
- payments: deposits and balances, the client's transfer receipts to check (approve with the amount, or reject);
- the documents the client must send for the service (passport copies…) and which are still missing;
- the day-by-day plan of a tailor-made trip, written by staff or drafted by the AI.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..ai.llm import LLMError, MockTravelLLM, clean_content, get_llm_client
from ..branding import clean_text
from ..models import RequestFile, Ticket, TicketPayment, TicketStatus as T, User, utcnow
from ..language import Bi
from .notify import say_in_chat
from .requests import event

log = logging.getLogger(__name__)

STAGES: dict[str, tuple[str, ...]] = {
    "quote": (T.NEW, T.CHANGES, T.CHOSEN),       # the team prepares choices or the final quotation
    "client": (T.QUOTED, T.FINAL),                # the client decides
    "payment": (T.PENDING_PAYMENT, T.IN_PROGRESS),  # waiting for the money, or a receipt to check
    "booking": (T.PAID, T.WORKING),               # the team works: documents, appointment, booking
    "confirmed": (T.CONFIRMED, T.COMPLETED),      # booked and sent: the trip, then the feedback
    "closed": (T.CANCELLED, T.REJECTED),
}
STAGE_OF = {status: stage for stage, statuses in STAGES.items() for status in statuses}
PAYABLE = (T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING, T.CONFIRMED, T.COMPLETED)
METHODS = ("bank_transfer", "cash", "card", "link", "other")


def stage_of(ticket: Ticket) -> str:
    return STAGE_OF.get(ticket.status, "quote")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def money(ticket: Ticket) -> dict:
    """Price, cost, profit and payments of a request (amounts in the request's currency)."""
    total = _dec(ticket.total_price)
    chosen = [o for o in ticket.options if o.chosen]
    choices_total = sum((_dec(o.price) for o in chosen if o.price is not None), Decimal(0))
    costs = [o.cost_price for o in chosen if o.cost_price is not None]
    if ticket.cost_price is not None:
        cost, cost_from = _dec(ticket.cost_price), "manual"
    elif costs:
        cost, cost_from = sum((_dec(c) for c in costs), Decimal(0)), "choices"
    else:
        cost, cost_from = None, None
    approved = [p for p in ticket.payments if p.status == "approved" and p.amount is not None]
    paid = sum((_dec(p.amount) for p in approved), Decimal(0))
    if not approved and ticket.status in (T.PAID, T.CONFIRMED, T.COMPLETED) and ticket.payment_reference:
        paid = total  # marked paid with a reference only (before payments were recorded one by one)
    price = total if total > 0 else choices_total
    profit = price - cost if cost is not None and price > 0 else None
    f = lambda v: None if v is None else float(round(v, 3))  # noqa: E731
    return {
        "total": f(total), "choices_total": f(choices_total), "cost": f(cost), "cost_from": cost_from,
        "profit": f(profit), "margin_pct": round(float(profit / cost * 100), 1) if profit is not None and cost else None,
        "paid": f(paid), "balance": f(max(total - paid, Decimal(0))) if total > 0 else None,
        "pending_proofs": sum(1 for p in ticket.payments if p.status == "pending"),
    }


def payment_out(p: TicketPayment) -> dict:
    return {"id": p.id, "amount": float(p.amount) if p.amount is not None else None, "method": p.method,
            "reference": p.reference, "file_id": p.file_id, "status": p.status, "note": p.note,
            "created_by": p.created_by, "reviewed_by": p.reviewed_by, "reviewed_at": p.reviewed_at, "created_at": p.created_at}


# --- Payments -----------------------------------------------------------------------------------------

def _settle(db: Session, ticket: Ticket, actor: str, user: User | None) -> bool:
    """After a payment: the workflow moves on once the active payment step's amount is in. Returns True when a
    payment step finished."""
    from .. import workflow  # noqa: PLC0415
    from . import seats  # noqa: PLC0415

    done_before = {s["key"] for s in workflow.steps(ticket) if s["type"] == "payment" and s.get("state") == "done"}
    workflow.refresh(db, ticket, actor, user)
    finished = {s["key"] for s in workflow.steps(ticket) if s["type"] == "payment" and s.get("state") == "done"} - done_before
    if not finished:
        return False
    last = next((p for p in reversed(ticket.payments) if p.status == "approved" and p.reference), None)
    if last or not ticket.payment_reference:
        ticket.payment_reference = (last.reference if last else None) or ticket.payment_reference or f"PAY-{ticket.reference}"
    seats.hold_or_409(db, ticket)
    return True


def add_client_proof(db: Session, ticket: Ticket, file: RequestFile) -> TicketPayment:
    """A receipt the client sent: a payment waiting for the team to check."""
    p = TicketPayment(company_id=ticket.company_id, ticket_id=ticket.id, file_id=file.id, created_by="client")
    ticket.payments.append(p)
    db.flush()
    return p


def record(db: Session, ticket: Ticket, amount: Decimal, method: str, reference: str | None, note: str | None,
           file_id: int | None, user: User) -> bool:
    """A payment the team received (approved at once). Returns True when the request became paid."""
    from .. import workflow  # noqa: PLC0415

    if ticket.status not in PAYABLE and not (workflow.find(ticket, "payment") and ticket.status not in workflow.CLOSED
                                             and ticket.total_price):
        raise HTTPException(409, "Payments are recorded once the client approved the quotation")
    if file_id is not None and not any(f.id == file_id for f in ticket.files):
        raise HTTPException(404, "File not found")
    ticket.payments.append(TicketPayment(
        company_id=ticket.company_id, ticket_id=ticket.id, amount=amount, method=method, reference=reference,
        note=note, file_id=file_id, status="approved", created_by=user.full_name, reviewed_by=user.full_name,
        reviewed_at=utcnow()))
    db.flush()
    event(db, ticket, user.full_name, "payment_added", None, f"{amount} {ticket.currency}" + (f" · {reference}" if reference else ""), user)
    return _settle(db, ticket, user.full_name, user)


def _pending(ticket: Ticket, payment_id: int) -> TicketPayment:
    p = next((x for x in ticket.payments if x.id == payment_id), None)
    if p is None:
        raise HTTPException(404, "Payment not found")
    if p.status != "pending":
        raise HTTPException(409, "This payment was already checked")
    return p


def approve(db: Session, ticket: Ticket, payment_id: int, amount: Decimal, method: str, reference: str | None,
            user: User) -> bool:
    p = _pending(ticket, payment_id)
    p.amount, p.method, p.reference = amount, method, reference
    p.status, p.reviewed_by, p.reviewed_at = "approved", user.full_name, utcnow()
    db.flush()
    event(db, ticket, user.full_name, "payment_approved", None, f"{amount} {ticket.currency}" + (f" · {reference}" if reference else ""), user)
    return _settle(db, ticket, user.full_name, user)


def reject(db: Session, ticket: Ticket, payment_id: int, note: str, user: User) -> None:
    """The receipt can't be accepted (wrong amount, unreadable…): the client is told why."""
    p = _pending(ticket, payment_id)
    p.status, p.note, p.reviewed_by, p.reviewed_at = "rejected", note, user.full_name, utcnow()
    event(db, ticket, user.full_name, "payment_rejected", None, note, user)
    _settle(db, ticket, user.full_name, user)
    db.commit()
    say_in_chat(db, ticket.company_id, ticket.conversation_id, Bi(
        f"We could not confirm the payment receipt for *{ticket.reference}*: {note}\nPlease send a clear receipt.",
        f"لم نتمكن من تأكيد إيصال الدفع للطلب *{ticket.reference}*: {note}\nيرجى إرسال إيصال واضح."))


# --- The client's documents ---------------------------------------------------------------------------

def documents_view(ticket: Ticket) -> dict:
    """The documents this service needs from the client, what was sent for each, and papers not sorted yet."""
    reqs = (ticket.service.documents if ticket.service else None) or []
    travellers = max(1, (ticket.adults or 0) + (ticket.children or 0))
    items = []
    for d in reqs:
        files = [f for f in ticket.files if f.requirement == d.get("key")]
        need = travellers if d.get("per_traveller") else 1
        items.append({"key": d.get("key"), "label_en": d.get("label_en", ""), "label_ar": d.get("label_ar", ""),
                      "required": bool(d.get("required", True)), "need": need, "have": len(files),
                      "done": len(files) >= need, "files": [f.id for f in files]})
    unsorted = [f.id for f in ticket.files if f.kind == "client_file" and not f.requirement]
    return {"items": items, "unsorted": unsorted,
            "missing": sum(1 for i in items if i["required"] and not i["done"])}


def classify(db: Session, ticket: Ticket, file_id: int, kind: str, requirement: str | None, user: User) -> None:
    """Staff sort a file: which client document it is, a payment receipt, or a travel document of ours."""
    f = next((x for x in ticket.files if x.id == file_id), None)
    if f is None:
        raise HTTPException(404, "File not found")
    if kind == "client_file" and requirement and requirement not in {d["key"] for d in documents_view(ticket)["items"]}:
        raise HTTPException(422, "This service has no such document")
    if kind == "document" and f.uploaded_by == "client":
        raise HTTPException(422, "A file from the client can't be one of our travel documents")
    was = f.kind
    f.kind, f.requirement = kind, (requirement if kind == "client_file" else None)
    if was != "payment_proof" and kind == "payment_proof" and ticket.status in PAYABLE:
        if not any(p.file_id == f.id for p in ticket.payments):
            add_client_proof(db, ticket, f)
    if was == "payment_proof" and kind != "payment_proof":
        for p in [p for p in ticket.payments if p.file_id == f.id and p.status == "pending"]:
            ticket.payments.remove(p)
    event(db, ticket, user.full_name, "file_sorted", None, f"{f.name}: {requirement or kind}", user)
    from .. import workflow  # noqa: PLC0415

    workflow.refresh(db, ticket, user.full_name, user)


# --- Trip plan (day by day) ---------------------------------------------------------------------------

class PlanDay(BaseModel):
    day: int = Field(ge=1, le=90)
    title: str = Field(min_length=1, max_length=120)
    details: str = Field(default="", max_length=1500)

    @field_validator("title")
    @classmethod
    def line(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("details")
    @classmethod
    def text(cls, v: str) -> str:
        return clean_text(v or "", multiline=True)


def _nights(ticket: Ticket) -> int:
    try:
        d1, d2 = date.fromisoformat(ticket.departure_date or ""), date.fromisoformat(ticket.return_date or "")
        return max(1, min((d2 - d1).days, 30))
    except ValueError:
        return 4


PLAN_PROMPT = """You plan day-by-day itineraries for a travel agency in Oman and the Gulf. Write the plan of this \
trip as JSON only: [{"day": 1, "title": "short title", "details": "2-3 sentences: morning, afternoon, evening, \
using the chosen hotels and activities"}], one item per day, {days} days. Respect the client's preferences and \
Gulf travellers' habits (prayer times, halal food, family-friendly). Write in English."""


def draft_plan(ticket: Ticket) -> list[dict]:
    days = _nights(ticket) + 1
    chosen = [f"{o.category}: {o.title}" for o in ticket.options if o.chosen or o.sent_to_client][:12]
    case = {"destination": ticket.destination, "from": ticket.origin, "depart": ticket.departure_date,
            "return": ticket.return_date, "adults": ticket.adults, "children": ticket.children,
            "answers": ticket.answers, "chosen": chosen}
    llm = get_llm_client()
    raw: list = []
    if not isinstance(llm, MockTravelLLM):
        try:
            resp = llm.chat([{"role": "system", "content": PLAN_PROMPT.replace("{days}", str(days))},
                             {"role": "user", "content": json.dumps(case, ensure_ascii=False, default=str)[:6000]}], [])
            match = re.search(r"\[.*\]", clean_content(resp.content or ""), re.DOTALL)
            raw = json.loads(match.group(0)) if match else []
        except (LLMError, json.JSONDecodeError, ValueError) as exc:
            log.info("Trip plan draft fell back: %s", exc)
            raw = []
    plan = []
    for i, item in enumerate(raw if isinstance(raw, list) else []):
        try:
            plan.append(PlanDay.model_validate({"day": item.get("day", i + 1), "title": str(item.get("title", ""))[:120] or f"Day {i + 1}",
                                                "details": str(item.get("details", ""))[:1500]}).model_dump())
        except (ValueError, AttributeError):
            continue
    if plan:
        return plan[:60]
    place = ticket.destination or "the destination"
    hotel = next((o.title for o in ticket.options if o.category == "hotel" and (o.chosen or o.sent_to_client)), None)
    out = [{"day": 1, "title": f"Arrival in {place}", "details": f"Meet and greet, transfer to {hotel or 'the hotel'}, check-in and a relaxed evening."}]
    for d in range(2, days):
        out.append({"day": d, "title": f"Discover {place}", "details": "Morning visit, lunch, free afternoon; evening activity."})
    if days > 1:
        out.append({"day": days, "title": "Departure", "details": "Breakfast, check-out and transfer to the airport."})
    return out


def apply_dates_hint(start: str | None, plan: list[dict]) -> list[dict]:
    """Adds the calendar date of each day when the departure date is known (for the quotation and client page)."""
    try:
        d0 = date.fromisoformat(start or "")
    except ValueError:
        return plan
    return [{**p, "date": (d0 + timedelta(days=int(p["day"]) - 1)).isoformat()} for p in plan]
