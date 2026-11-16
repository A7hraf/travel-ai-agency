"""Request workflows: the ordered steps a request goes through.

Each service has a default workflow (built-in, or set by the owner); each request keeps its own copy, which the
team can change for that request (only the steps not started yet). The request's status follows its active step.
A step whose work is already done when it starts (answers complete, documents in, amount paid…) is passed.

Step types: intake (the request's details), review (the team checks it), quote (choices and final quotation),
documents (the client's papers), payment (one installment: a percent, a fixed amount or the rest), schedule (an
appointment agreed with the client), booking (the booking checklist), delivery (the travel documents), trip,
feedback, task (any other step, done by the team).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .branding import clean_text
from .models import Ticket, TicketStatus as T, TripFeedback, User, utcnow
from .timeutil import local_today

StepType = Literal["intake", "review", "quote", "documents", "payment", "schedule", "booking", "delivery", "trip",
                   "feedback", "task"]
TYPES: dict[str, tuple[str, str]] = {
    "intake": ("Request details", "تفاصيل الطلب"),
    "review": ("Team review", "مراجعة الفريق"),
    "quote": ("Quotation", "عرض السعر"),
    "documents": ("Client documents", "مستندات العميل"),
    "payment": ("Payment", "الدفع"),
    "schedule": ("Appointment", "الموعد"),
    "booking": ("Booking", "الحجز"),
    "delivery": ("Travel documents", "وثائق السفر"),
    "trip": ("Trip", "الرحلة"),
    "feedback": ("Feedback", "التقييم"),
    "task": ("Task", "مهمة"),
}
ONCE = {"intake", "review", "quote", "documents", "booking", "delivery", "trip", "feedback"}
TEAM_DONE = {"intake", "review", "documents", "schedule", "booking", "delivery", "trip", "feedback", "task"}
ADMIN_DONE = {"payment"}  # passing a payment that was not made (a waiver, paid outside the system)
TEAM_WORK = {"documents", "schedule", "booking", "delivery", "task"}
KEY = r"^[a-z][a-z0-9_]{1,39}$"
MAX_STEPS = 25
QUOTING = (T.NEW, T.QUOTED, T.CHANGES, T.CHOSEN, T.FINAL)
CLOSED = (T.CANCELLED, T.REJECTED)


class StepIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(pattern=KEY)
    type: StepType
    label_en: str = Field(default="", max_length=80)
    label_ar: str = Field(default="", max_length=80)
    pay_mode: Literal["percent", "fixed", "rest"] | None = None
    pay_value: Decimal | None = Field(default=None, ge=0, le=Decimal("100000000"), decimal_places=3)

    @field_validator("label_en", "label_ar")
    @classmethod
    def line(cls, v: str) -> str:
        return clean_text(v or "", multiline=False)

    @model_validator(mode="after")
    def defaults(self) -> StepIn:
        en, ar = TYPES[self.type]
        self.label_en = self.label_en or en
        self.label_ar = self.label_ar or ar
        if self.type == "payment":
            self.pay_mode = self.pay_mode or "rest"
            if self.pay_mode == "percent" and not (self.pay_value and 0 < self.pay_value <= 100):
                raise ValueError("A payment in percent needs a value between 1 and 100")
            if self.pay_mode == "fixed" and not self.pay_value:
                raise ValueError("A fixed payment needs its amount")
            if self.pay_mode == "rest":
                self.pay_value = None
        else:
            self.pay_mode = self.pay_value = None
        return self


def validate(items: list[StepIn]) -> list[StepIn]:
    if not items:
        raise HTTPException(422, "A workflow needs at least one step")
    if len(items) > MAX_STEPS:
        raise HTTPException(422, f"A workflow can have at most {MAX_STEPS} steps")
    if len({s.key for s in items}) != len(items):
        raise HTTPException(422, "Two steps have the same key")
    for kind in ONCE:
        if sum(s.type == kind for s in items) > 1:
            raise HTTPException(422, f"Only one '{TYPES[kind][0]}' step is possible")
    if any(s.type == "intake" for s in items) and items[0].type != "intake":
        raise HTTPException(422, "Request details must be the first step")
    pays = [s for s in items if s.type == "payment"]
    if sum(s.pay_value for s in pays if s.pay_mode == "percent") > 100:
        raise HTTPException(422, "The payments add up to more than 100%")
    if pays and pays[-1].pay_mode != "rest":
        raise HTTPException(422, "The last payment must be the rest of the amount")
    if sum(s.pay_mode == "rest" for s in pays) > 1:
        raise HTTPException(422, "Only the last payment can be the rest of the amount")
    return items


def _t(type_, key=None, en="", ar="") -> dict:
    return {"key": key or type_, "type": type_, "label_en": en, "label_ar": ar}


PAY = {"key": "payment", "type": "payment", "pay_mode": "rest", "label_en": "", "label_ar": ""}
STANDARD = [_t("intake"), _t("review"), _t("quote"), _t("documents"), PAY, _t("booking"), _t("delivery"), _t("trip"),
            _t("feedback")]
DEFAULTS: dict[str, list[dict]] = {
    "packages": [PAY, _t("documents"), _t("booking"), _t("delivery"), _t("trip"), _t("feedback")],
    "custom_trip": STANDARD,
    "flights": STANDARD,
    "hotel": STANDARD,
    "visa": [_t("intake"), _t("review"), _t("quote"), _t("documents"), PAY,
             _t("booking", en="Visa application", ar="تقديم طلب التأشيرة"),
             _t("delivery", en="Send the visa", ar="إرسال التأشيرة"), _t("trip"), _t("feedback")],
    "concierge": [_t("intake"), _t("review"), _t("quote"), PAY, _t("booking", en="Arrange it", ar="الترتيب"), _t("feedback")],
    "embassy": [_t("intake"), _t("review"), _t("documents"), _t("schedule", en="Embassy appointment", ar="موعد السفارة"),
                PAY, _t("task", "accompany", "Go with the client to the embassy", "مرافقة العميل إلى السفارة"), _t("feedback")],
    "airport_assist": [_t("intake"), _t("review"), _t("schedule", en="Meeting time at the airport", ar="موعد اللقاء في المطار"),
                       PAY, _t("task", "assist", "Meet the client and finish the airport steps", "استقبال العميل وإنهاء إجراءات المطار"),
                       _t("feedback")],
    "airport_transfer": [_t("intake"), _t("review"), _t("schedule", en="Pick-up time", ar="وقت الاستقبال"), PAY,
                         _t("task", "drive", "Drive the client", "توصيل العميل"), _t("feedback")],
}
GENERIC = [_t("intake"), _t("review"), _t("quote"), _t("documents"), PAY, _t("booking"), _t("delivery"), _t("feedback")]


def template_for(service) -> list[dict]:
    """A service's workflow: its own, else the built-in default for its kind."""
    if service is None or service.pricing == "packages":
        raw = (service.workflow if service is not None else None) or DEFAULTS["packages"]
    elif service.workflow:
        raw = service.workflow
    else:
        raw = DEFAULTS.get(service.key or "", GENERIC)
    return [StepIn.model_validate(s).model_dump(mode="json") for s in raw]


