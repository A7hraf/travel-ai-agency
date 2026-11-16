"""The AI advisor chat: for a company's owner and managers (``/api/advisor``), and for the platform owner
(``/api/system/advisor``)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..addons import require_addon, use, user_may
from ..database import get_db
from ..deps import require_permission, require_system_admin
from ..models import AdvisorMessage, User
from ..ratelimit import limiter
from ..services import advisor as svc

router = APIRouter(tags=["advisor"])


class AskIn(BaseModel):
    text: str = Field(min_length=2, max_length=4000)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


def _out(rows: list[AdvisorMessage]) -> list[MessageOut]:
    return [MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in rows]


def company_user(me: User = Depends(require_permission("reports.view"))) -> User:
    require_addon(me.company, "advisor")
    if not user_may(me, "advisor"):
        raise HTTPException(403, "Your company admin has not given you this feature")
    return me


@router.get("/api/advisor", response_model=list[MessageOut])
def company_chat(me: User = Depends(company_user), db: Session = Depends(get_db)):
    return _out(svc.history(db, me.company_id))


@router.post("/api/advisor", response_model=list[MessageOut])
def company_ask(body: AskIn, me: User = Depends(company_user), db: Session = Depends(get_db)):
    limiter.check(f"advisor:{me.company_id}", 60, "The advisor is busy: please try again in a few minutes", window=3600)
    use(db, me, "advisor")
    return _out(svc.ask(db, me, me.company, body.text))


@router.delete("/api/advisor", status_code=204)
def company_clear(me: User = Depends(company_user), db: Session = Depends(get_db)):
    db.execute(delete(AdvisorMessage).where(AdvisorMessage.company_id == me.company_id))
    db.commit()


@router.get("/api/system/advisor", response_model=list[MessageOut])
def platform_chat(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return _out(svc.history(db, None))


@router.post("/api/system/advisor", response_model=list[MessageOut])
def platform_ask(body: AskIn, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    limiter.check("advisor:platform", 60, "The advisor is busy: please try again in a few minutes", window=3600)
    return _out(svc.ask(db, me, None, body.text))


@router.post("/api/system/advisor/check", response_model=list[MessageOut])
def platform_check(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Looks for findings now (they are also looked for once a day)."""
    svc.platform_findings(db)
    db.commit()
    return _out(svc.history(db, None))


@router.delete("/api/system/advisor", status_code=204)
def platform_clear(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    db.execute(delete(AdvisorMessage).where(AdvisorMessage.company_id.is_(None)))
    db.commit()
