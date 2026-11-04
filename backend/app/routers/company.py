"""The logged-in employee's company: settings and dashboard."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.health import check_ai, for_company
from ..audit import audit
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
    utcnow,
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
    InstagramStatusOut,
    InstagramTestOut,
    TopPackage,
    WhatsAppStatusOut,
    WhatsAppTestMessageIn,
    WhatsAppTestMessageOut,
    WhatsAppTestOut,
)
from ..serializers import OPEN_TICKET_STATUSES, company_settings_out
from ..services import instagram as instagram_service
from ..services import plans
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
    before = _channel_state(company)  # activity log
    # These columns can't be empty in the database: null means "leave as it is".
    for key in NOT_NULL_FIELDS:
        if key in data and data[key] is None:
            del data[key]

    for secret in ("whatsapp_access_token", "whatsapp_app_secret", "instagram_access_token", "instagram_app_secret"):
        if secret in data:
            value = (data.pop(secret) or "").strip()
            setattr(company, secret, value or None)
            if secret == "instagram_access_token":
                company.instagram_token_refreshed_at = utcnow() if value else None
    if "whatsapp_phone_number_id" in data:
        number_id = (data.pop("whatsapp_phone_number_id") or "").strip() or None
        if number_id and number_id != company.whatsapp_phone_number_id:
            plans.require_channel(db, company.id, "whatsapp")
            _check_number_is_ours(db, company, number_id)
        company.whatsapp_phone_number_id = number_id
    if (company.instagram_access_token and "instagram_access_token" in body.model_fields_set) or \
            (data.get("instagram_account_id") or "").strip() not in ("", company.instagram_account_id or ""):
        plans.require_channel(db, company.id, "instagram")  # before anything is saved
    if "instagram_access_token" in body.model_fields_set and company.instagram_access_token \
            and not company.instagram_account_id and not (data.get("instagram_account_id") or "").strip():
        _detect_instagram_account(db, company)
    if "instagram_account_id" in data:
        account_id = (data.pop("instagram_account_id") or "").strip() or None
        if account_id and account_id != company.instagram_account_id:
            company.instagram_username = _check_instagram_is_ours(db, company, account_id)
        elif not account_id:
            company.instagram_username = None
        company.instagram_account_id = account_id
    if data.get("currency"):
        data["currency"] = data["currency"].upper()
    for key, value in data.items():
        if key in ("ai_agent_name", "currency") and not value:
            continue  # required fields can't be blanked
        setattr(company, key, value)
    _audit_settings(db, me, before, _channel_state(company), set(body.model_fields_set))
    try:
        db.commit()
    except IntegrityError as exc:  # the same number or account saved by another company at the same moment
        db.rollback()
        raise HTTPException(409, "This WhatsApp number or Instagram account is already connected to another "
                                 "company") from exc
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


def _detect_instagram_account(db: Session, company: Company) -> None:
    """A new token and no account yet: connect the account the token belongs to, so the company does
    not have to look up its account ID. Nothing happens when Instagram can't tell (Test connection
    then explains why) or when that account is already another company's."""
    found = instagram_service.check_account(None, company.instagram_access_token)
    user_id = found.get("user_id")
    if found["result"] != "account_missing" or not user_id:
        return
    if db.scalar(select(Company.id).where(Company.instagram_account_id == user_id, Company.id != company.id)):
        return
    company.instagram_account_id = user_id
    company.instagram_username = str(found.get("username") or "")[:100] or None


def _check_instagram_is_ours(db: Session, company: Company, account_id: str) -> str | None:
    """A company may only connect an Instagram account its own access token belongs to (same rule as
    WhatsApp numbers), so nobody can receive another company's Instagram messages. Returns the username."""
    taken = db.scalar(select(Company.id).where(Company.instagram_account_id == account_id, Company.id != company.id))
    if taken:
        raise HTTPException(409, "This Instagram account is already connected to another company")
    if not company.instagram_access_token:
        raise HTTPException(400, "Add your Instagram access token to connect an Instagram account")
    confirmed = instagram_service.verify_account(account_id, company.instagram_access_token)
    if confirmed is None:
        raise HTTPException(400, "Instagram did not confirm this account ID for your access token. "
                                 "Use Test connection to see the exact problem.")
    username = confirmed.get("username")
    return str(username)[:100] if username else None


