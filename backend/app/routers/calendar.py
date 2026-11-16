"""The company calendar (``/api/calendar``): appointments with WhatsApp reminders, and trips leaving or coming back."""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..addons import require_addon
from ..audit import audit
from ..branding import clean_text
from ..database import get_db
from ..deps import require_permission
from ..models import Appointment, Ticket, User
from ..services import calendar as svc
from ..timeutil import local_today

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


def viewer(me: User = Depends(require_permission("tickets.view"))) -> User:
    require_addon(me.company, "calendar")
    return me


def editor(me: User = Depends(require_permission("tickets.manage"))) -> User:
    require_addon(me.company, "calendar")
    return me


class AppointmentIn(BaseModel):
    kind: Literal["meeting", "airport", "call", "visit", "other"] = "meeting"
    title: str = Field(min_length=2, max_length=200)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    ticket_id: int | None = None
    assigned_to_id: int | None = None
    remind_minutes: int = Field(default=60, ge=0, le=7 * 24 * 60)
    remind_client: bool = False
    client_remind_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    remind_owner: bool = False
    status: Literal["planned", "done", "cancelled"] = "planned"

    @field_validator("title", "location")
    @classmethod
    def one_line(cls, v: str) -> str:
        return " ".join((v or "").split())

    @field_validator("notes")
    @classmethod
    def text(cls, v: str) -> str:
        return clean_text(v or "", multiline=True)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("Give the time with its time zone")
        return v.astimezone(timezone.utc) if v else v


class AppointmentOut(BaseModel):
    id: int
    kind: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    location: str
    notes: str
    ticket_id: int | None
    reference: str | None
    client: str | None
    assigned_to_id: int | None
    assigned_to: str | None
    remind_minutes: int
    remind_client: bool
    client_remind_minutes: int | None = None
    remind_owner: bool = False
    staff_reminded_at: datetime | None
    client_reminded_at: datetime | None
    owner_reminded_at: datetime | None = None
    reminder_note: str | None
    status: str


def out(a: Appointment) -> AppointmentOut:
    client = (a.customer.name if a.customer else None) or (a.ticket.lead_traveler_name if a.ticket else None)
    return AppointmentOut(id=a.id, kind=a.kind, title=a.title, starts_at=a.starts_at, ends_at=a.ends_at, location=a.location,
                          notes=a.notes, ticket_id=a.ticket_id, reference=a.ticket.reference if a.ticket else None,
                          client=client, assigned_to_id=a.assigned_to_id,
                          assigned_to=a.assigned_to.full_name if a.assigned_to else None, remind_minutes=a.remind_minutes,
                          remind_client=a.remind_client, client_remind_minutes=a.client_remind_minutes,
                          remind_owner=a.remind_owner, staff_reminded_at=a.staff_reminded_at,
                          client_reminded_at=a.client_reminded_at, owner_reminded_at=a.owner_reminded_at,
                          reminder_note=a.reminder_note, status=a.status)


def _apply(db: Session, me: User, a: Appointment, body: AppointmentIn) -> None:
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(422, "The end is before the start")
    ticket = None
    if body.ticket_id is not None:
        ticket = db.get(Ticket, body.ticket_id)
        if ticket is None or ticket.company_id != me.company_id:
            raise HTTPException(404, "Ticket not found")
    if body.assigned_to_id is not None:
        person = db.get(User, body.assigned_to_id)
        if person is None or person.company_id != me.company_id or person.partner_id is not None or not person.is_active:
            raise HTTPException(404, "Team member not found")
    timing_changed = (a.starts_at is None or a.starts_at != body.starts_at or a.remind_minutes != body.remind_minutes
                      or a.client_remind_minutes != body.client_remind_minutes)
    for k, v in body.model_dump().items():
        if k == "assigned_to_id" and "assigned_to_id" not in body.model_fields_set:
            continue  # not given: keep who is in charge
        setattr(a, k, v)
    a.customer_id = ticket.customer_id if ticket else None
    if timing_changed:  # a moved appointment is reminded again
        a.staff_reminded_at = a.client_reminded_at = a.owner_reminded_at = None
        a.reminder_note = None


