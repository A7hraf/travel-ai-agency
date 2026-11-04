"""Activity log: the company admins' Activity page and the owner's "Activity" tab of a company."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import ACTIONS
from ..database import get_db
from ..deps import get_company_user, require_system_admin
from ..models import AuditEvent, Company, Role, User

router = APIRouter(prefix="/api", tags=["activity"])


class ActivityItem(BaseModel):
    id: int
    created_at: datetime
    user_id: int | None
    actor: str
    action: str
    label: str
    target: str | None
    detail: str | None


class ActivityPeople(BaseModel):
    user_id: int | None
    actor: str


class ActivityOut(BaseModel):
    items: list[ActivityItem]
    actions: dict[str, str]
    people: list[ActivityPeople]
    has_more: bool


def require_company_admin(user: User = Depends(get_company_user)) -> User:
    if user.role != Role.COMPANY_ADMIN:
        raise HTTPException(403, "Only a company admin can see the activity log")
    return user


def _activity(db: Session, company_id: int, days: int, action: str | None, user_id: int | None,
              before_id: int | None, limit: int) -> ActivityOut:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = select(AuditEvent).where(AuditEvent.company_id == company_id, AuditEvent.created_at >= since)
    stmt = base
    if action:
        # "ticket" matches every ticket action; "ticket.status" only that one.
        stmt = stmt.where(AuditEvent.action == action) if "." in action else \
            stmt.where(AuditEvent.action.like(f"{action}.%"))
    if user_id is not None:
        stmt = stmt.where(AuditEvent.user_id == user_id)
    if before_id is not None:
        stmt = stmt.where(AuditEvent.id < before_id)
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1)).all()
    people = db.execute(select(AuditEvent.user_id, AuditEvent.actor).where(
        AuditEvent.company_id == company_id, AuditEvent.created_at >= since).distinct().limit(200)).all()
    return ActivityOut(
        items=[ActivityItem(id=r.id, created_at=r.created_at, user_id=r.user_id, actor=r.actor, action=r.action,
                            label=ACTIONS.get(r.action, r.action), target=r.target, detail=r.detail)
               for r in rows[:limit]],
        actions=ACTIONS,
        people=[ActivityPeople(user_id=u, actor=a) for u, a in sorted(set(people), key=lambda p: p[1].lower())],
        has_more=len(rows) > limit,
    )


def _query(days: int = Query(default=30, ge=1, le=365),
           action: str | None = Query(default=None, max_length=40, pattern=r"^[a-z]+(\.[a-z_]+)?$"),
           user_id: int | None = None,
           before_id: int | None = None,
           limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"days": days, "action": action, "user_id": user_id, "before_id": before_id, "limit": limit}


@router.get("/activity", response_model=ActivityOut)
def company_activity(q: dict = Depends(_query), me: User = Depends(require_company_admin),
                     db: Session = Depends(get_db)):
    return _activity(db, me.company_id, **q)


@router.get("/system/companies/{company_id}/activity", response_model=ActivityOut)
def any_company_activity(company_id: int, q: dict = Depends(_query), _: User = Depends(require_system_admin),
                         db: Session = Depends(get_db)):
    if db.get(Company, company_id) is None:
        raise HTTPException(404, "Company not found")
    return _activity(db, company_id, **q)