def steps(ticket: Ticket) -> list[dict]:
    return [dict(s) for s in (ticket.workflow or [])]


def active(ticket: Ticket) -> dict | None:
    return next((s for s in steps(ticket) if s.get("state") == "active"), None)


def find(ticket: Ticket, kind: str) -> dict | None:
    return next((s for s in steps(ticket) if s["type"] == kind), None)


def _store(ticket: Ticket, items: list[dict]) -> None:
    ticket.workflow = [dict(s) for s in items]  # a new list, so the change is saved


def _entered(ticket: Ticket, step: dict) -> None:
    """Steps started since the last commit, for the client message sent after it (see announce)."""
    pending = ticket.__dict__.setdefault("_entered_steps", [])
    if step and all(s["key"] != step["key"] for s in pending):
        pending.append(step)


def take_entered(ticket: Ticket) -> list[dict]:
    keys = [s["key"] for s in ticket.__dict__.pop("_entered_steps", [])]
    current = {s["key"]: s for s in steps(ticket)}
    return [current[k] for k in keys if k in current and current[k].get("state") == "active"]


# --- Money of the payment steps -----------------------------------------------------------------------

def _paid(ticket: Ticket) -> Decimal:
    from .services.request_desk import money  # noqa: PLC0415

    return Decimal(str(money(ticket)["paid"] or 0))