@router.get("")
def calendar(start: date | None = None, end: date | None = None, mine: bool = False, me: User = Depends(viewer),
             db: Session = Depends(get_db)):
    start = start or local_today().replace(day=1)
    end = end or start + timedelta(days=41)
    if end < start or (end - start).days > 120:
        raise HTTPException(422, "Choose a period of up to 120 days")
    data = svc.items(db, me.company_id, start, end, me.id if mine else None)
    return {"appointments": [out(a) for a in data["appointments"]], "trips": data["trips"]}


@router.post("", response_model=AppointmentOut, status_code=201)
def create(body: AppointmentIn, me: User = Depends(editor), db: Session = Depends(get_db)):
    a = Appointment(company_id=me.company_id, created_by=me.full_name, assigned_to_id=me.id)
    a.starts_at = None  # type: ignore[assignment]
    _apply(db, me, a, body)
    svc.apply_defaults(me.company, a, body.model_fields_set)
    if a.assigned_to_id is None:
        a.assigned_to_id = me.id
    db.add(a)
    db.commit()
    db.refresh(a)
    return out(a)


def _get(db: Session, me: User, appointment_id: int) -> Appointment:
    a = db.get(Appointment, appointment_id)
    if a is None or a.company_id != me.company_id:
        raise HTTPException(404, "Appointment not found")
    return a


@router.put("/{appointment_id}", response_model=AppointmentOut)
def update(appointment_id: int, body: AppointmentIn, me: User = Depends(editor), db: Session = Depends(get_db)):
    a = _get(db, me, appointment_id)
    _apply(db, me, a, body)
    db.commit()
    db.refresh(a)
    return out(a)


@router.delete("/{appointment_id}", status_code=204)
def delete(appointment_id: int, me: User = Depends(editor), db: Session = Depends(get_db)):
    db.delete(_get(db, me, appointment_id))
    db.commit()


class TemplateIn(BaseModel):
    name: str = Field(default="", max_length=120, pattern=r"^[a-z0-9_]*$")
    language: str = Field(default="en", max_length=10, pattern=r"^[a-z]{2}(_[A-Z]{2})?$")


@router.get("/settings/template", response_model=TemplateIn)
def get_template(me: User = Depends(viewer)):
    return TemplateIn.model_validate(me.company.reminder_template or {})


@router.put("/settings/template", response_model=TemplateIn)
def save_template(body: TemplateIn, me: User = Depends(require_permission("settings.manage")), db: Session = Depends(get_db)):
    require_addon(me.company, "calendar")
    me.company.reminder_template = body.model_dump() if body.name else None
    audit(db, me, "reminder_template.saved", target=body.name or "none")
    db.commit()
    return body


class ReminderSettingsIn(BaseModel):
    staff_minutes: int = Field(ge=0, le=7 * 24 * 60)
    client_minutes: int = Field(ge=0, le=7 * 24 * 60)
    remind_client: bool
    remind_owner: bool


@router.get("/settings/reminders", response_model=ReminderSettingsIn)
def get_reminders(me: User = Depends(viewer)):
    return ReminderSettingsIn.model_validate(svc.settings_of(me.company))


@router.put("/settings/reminders", response_model=ReminderSettingsIn)
def save_reminders(body: ReminderSettingsIn, me: User = Depends(require_permission("settings.manage")),
                   db: Session = Depends(get_db)):
    """When new appointments remind the employee, the client and the company admins (each appointment can differ)."""
    require_addon(me.company, "calendar")
    me.company.calendar_settings = body.model_dump()
    audit(db, me, "calendar.reminders", detail=f"team {body.staff_minutes} min, client {body.client_minutes} min")
    db.commit()
    return body
