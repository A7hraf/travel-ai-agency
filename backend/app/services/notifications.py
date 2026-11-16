"""In-app notifications for the team: who hears about what happens on a request.

A notification goes to the request's assigned employee; when nobody has it yet, to the colleagues who
assign requests (and the company admins). Some go to the company admins only (a price or payment reference
changed by an employee). The reader's screen writes the text from `kind` and `params`, in their language.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Notification, Role, Ticket, User, utcnow
from ..permissions import effective_permissions

KINDS = ("new_request", "assigned", "client_answered", "client_file", "receipt", "client_approved", "client_cancelled",
         "step_late", "price_changed", "reference_changed", "client_problem")
KEEP_DAYS = 60


def _people(db: Session, company_id: int, *, admins_only: bool = False) -> list[User]:
    users = db.scalars(select(User).where(User.company_id == company_id, User.is_active.is_(True))).all()
    if admins_only:
        return [u for u in users if u.role == Role.COMPANY_ADMIN]
    return [u for u in users if u.role == Role.COMPANY_ADMIN or "tickets.assign" in effective_permissions(u)]


def _params(ticket: Ticket | None, extra: dict) -> dict:
    base = {"ref": ticket.reference, "client": ticket.lead_traveler_name or "",
            "service": ticket.service.name_en if ticket and ticket.service else (ticket.package_title if ticket else "")} \
        if ticket is not None else {}
    return {**base, **{k: str(v)[:200] for k, v in extra.items() if v is not None}}


def notify(db: Session, ticket: Ticket, kind: str, *, to: str = "owner", skip: User | None = None, **extra) -> int:
    """`to`: "owner" (the assignee, else the people who assign), or "admins". Never the person who acted."""
    if to == "admins":
        people = _people(db, ticket.company_id, admins_only=True)
    elif ticket.assigned_to_id:
        people = [ticket.assigned_to] if ticket.assigned_to and ticket.assigned_to.is_active else []
    else:
        people = _people(db, ticket.company_id)
    sent = 0
    for user in people:
        if skip is not None and user.id == skip.id:
            continue
        db.add(Notification(company_id=ticket.company_id, user_id=user.id, ticket_id=ticket.id, kind=kind,
                            params=_params(ticket, extra)))
        sent += 1
    return sent


def to_user(db: Session, user: User, ticket: Ticket | None, kind: str, **extra) -> None:
    db.add(Notification(company_id=user.company_id, user_id=user.id, ticket_id=ticket.id if ticket else None, kind=kind,
                        params=_params(ticket, extra)))


def mine(db: Session, user: User, limit: int = 50) -> tuple[list[Notification], int]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.company_id == user.company_id)
                      .order_by(Notification.id.desc()).limit(limit)).all()
    unread = sum(1 for n in rows if n.read_at is None)
    return rows, unread


def mark_read(db: Session, user: User, ids: list[int] | None) -> None:
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=utcnow()))


def clean_old(db: Session) -> None:
    from sqlalchemy import delete  # noqa: PLC0415

    db.execute(delete(Notification).where(Notification.created_at < utcnow() - timedelta(days=KEEP_DAYS)))


def late_steps(db: Session) -> int:
    """Tells the assigned employee (else the people who assign) once when the team holds a step too long."""
    from .. import workflow  # noqa: PLC0415
    from ..models import Company, CompanyStatus, TicketStatus as T  # noqa: PLC0415

    open_ = (T.NEW, T.CHANGES, T.CHOSEN, T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING)
    rows = db.scalars(select(Ticket).join(Company, Company.id == Ticket.company_id).where(
        Ticket.status.in_(open_), Company.status == CompanyStatus.ACTIVE, Ticket.workflow.is_not(None))).all()
    sent = 0
    for ticket in rows:
        d = workflow.delay(ticket, ticket.company)
        step = workflow.active(ticket)
        if not d or not d["late"] or d["waiting_on"] != "team" or step.get("late_noted"):
            continue
        workflow.set_step(ticket, step["key"], late_noted=True)
        sent += notify(db, ticket, "step_late", step=step["label_en"], step_ar=step["label_ar"], hours=int(d["hours"]))
    db.commit()
    return sent