def installments(ticket: Ticket) -> list[dict]:
    """Each payment step with its amount and the running total due through it."""
    total, paid = Decimal(str(ticket.total_price or 0)), _paid(ticket)
    out, running = [], Decimal(0)
    for s in steps(ticket):
        if s["type"] != "payment":
            continue
        value = Decimal(str(s.get("pay_value") or 0))
        left = max(total - running, Decimal(0))
        if s.get("pay_mode") == "percent":
            amount = min((total * value / 100).quantize(Decimal("0.001")), left)
        elif s.get("pay_mode") == "fixed":
            amount = min(value, left)
        else:
            amount = left
        running += amount
        out.append({"key": s["key"], "label_en": s["label_en"], "label_ar": s["label_ar"], "amount": float(amount),
                    "through": float(running), "state": s.get("state"),
                    "covered": total > 0 and paid + Decimal("0.0005") >= running})
    return out


def due_now(ticket: Ticket) -> float | None:
    """What the client has to pay now for the active payment step (None when no payment is waiting)."""
    step = active(ticket)
    if not step or step["type"] != "payment" or not ticket.total_price:
        return None
    row = next(i for i in installments(ticket) if i["key"] == step["key"])
    return max(round(row["through"] - float(_paid(ticket)), 3), 0.0)


# --- Status ---------------------------------------------------------------------------------------------

def _status_for(ticket: Ticket) -> str:
    step = active(ticket)
    if step is None:
        return T.COMPLETED
    kind = step["type"]
    if kind in ("intake", "review"):
        return T.NEW
    if kind == "quote":
        return ticket.status if ticket.status in QUOTING else T.NEW
    if kind == "payment":
        from .services.request_desk import money  # noqa: PLC0415

        m = money(ticket)
        row = next(i for i in installments(ticket) if i["key"] == step["key"])
        paid_before = row["through"] - row["amount"]
        return T.IN_PROGRESS if m["pending_proofs"] or float(_paid(ticket)) > paid_before + 0.0005 else T.PENDING_PAYMENT
    if kind in ("trip", "feedback"):
        return T.CONFIRMED
    items = steps(ticket)
    before = items[:next(i for i, s in enumerate(items) if s["key"] == step["key"])]
    paid_steps = [s for s in before if s["type"] == "payment"]
    return T.PAID if paid_steps and all(s.get("state") in ("done", "skipped") for s in paid_steps) else T.WORKING


def sync(db: Session, ticket: Ticket, actor: str = "System", user: User | None = None) -> None:
    if ticket.status in CLOSED:
        return
    new = _status_for(ticket)
    if new != ticket.status:
        from .services.requests import event  # noqa: PLC0415

        event(db, ticket, actor, "status", ticket.status, new, user)
        ticket.status = new


# --- Building and placing a request's workflow --------------------------------------------------------

def _target(items: list[dict], status: str) -> int:
    """Where a status puts a request in its workflow (requests made before workflows, manual status changes)."""
    first = {}
    for i, s in enumerate(items):
        first.setdefault(s["type"], i)
    pay = first.get("payment")
    if status in QUOTING:
        return first.get("quote", first.get("review", 0))
    if status in (T.PENDING_PAYMENT, T.IN_PROGRESS):
        return pay if pay is not None else first.get("booking", 0)
    if status in (T.PAID, T.WORKING):
        return pay + 1 if pay is not None else first.get("booking", 0)
    if status == T.CONFIRMED:
        return first["delivery"] + 1 if "delivery" in first else first.get("trip", len(items))
    if status == T.COMPLETED:
        return len(items)
    return 0


