"""Activity log: one short row per important staff action (see models.AuditEvent).

``audit(db, user, "package.created", target=title)`` adds the row to the caller's transaction, so it
is saved with the change itself (pass commit=True when the change was already committed). Texts are
short and never hold secrets: callers pass names and field names, never values of tokens or passwords.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .diagnostics import scrub
from .models import AuditEvent, User, utcnow

log = logging.getLogger(__name__)

# Every action the log knows, with the English label the Activity page shows.
ACTIONS: dict[str, str] = {
    "auth.login": "Logged in",
    "user.created": "Account created",
    "user.updated": "Account changed",
    "user.disabled": "Account disabled",
    "user.enabled": "Account enabled",
    "user.deleted": "Account deleted",
    "package.created": "Package created",
    "package.updated": "Package edited",
    "package.deleted": "Package deleted",
    "package.hidden": "Package hidden (has bookings)",
    "ticket.status": "Booking status changed",
    "ticket.payment": "Payment reference changed",
    "ticket.price": "Booking price changed",
    "customer.updated": "Customer details changed",
    "branding.saved": "Customer page design saved",
    "settings.saved": "Company settings saved",
    "ai.knowledge": "AI knowledge changed",
    "ai.training": "AI training changed",
    "whatsapp.connected": "WhatsApp connected",
    "whatsapp.disconnected": "WhatsApp disconnected",
    "whatsapp.credentials": "WhatsApp credentials changed",
    "instagram.connected": "Instagram connected",
    "instagram.disconnected": "Instagram disconnected",
    "instagram.credentials": "Instagram credentials changed",
}

PLATFORM_OWNER = "Platform owner"

# Retention: a year of history, and at most this many rows per company (oldest go first). Checked
# when someone of the company logs in, so the log never grows without limit.
KEEP_DAYS = 365
MAX_ROWS_PER_COMPANY = 100_000


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = " ".join(str(text).split())
    return (text[: limit - 1] + "…") if len(text) > limit else (text or None)


def audit(db: Session, user: User | None, action: str, target: str | None = None, detail: str | None = None,
          company_id: int | None = None, commit: bool = False) -> None:
    """Records one action of ``user`` in their company (or in ``company_id`` for the platform owner).
    Never fails the request: a problem here is logged and the action goes on."""
    try:
        cid = company_id if company_id is not None else (user.company_id if user is not None else None)
        if cid is None:
            return
        actor = user.full_name if user is not None and user.company_id is not None else PLATFORM_OWNER
        db.add(AuditEvent(company_id=cid, user_id=user.id if user is not None else None, actor=_clip(actor, 200),
                          action=action[:40], target=_clip(target, 200),
                          detail=_clip(scrub(detail) if detail else None, 300)))
        if action == "auth.login":
            prune(db, cid)
        if commit:
            db.commit()
    except Exception:  # noqa: BLE001
        log.warning("Could not record activity %s", action, exc_info=True)


def prune(db: Session, company_id: int) -> None:
    """Removes the company's rows older than KEEP_DAYS and beyond the newest MAX_ROWS_PER_COMPANY
    (two indexed queries on company_id)."""
    db.flush()  # the row just added counts too
    mine = AuditEvent.company_id == company_id
    db.execute(delete(AuditEvent).where(mine, AuditEvent.created_at < utcnow() - timedelta(days=KEEP_DAYS))
               .execution_options(synchronize_session=False))
    cutoff = db.scalar(select(AuditEvent.id).where(mine).order_by(AuditEvent.id.desc())
                       .offset(MAX_ROWS_PER_COMPANY - 1).limit(1))
    if cutoff is not None:
        db.execute(delete(AuditEvent).where(mine, AuditEvent.id < cutoff).execution_options(synchronize_session=False))
