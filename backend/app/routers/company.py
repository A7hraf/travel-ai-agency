"""The logged-in employee's company: settings and dashboard."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.health import check_ai
from ..branding import Branding, BrandingUpdate, apply_update, get_branding
from ..database import get_db
from ..deps import get_company_user, require_permission
from ..models import (
    Channel,
    Company,
    Conversation,
    ConversationStatus,
    Ticket,
    TicketStatus,
    TravelPackage,
    User,
)
from ..permissions import effective_permissions
from ..ratelimit import limiter
from ..schemas import (
    AICheckOut,
    AnalyticsOut,
    CompanySettingsOut,
    CompanySettingsUpdate,
    DailyPoint,
    DashboardOut,
    FunnelOut,
    TopPackage,
    WhatsAppStatusOut,
    WhatsAppTestMessageIn,
    WhatsAppTestMessageOut,
    WhatsAppTestOut,
)
from ..serializers import OPEN_TICKET_STATUSES, company_settings_out
from ..services import whatsapp as whatsapp_service
from ..services.users import seats_used
from ..timeutil import days_back, local_date
from .media import media_belongs_to

router = APIRouter(prefix="/api", tags=["company"])


@router.get("/company", response_model=CompanySettingsOut)
def get_company(me: User = Depends(get_company_user)):
    return company_settings_out(me.company, can_manage="settings.manage" in effective_permissions(me))


@router.patch("/company", response_model=CompanySettingsOut)
def update_company(body: CompanySettingsUpdate, me: User = Depends(require_permission("settings.manage")),
                   db: Session = Depends(get_db)):
    company = me.company
    data = body.model_dump(exclude_unset=True)
    # These columns can't be empty in the database: null means "leave as it is".
    for key in NOT_NULL_FIELDS:
        if key in data and data[key] is None:
            del data[key]

    for secret in ("whatsapp_access_token", "whatsapp_app_secret"):
        if secret in data:
            value = (data.pop(secret) or "").strip()
            setattr(company, secret, value or None)
    if "whatsapp_phone_number_id" in data:
        number_id = (data.pop("whatsapp_phone_number_id") or "").strip() or None
        if number_id and number_id != company.whatsapp_phone_number_id:
            _check_number_is_ours(db, company, number_id)
        company.whatsapp_phone_number_id = number_id
    if data.get("currency"):
        data["currency"] = data["currency"].upper()
    for key, value in data.items():
        if key in ("ai_agent_name", "currency") and not value:
            continue  # required fields can't be blanked
        setattr(company, key, value)
    db.commit()
    return company_settings_out(company, can_manage=True)


NOT_NULL_FIELDS = ("currency", "ai_agent_name", "ai_instructions", "knowledge_base")


def _check_number_is_ours(db: Session, company: Company, number_id: str) -> None:
    """A company may only connect a WhatsApp number its own Meta access token can use.

    Otherwise anybody could type in another company's phone number ID and receive its
    customers' messages. (The platform owner assigns numbers on the shared app.)
    """
    taken = db.scalar(select(Company.id).where(Company.whatsapp_phone_number_id == number_id, Company.id != company.id))
    if taken:
        raise HTTPException(409, "This WhatsApp number is already connected to another company")
    if not company.whatsapp_access_token:
        raise HTTPException(400, "Add your WhatsApp access token to connect a phone number ID")
    if not whatsapp_service.verify_phone_number(number_id, company.whatsapp_access_token):
        raise HTTPException(400, "WhatsApp did not confirm this phone number ID for your access token. "
                                 "Check both in your Meta app and try again.")


@router.get("/company/whatsapp", response_model=WhatsAppStatusOut)
def whatsapp_status(me: User = Depends(require_permission("settings.manage"))):
    """Connection status for the "Connect WhatsApp" steps (webhook address and verify token included)."""
    return whatsapp_service.connection_status(me.company)


@router.post("/company/whatsapp/test", response_model=WhatsAppTestOut)
def whatsapp_test(me: User = Depends(require_permission("settings.manage"))):
    """Asks Meta whether the saved access token may use the saved phone number ID."""
    return whatsapp_service.run_connection_test(me.company, me.id)


@router.post("/company/whatsapp/test-message", response_model=WhatsAppTestMessageOut)
def whatsapp_test_message(body: WhatsAppTestMessageIn, me: User = Depends(require_permission("settings.manage"))):
    return whatsapp_service.send_test_whatsapp(me.company, me.id, body.phone)


@router.post("/company/ai-check", response_model=AICheckOut)
def company_ai_check(me: User = Depends(require_permission("settings.manage"))):
    limiter.check(f"ai-check:{me.id}", 6, "Please wait a minute before testing again")
    return check_ai()


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(me: User = Depends(require_permission("reports.view")), db: Session = Depends(get_db)):
    cid = me.company_id

    def grouped(model, column) -> dict[str, int]:
        rows = db.execute(select(column, func.count(model.id)).where(model.company_id == cid).group_by(column))
        return {str(k): v for k, v in rows}

    currency = me.company.currency

    def total(statuses) -> float:
        # Amounts in other currencies are never added to the company currency (see other_currencies).
        value = db.scalar(
            select(func.coalesce(func.sum(Ticket.total_price), 0)).where(
                Ticket.company_id == cid, Ticket.status.in_(statuses), Ticket.currency == currency
            )
        )
        return float(value or 0)

    others = db.execute(
        select(Ticket.currency, func.sum(Ticket.total_price)).where(
            Ticket.company_id == cid, Ticket.currency != currency, Ticket.status != TicketStatus.CANCELLED
        ).group_by(Ticket.currency)
    ).all()

    return DashboardOut(
        conversations_by_status=grouped(Conversation, Conversation.status),
        tickets_by_status=grouped(Ticket, Ticket.status),
        pipeline_value=total(OPEN_TICKET_STATUSES),
        confirmed_value=total([TicketStatus.CONFIRMED]),
        currency=currency,
        other_currencies={str(cur): round(float(v or 0), 3) for cur, v in others},
        packages_active=db.scalar(
            select(func.count(TravelPackage.id)).where(TravelPackage.company_id == cid, TravelPackage.is_active)
        ) or 0,
        users=seats_used(db, cid),
        max_users=me.company.max_users,
        conversations_waiting=db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.company_id == cid,
                Conversation.status == ConversationStatus.HUMAN,
                Conversation.assigned_to_id.is_(None),
            )
        ) or 0,
        my_open_tickets=db.scalar(
            select(func.count(Ticket.id)).where(
                Ticket.company_id == cid, Ticket.assigned_to_id == me.id, Ticket.status.in_(OPEN_TICKET_STATUSES)
            )
        ) or 0,
    )


@router.get("/company/branding", response_model=Branding)
def read_branding(me: User = Depends(require_permission("settings.manage"))):
    return get_branding(me.company)


@router.patch("/company/branding", response_model=Branding)
def update_branding(body: BrandingUpdate, me: User = Depends(require_permission("settings.manage")),
                    db: Session = Depends(get_db)):
    """The company admin edits the customer page; dashboard colours stay with the platform owner."""
    for url in body.image_urls():
        if not media_belongs_to(db, url, me.company_id):
            raise HTTPException(400, "Use an image uploaded by your company")
    branding = apply_update(me.company, body, allow_dashboard=False)
    db.commit()
    return branding


PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)


@router.get("/dashboard/analytics", response_model=AnalyticsOut)
def analytics(days: int = 30, me: User = Depends(require_permission("reports.view")), db: Session = Depends(get_db)):
    """Daily activity, sales funnel and best-selling packages of the last `days` days."""
    days = max(7, min(days, 365))
    cid = me.company_id
    currency = me.company.currency
    # Days are the agency's local days (Oman), and every number covers exactly the days shown.
    first_day, since = days_back(days)

    convs = db.execute(
        select(Conversation.id, Conversation.channel, Conversation.created_at, Conversation.was_handed_over)
        .where(Conversation.company_id == cid, Conversation.created_at >= since)
    ).all()
    tickets = db.execute(
        select(Ticket.conversation_id, Ticket.created_at, Ticket.total_price, Ticket.status, Ticket.package_title)
        .where(Ticket.company_id == cid, Ticket.created_at >= since, Ticket.currency == currency)
    ).all()

    daily: dict[date, dict] = {
        first_day + timedelta(days=i): {"web": 0, "whatsapp": 0, "bookings": 0, "booked_value": 0.0}
        for i in range(days)
    }
    for _, channel, created, _ in convs:
        day = daily.get(local_date(created))
        if day is not None:
            day["whatsapp" if channel == Channel.WHATSAPP else "web"] += 1
    packages: dict[str, dict] = {}
    booked_conversations = set()
    paid_conversations = set()
    booked_value = paid_value = 0.0
    for conversation_id, created, total, status, title in tickets:
        if status == TicketStatus.CANCELLED:
            continue
        value = float(total)
        booked_value += value
        if status in PAID:
            paid_value += value
            paid_conversations.add(conversation_id)
        booked_conversations.add(conversation_id)
        day = daily.get(local_date(created))
        if day is not None:
            day["bookings"] += 1
            day["booked_value"] += value
        entry = packages.setdefault(title, {"bookings": 0, "value": 0.0})
        entry["bookings"] += 1
        entry["value"] += value

    conversation_ids = {c[0] for c in convs}
    handed = sum(1 for c in convs if c[3])
    top = sorted(packages.items(), key=lambda kv: (-kv[1]["value"], kv[0]))[:5]
    return AnalyticsOut(
        days=days,
        currency=currency,
        daily=[DailyPoint(date=d.isoformat(), **v) for d, v in sorted(daily.items())],
        funnel=FunnelOut(
            conversations=len(convs),
            with_booking=len(booked_conversations & conversation_ids),
            paid_or_confirmed=len(paid_conversations & conversation_ids),
        ),
        top_packages=[TopPackage(title=t, bookings=v["bookings"], value=round(v["value"], 3)) for t, v in top],
        handled_by_ai=len(convs) - handed,
        handed_to_team=handed,
        booked_value=round(booked_value, 3),
        paid_value=round(paid_value, 3),
    )