def place(ticket: Ticket, status: str) -> None:
    """Marks the steps before `status`'s place done and makes the one there active."""
    items = steps(ticket)
    at = min(_target(items, status), len(items))
    now = utcnow().isoformat()
    for i, s in enumerate(items):
        if i < at:
            if s.get("state") not in ("done", "skipped"):
                s.update(state="done", done_at=now, by="System")
        elif i == at:
            if s.get("state") != "active":
                s.update(state="active", started_at=now)
        else:
            s["state"] = "pending"
    _store(ticket, items)


def ensure(ticket: Ticket) -> None:
    """Gives a request made before workflows its workflow, placed where its status is."""
    if ticket.workflow:
        return
    _store(ticket, [dict(s, state="pending") for s in template_for(ticket.service)])
    place(ticket, T.NEW if ticket.status in CLOSED else ticket.status)


def start(db: Session, ticket: Ticket, actor: str = "System") -> None:
    """A new request: its service's workflow from the first step (steps already done are passed)."""
    now = utcnow().isoformat()
    _store(ticket, [dict(s, state="active", started_at=now) if i == 0 else dict(s, state="pending")
                    for i, s in enumerate(template_for(ticket.service))])
    refresh(db, ticket, actor)


# --- Moving forward -------------------------------------------------------------------------------------

def _auto_done(ticket: Ticket, step: dict, today: date) -> bool:
    kind = step["type"]
    if kind == "intake":
        from .catalog import check_answers  # noqa: PLC0415

        return ticket.service is None or not check_answers(ticket.service, ticket.answers or {})[1]
    if kind == "documents":
        from .services.request_desk import documents_view  # noqa: PLC0415

        return documents_view(ticket)["missing"] == 0
    if kind == "payment":
        row = next((i for i in installments(ticket) if i["key"] == step["key"]), None)
        return bool(ticket.total_price) and row is not None and (row["amount"] == 0 or row["covered"])
    if kind == "booking":
        from .services.request_files import DOCS_STEP, checklist_view  # noqa: PLC0415

        todo = [s for s in checklist_view(ticket) if s["key"] != DOCS_STEP]
        return bool(todo) and all(s["done"] for s in todo)
    if kind == "delivery":
        return ticket.documents_sent_at is not None
    if kind == "schedule":
        return bool(step.get("confirmed_at"))
    if kind == "trip":
        return trip_over(ticket, today)
    if kind == "feedback":
        db = object_session(ticket)
        return db is not None and ticket.id is not None and bool(
            db.scalar(select(TripFeedback.id).where(TripFeedback.ticket_id == ticket.id)))
    return False


def _finish(db: Session, ticket: Ticket, key: str, actor: str, user: User | None, note: str | None = None,
            state: str = "done") -> None:
    from .services.requests import event  # noqa: PLC0415

    items = steps(ticket)
    for i, s in enumerate(items):
        if s["key"] == key:
            s.update(state=state, done_at=utcnow().isoformat(), by=actor[:120], by_id=user.id if user else None,
                     hours=_hours_since(s.get("started_at")))
            if note:
                s["note"] = note.strip()[:500]
            event(db, ticket, actor, "step_skipped" if state == "skipped" else "step_done", None, s["label_en"], user)
            nxt = next((x for x in items[i + 1:] if x.get("state") == "pending"), None)
            if nxt:
                nxt.update(state="active", started_at=utcnow().isoformat())
                _store(ticket, items)
                _entered(ticket, nxt)
                return
            break
    _store(ticket, items)


def _hours_since(iso: str | None) -> float | None:
    if not iso:
        return None
    from datetime import datetime, timezone  # noqa: PLC0415

    started = datetime.fromisoformat(iso)
    started = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
    return round(max((utcnow() - started).total_seconds() / 3600, 0), 2)


def refresh(db: Session, ticket: Ticket, actor: str = "System", user: User | None = None,
            today: date | None = None) -> None:
    """Passes the active steps whose work is done and updates the status. Call after anything that can finish
    a step: an answer, a document, a payment, a booking step, the travel documents, the trip's end."""
    ensure(ticket)
    if ticket.status in CLOSED:
        return
    today = today or local_today()
    for _ in range(MAX_STEPS):
        step = active(ticket)
        if step is None or not _auto_done(ticket, step, today):
            break
        _finish(db, ticket, step["key"], "System", None)
    sync(db, ticket, actor, user)


