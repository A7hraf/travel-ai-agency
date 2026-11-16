"""The company calendar: appointments (meetings, airport pick-ups, calls…) and the trips' departures and returns,
with reminders on WhatsApp to the staff member in charge and, when asked, to the client.

WhatsApp delivers a free message only within 24 hours of the person's last message to the company. Outside it,
a reminder needs the company's message template approved by Meta; without one the reminder is noted as not sent
(the calendar still shows it).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..addons import has_addon
from ..language import Bi, pick
from ..models import (
    Appointment, Channel, Company, CompanyStatus, Conversation, Customer, Ticket, TicketStatus as T, utcnow,
)
from ..timeutil import business_tz, start_of_local_day

log = logging.getLogger(__name__)

TRIP_STATUSES = (T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING, T.CONFIRMED, T.COMPLETED)
WINDOW = timedelta(hours=24)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_text(moment: datetime) -> str:
    return _aware(moment).astimezone(business_tz()).strftime("%a %d %b %Y, %H:%M")


def items(db: Session, company_id: int, start: date, end: date, user_id: int | None = None) -> dict:
    """Appointments between two local days, and the trips leaving or coming back."""
    lo, hi = start_of_local_day(start), start_of_local_day(end + timedelta(days=1))
    stmt = (select(Appointment).where(Appointment.company_id == company_id, Appointment.starts_at >= lo,
                                      Appointment.starts_at < hi)
            .options(selectinload(Appointment.ticket), selectinload(Appointment.customer),
                     selectinload(Appointment.assigned_to)).order_by(Appointment.starts_at))
    if user_id is not None:
        stmt = stmt.where(Appointment.assigned_to_id == user_id)
    trips = []
    s, e = start.isoformat(), end.isoformat()
    tstmt = select(Ticket).where(Ticket.company_id == company_id, Ticket.status.in_(TRIP_STATUSES))
    if user_id is not None:
        tstmt = tstmt.where(Ticket.assigned_to_id == user_id)
    for t in db.scalars(tstmt.where(((Ticket.departure_date >= s) & (Ticket.departure_date <= e))
                                    | ((Ticket.return_date >= s) & (Ticket.return_date <= e)))).all():
        who = t.lead_traveler_name or (t.customer.name if t.customer else "") or ""
        for kind, day in (("departure", t.departure_date), ("return", t.return_date)):
            if day and s <= day <= e:
                trips.append({"kind": kind, "date": day, "ticket_id": t.id, "reference": t.reference, "client": who,
                              "destination": t.destination or t.package_title, "status": t.status})
    return {"appointments": list(db.scalars(stmt).all()), "trips": sorted(trips, key=lambda x: x["date"])}


# --- Reminders ----------------------------------------------------------------------------------------

def _window_open(db: Session, company_id: int, wa_id: str) -> bool:
    last = db.scalar(select(Conversation.last_customer_message_at).join(Customer, Customer.id == Conversation.customer_id)
                     .where(Conversation.company_id == company_id, Conversation.channel == Channel.WHATSAPP,
                            Customer.whatsapp_id == wa_id).order_by(Conversation.last_customer_message_at.desc()).limit(1))
    return bool(last) and utcnow() - _aware(last) < WINDOW


def deliver(db: Session, company: Company, wa_id: str, text: str) -> str | None:
    """Sends `text` on WhatsApp. Returns None when sent, or why it could not be."""
    from .whatsapp import WhatsAppError, get_whatsapp_sender  # noqa: PLC0415

    if not company.whatsapp_phone_number_id:
        return "WhatsApp is not connected"
    sender = get_whatsapp_sender()
    tpl = company.reminder_template if isinstance(company.reminder_template, dict) else {}
    try:
        if _window_open(db, company.id, wa_id):
            sender.send_text(company, wa_id, text)
        elif tpl.get("name"):
            sender.send_template(company, wa_id, tpl["name"], tpl.get("language") or "en", [text])
        else:
            return "Outside WhatsApp's 24-hour window and no reminder template is set"
    except WhatsAppError as exc:
        log.info("Reminder not delivered for company %s: %s", company.id, exc)
        return "WhatsApp did not accept the message"
    return None


DEFAULTS = {"staff_minutes": 60, "client_minutes": 24 * 60, "remind_client": False, "remind_owner": False}


def settings_of(company: Company) -> dict:
    own = company.calendar_settings if isinstance(company.calendar_settings, dict) else {}
    return {**DEFAULTS, **{k: v for k, v in own.items() if k in DEFAULTS}}


def apply_defaults(company: Company, a: Appointment, given: set[str]) -> None:
    """A new appointment takes the company's reminder settings for what the employee didn't choose."""
    s = settings_of(company)
    if "remind_minutes" not in given:
        a.remind_minutes = s["staff_minutes"]
    if "client_remind_minutes" not in given:
        a.client_remind_minutes = s["client_minutes"]
    if "remind_client" not in given:
        a.remind_client = s["remind_client"]
    if "remind_owner" not in given:
        a.remind_owner = s["remind_owner"]


def send_reminders(db: Session, now: datetime | None = None) -> int:
    """Reminders due now (each appointment's own notice before it starts). Each is tried once."""
    from .whatsapp import normalize_phone  # noqa: PLC0415

    now = now or utcnow()
    due = db.scalars(select(Appointment).where(
        Appointment.status == "planned", Appointment.starts_at > now, Appointment.starts_at <= now + timedelta(days=8),
        (Appointment.staff_reminded_at.is_(None))
        | ((Appointment.remind_client.is_(True)) & Appointment.client_reminded_at.is_(None))
        | ((Appointment.remind_owner.is_(True)) & Appointment.owner_reminded_at.is_(None)))
        .options(selectinload(Appointment.assigned_to), selectinload(Appointment.customer), selectinload(Appointment.ticket))).all()
    sent = 0
    for a in due:
        starts = _aware(a.starts_at)
        staff_due = starts - timedelta(minutes=a.remind_minutes) <= now
        client_due = starts - timedelta(minutes=a.client_remind_minutes if a.client_remind_minutes is not None else a.remind_minutes) <= now
        if not staff_due and not client_due:
            continue
        company = db.get(Company, a.company_id)
        if company is None or company.status != CompanyStatus.ACTIVE or not has_addon(company, "calendar"):
            continue
        notes = [n for n in (a.reminder_note or "").split("; ") if n]
        when = local_text(a.starts_at)
        ref = f" ({a.ticket.reference})" if a.ticket else ""
        if staff_due and a.remind_owner and a.owner_reminded_at is None:
            a.owner_reminded_at = now
            from ..models import Role, User  # noqa: PLC0415

            for owner in db.scalars(select(User).where(User.company_id == company.id, User.role == Role.COMPANY_ADMIN,
                                                       User.is_active.is_(True))).all():
                number = normalize_phone(owner.whatsapp_number or "")
                if number and owner.id != a.assigned_to_id:
                    sent += deliver(db, company, number, f"⏰ {company.name}: {a.title}{ref} · {when}"
                                    + (f" · {a.location}" if a.location else "")) is None
        if staff_due and a.staff_reminded_at is None:
            if a.assigned_to is not None and a.ticket is not None:
                from .notifications import to_user  # noqa: PLC0415

                to_user(db, a.assigned_to, a.ticket, "appointment_soon", title=a.title, when=when)
            a.staff_reminded_at = now
            number = normalize_phone(a.assigned_to.whatsapp_number or "") if a.assigned_to else None
            if number:
                who = (a.customer.name if a.customer else None) or (a.ticket.lead_traveler_name if a.ticket else None)
                text = (f"⏰ {company.name}: {a.title}{ref} · {when}" + (f" · {a.location}" if a.location else "")
                        + (f" · {who}" if who else ""))
                why = deliver(db, company, number, text)
                if why:
                    notes.append(f"Team: {why}")
                else:
                    sent += 1
            else:
                notes.append("Team: no WhatsApp number for the person in charge")
        if client_due and a.remind_client and a.client_reminded_at is None:
            a.client_reminded_at = now
            wa_id = a.customer.whatsapp_id if a.customer else None
            if not has_addon(company, "calendar_client_reminders"):
                notes.append("Client: client reminders are not switched on")
            elif not wa_id:
                notes.append("Client: no WhatsApp number")
            else:
                place = f" · {a.location}" if a.location else ""
                lang = db.scalar(select(Conversation.language).where(Conversation.customer_id == a.customer_id,
                                                                     Conversation.language.is_not(None))
                                 .order_by(Conversation.last_message_at.desc()).limit(1))
                text = pick(Bi(f"⏰ Reminder from {company.name}: {a.title}{ref} · {when}{place}",
                               f"⏰ تذكير من {company.name}: {a.title}{ref} · {when}{place}"), lang)
                why = deliver(db, company, wa_id, text)
                if why:
                    notes.append(f"Client: {why}")
                else:
                    sent += 1
        a.reminder_note = "; ".join(dict.fromkeys(notes))[:300] or None
        db.commit()
    return sent
