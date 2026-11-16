"""The employee's notifications (bell in the staff screens)."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_company_user
from ..models import User
from ..services import notifications as svc

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    kind: str
    params: dict
    ticket_id: int | None
    read: bool
    created_at: datetime


class ReadIn(BaseModel):
    ids: list[int] | None = Field(default=None, max_length=200)  # None: all


@router.get("")
def list_mine(me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    rows, unread = svc.mine(db, me)
    return {"unread": unread, "items": [NotificationOut(id=n.id, kind=n.kind, params=n.params or {}, ticket_id=n.ticket_id,
                                                        read=n.read_at is not None, created_at=n.created_at) for n in rows]}


@router.post("/read", status_code=204)
def read(body: ReadIn, me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    svc.mark_read(db, me, body.ids)
    db.commit()