@router.get("/company/instagram", response_model=InstagramStatusOut)
def instagram_status(me: User = Depends(require_permission("settings.manage"))):
    """Connection status for the "Connect Instagram" steps (webhook address and verify token included)."""
    return instagram_service.connection_status(me.company)


@router.post("/company/instagram/test", response_model=InstagramTestOut)
def instagram_test(me: User = Depends(require_permission("settings.manage")), db: Session = Depends(get_db)):
    """Asks Instagram which account the saved access token belongs to, and whether it is the saved one."""
    result = instagram_service.run_connection_test(me.company, me.id)
    db.commit()
    return result


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
    return for_company(check_ai())


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
    """The company admin edits the customer page; dashboard colours stay with the platform owner.
    The plan decides whether the page editor is included and whether "Powered by" can be hidden."""
    ent = plans.require_page_editor(db, me.company_id)
    for url in body.image_urls():
        if not media_belongs_to(db, url, me.company_id):
            raise HTTPException(400, "Use an image uploaded by your company")
    branding = apply_update(me.company, body, allow_dashboard=False, allow_powered_by=ent.remove_powered_by)
    audit(db, me, "branding.saved")
    db.commit()
    return branding


PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED)
# The dashboard's conversations-per-day series of each channel.
CHANNEL_SERIES = {Channel.WHATSAPP: "whatsapp", Channel.INSTAGRAM: "instagram"}


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
        first_day + timedelta(days=i): {"web": 0, "whatsapp": 0, "instagram": 0, "bookings": 0, "booked_value": 0.0}
        for i in range(days)
    }
    for _, channel, created, _ in convs:
        day = daily.get(local_date(created))
        if day is not None:
            day[CHANNEL_SERIES.get(channel, "web")] += 1
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


# --- Activity log of the settings page (business tools) -----------------------------------------

_AI_FIELDS = {"ai_agent_name", "ai_welcome_message", "ai_welcome_message_ar", "ai_instructions", "knowledge_base"}
_WA_SECRETS = {"whatsapp_access_token", "whatsapp_app_secret"}
_IG_SECRETS = {"instagram_access_token", "instagram_app_secret"}


def _channel_state(company: Company) -> dict:
    return {"wa": company.whatsapp_phone_number_id, "wa_number": company.whatsapp_display_number,
            "ig": company.instagram_account_id, "ig_user": company.instagram_username}


def _audit_settings(db: Session, me: User, before: dict, after: dict, fields: set[str]) -> None:
    """Connections and changed field names only: never the value of a token or secret."""
    if after["wa"] != before["wa"]:
        if after["wa"]:
            audit(db, me, "whatsapp.connected", target=after["wa_number"] or after["wa"])
        else:
            audit(db, me, "whatsapp.disconnected", target=before["wa_number"] or before["wa"])
    if fields & _WA_SECRETS:
        audit(db, me, "whatsapp.credentials", detail=", ".join(sorted(f.replace("whatsapp_", "").replace("_", " ")
                                                                       for f in fields & _WA_SECRETS)))
    if after["ig"] != before["ig"]:
        if after["ig"]:
            audit(db, me, "instagram.connected", target=f"@{after['ig_user']}" if after["ig_user"] else after["ig"])
        else:
            audit(db, me, "instagram.disconnected",
                  target=f"@{before['ig_user']}" if before["ig_user"] else before["ig"])
    if fields & _IG_SECRETS:
        audit(db, me, "instagram.credentials", detail=", ".join(sorted(f.replace("instagram_", "").replace("_", " ")
                                                                        for f in fields & _IG_SECRETS)))
    if fields & _AI_FIELDS:
        audit(db, me, "ai.knowledge", detail=", ".join(sorted(f.replace("_", " ") for f in fields & _AI_FIELDS)))
    rest = fields - _AI_FIELDS - _WA_SECRETS - _IG_SECRETS - {"whatsapp_phone_number_id", "instagram_account_id"}
    if rest:
        audit(db, me, "settings.saved", detail=", ".join(sorted(f.replace("_", " ") for f in rest)))