def complete(db: Session, ticket: Ticket, actor: str, user: User, key: str | None = None, note: str | None = None,
             skip: bool = False) -> None:
    """The team marks the active step done (or skipped)."""
    ensure(ticket)
    step = active(ticket)
    if ticket.status in CLOSED or step is None or (key and step["key"] != key):
        raise HTTPException(409, "This step is not the current one")
    allowed = TEAM_DONE | (ADMIN_DONE if user.role == "company_admin" else set())
    if step["type"] not in allowed:
        raise HTTPException(403 if step["type"] in ADMIN_DONE else 409,
                            "Only a company admin can pass a payment" if step["type"] in ADMIN_DONE
                            else "This step finishes when the client answers")
    _finish(db, ticket, step["key"], actor, user, note, "skipped" if skip else "done")
    refresh(db, ticket, actor, user)


def finish_quote(db: Session, ticket: Ticket, actor: str) -> None:
    """The client approved the final quotation."""
    ensure(ticket)
    step = active(ticket)
    if step and step["type"] == "quote":
        _finish(db, ticket, step["key"], actor, None)
    refresh(db, ticket, actor)


def reach(db: Session, ticket: Ticket, kind: str, actor: str, user: User | None = None,
          passing: frozenset = frozenset({"intake", "review", "task"})) -> None:
    """The team works on a later step (sends choices while the request is in review, sends the travel documents
    before ticking every step…): the steps before it of the `passing` kinds are done. An unpaid payment is never
    passed this way."""
    ensure(ticket)
    if find(ticket, kind) is None or find(ticket, kind).get("state") in ("done", "skipped"):
        return
    for _ in range(MAX_STEPS):
        step = active(ticket)
        if step is None or step["type"] == kind:
            break
        if step["type"] == "payment":
            raise HTTPException(409, f"The client has to pay first ({step['label_en']})")
        if step["type"] not in passing:
            raise HTTPException(409, f"Finish '{step['label_en']}' first")
        _finish(db, ticket, step["key"], actor, user)
    sync(db, ticket, actor, user)


def edit(db: Session, ticket: Ticket, new_steps: list[StepIn], actor: str, user: User) -> None:
    """Changes one request's steps that have not started; the done and active ones stay as they are."""
    from .services.requests import event  # noqa: PLC0415

    ensure(ticket)
    items = steps(ticket)
    fixed = [s for s in items if s.get("state") in ("done", "skipped", "active")]
    if [s.key for s in new_steps[:len(fixed)]] != [s["key"] for s in fixed]:
        raise HTTPException(422, "Steps already started or done can't be moved or removed")
    tail = [s for s in new_steps[len(fixed):]]
    validate([StepIn.model_validate(s) for s in fixed] + tail)
    merged = fixed + [dict(s.model_dump(mode="json"), state="pending") for s in tail]
    if not any(s["state"] == "active" for s in merged) and tail:
        merged[len(fixed)].update(state="active", started_at=utcnow().isoformat())
    _store(ticket, merged)
    event(db, ticket, actor, "workflow_changed", None, " → ".join(s["label_en"] for s in merged), user)
    refresh(db, ticket, actor, user)


def set_step(ticket: Ticket, key: str, **values) -> dict:
    items = steps(ticket)
    step = next((s for s in items if s["key"] == key), None)
    if step is None:
        raise HTTPException(404, "Step not found")
    step.update(values)
    _store(ticket, items)
    return step


# --- Closing --------------------------------------------------------------------------------------------

def cancel(db: Session, ticket: Ticket, by: Literal["client", "team"], reason: str | None, actor: str,
           user: User | None = None, rejected: bool = False) -> None:
    """Closes the request, keeping who closed it, why and at which step."""
    from .services import seats  # noqa: PLC0415
    from .services.requests import event  # noqa: PLC0415

    if ticket.status in CLOSED:
        raise HTTPException(409, "This request is already closed")
    reason = record_close(ticket, by, reason, actor)
    seats.release(db, ticket)
    new = T.REJECTED if rejected else T.CANCELLED
    event(db, ticket, actor, "status", ticket.status, new, user)
    if reason:
        event(db, ticket, actor, "close_reason", None, reason, user)
    ticket.status = new


