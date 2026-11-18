"""Learning from the data: a company's client groups (a feature the platform owner grants, with levels) and the
market across every company (the platform owner only)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..addons import grant, user_may
from ..database import get_db
from ..deps import require_permission, require_system_admin
from ..models import User
from ..services import segments as svc
from ..timeutil import local_today

router = APIRouter(tags=["segments"])


def levels(user: User) -> list[str]:
    """The levels the platform owner gave this company (none ticked: all)."""
    return list(grant(user.company, "client_segments").levels) or list(svc.LEVELS)


def segments_user(me: User = Depends(require_permission("customers.manage"))) -> User:
    if not user_may(me, "client_segments"):
        raise HTTPException(403, "Client segments are not switched on for your company. Ask the platform admin.")
    return me


@router.get("/api/segments")
def my_segments(me: User = Depends(segments_user), db: Session = Depends(get_db)):
    data = svc.client_segments(db, me.company, local_today(), levels(me))
    data["can_target"] = "targeting" in data["levels"] and user_may(me, "broadcasts")
    return data


@router.get("/api/system/market")
def market(days: int = 365, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return svc.market(db, local_today(), max(30, min(days, 730)))
