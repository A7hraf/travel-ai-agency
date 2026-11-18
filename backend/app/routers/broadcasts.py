"""Messages to a group of clients (an offer, news, a feedback request), when the company has broadcasts."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..addons import require_addon, use, user_may
from ..audit import audit
from ..database import get_db
from ..deps import get_company_user
from ..models import Broadcast, Role, User
from ..permissions import effective_permissions
from ..ratelimit import limiter
from ..services import broadcasts as svc
from ..timeutil import local_today

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])


def manager(me: User = Depends(get_company_user)) -> User:
    require_addon(me.company, "broadcasts")
    if me.role != Role.COMPANY_ADMIN and "customers.manage" not in effective_permissions(me):
        raise HTTPException(403, "Missing permission: customers.manage")
    return me


@router.get("")
def history(me: User = Depends(manager), db: Session = Depends(get_db)):
    rows = db.scalars(select(Broadcast).where(Broadcast.company_id == me.company_id).order_by(Broadcast.id.desc()).limit(50)).all()
    return [{"id": b.id, "kind": b.kind, "text_en": b.text_en, "text_ar": b.text_ar, "audience": b.audience, "sent": b.sent,
             "skipped": b.skipped, "created_by": b.created_by, "created_at": b.created_at} for b in rows]


def _check_segment(me: User, audience: svc.Audience) -> None:
    """A group from Client segments needs that feature with its targeting level."""
    if audience.segment is None:
        return
    from .segments import levels  # noqa: PLC0415
    from ..services.segments import SEGMENTS  # noqa: PLC0415

    if audience.segment not in SEGMENTS:
        raise HTTPException(422, "Unknown client group")
    if not user_may(me, "client_segments") or "targeting" not in levels(me):
        raise HTTPException(403, "Messages to a client group are not switched on for your company. Ask the platform admin.")


@router.post("/preview")
def preview(body: svc.Audience, me: User = Depends(manager), db: Session = Depends(get_db)):
    _check_segment(me, body)
    people = svc.recipients(db, me.company, body, local_today())
    return {"count": len(people), "sample": [c.name or f"+{c.whatsapp_id}" for c in people[:5]], "limit": svc.MAX_RECIPIENTS}


@router.post("", status_code=201)
def send(body: svc.BroadcastIn, me: User = Depends(manager), db: Session = Depends(get_db)):
    limiter.check(f"broadcast:{me.company_id}", 5, "Wait a little before sending another message to many clients", window=3600)
    _check_segment(me, body.audience)
    use(db, me, "broadcasts")
    b = svc.send(db, me.company, body, me, local_today())
    audit(db, me, "broadcast.sent", detail=f"{b.kind}: {b.sent} sent, {b.skipped} not reached", commit=True)
    return {"id": b.id, "sent": b.sent, "skipped": b.skipped}