def record_close(ticket: Ticket, by: str, reason: str | None, actor: str) -> str:
    ensure(ticket)
    step = active(ticket)
    reason = (reason or "").strip()[:500]
    ticket.cancel_info = {"by": by, "name": actor[:120], "reason": reason, "step": step["key"] if step else None,
                          "step_en": step["label_en"] if step else None, "step_ar": step["label_ar"] if step else None,
                          "status": ticket.status, "at": utcnow().isoformat()}
    return reason


def reopened(db: Session, ticket: Ticket, status: str) -> None:
    """A closed request opened again at `status`."""
    ensure(ticket)
    ticket.cancel_info = None
    place(ticket, status)


def trip_over(ticket: Ticket, today: date) -> bool:
    end = ticket.return_date or ticket.departure_date
    try:
        return bool(end) and date.fromisoformat(end[:10]) < today
    except ValueError:
        return False


def pass_finished_trips(db: Session, today: date) -> int:
    """Daily: requests whose trip ended move on to feedback (and requests with feedback are completed)."""
    rows = db.scalars(select(Ticket).where(Ticket.status == T.CONFIRMED)).all()
    moved = 0
    for ticket in rows:
        before = ticket.status, (active(ticket) or {}).get("key")
        refresh(db, ticket, "System", today=today)
        moved += (ticket.status, (active(ticket) or {}).get("key")) != before
    db.commit()
    return moved


def current(ticket: Ticket) -> dict | None:
    """The active step, short (for lists)."""
    if ticket.status in CLOSED:
        return None
    step = active(ticket) if ticket.workflow else None
    return {k: step.get(k) for k in ("key", "type", "label_en", "label_ar", "started_at")} if step else None


# --- How long a step should take ------------------------------------------------------------------------

# Hours a step may stay active before it counts as late (the owner can change them for the company), and who
# the request waits for at that step.
DEFAULT_HOURS: dict[str, int] = {"intake": 24, "review": 4, "quote": 24, "documents": 72, "payment": 72,
                                 "schedule": 24, "booking": 48, "delivery": 48, "task": 24, "feedback": 168}
CLIENT_TURN = {"intake", "documents", "payment"}
CLIENT_QUOTE = (T.QUOTED, T.FINAL)


def hours_for(company, kind: str) -> int | None:
    own = (company.sla or {}) if company is not None and isinstance(getattr(company, "sla", None), dict) else {}
    value = own.get(kind, DEFAULT_HOURS.get(kind))
    return int(value) if value else None


def waiting_on(ticket: Ticket, step: dict) -> str:
    if step["type"] in CLIENT_TURN:
        from .services.request_desk import money  # noqa: PLC0415

        if step["type"] == "payment" and (money(ticket)["pending_proofs"] or not ticket.total_price):
            return "team"  # a receipt to check, or no price yet
        return "client"
    if step["type"] == "quote" and ticket.status in CLIENT_QUOTE:
        return "client"
    if step["type"] == "schedule" and step.get("appointment"):
        return "client"
    return "team"


def delay(ticket: Ticket, company, now=None) -> dict | None:
    """How long the request has been at its step, against the expected time, and who it waits for."""
    if ticket.status in CLOSED or not ticket.workflow:
        return None
    step = active(ticket)
    if step is None or not step.get("started_at") or step["type"] == "trip":
        return None
    from datetime import datetime, timezone  # noqa: PLC0415

    started = datetime.fromisoformat(step["started_at"])
    started = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
    hours = max(((now or utcnow()) - started).total_seconds() / 3600, 0)
    limit = hours_for(company, step["type"])
    who = waiting_on(ticket, step)
    return {"step": step["key"], "hours": round(hours, 1), "limit": limit, "waiting_on": who,
            "late": bool(limit) and hours > limit}


def view(ticket: Ticket) -> dict:
    ensure(ticket)
    return {"steps": steps(ticket), "installments": installments(ticket), "due_now": due_now(ticket),
            "cancel": ticket.cancel_info if ticket.status in CLOSED else None}
