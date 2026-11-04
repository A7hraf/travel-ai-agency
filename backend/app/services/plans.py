"""Subscription plans: the catalogue, each company's subscription, payments and the plan checks.

Model:
* ``Plan`` holds prices (OMR, 3 decimals) and limits; None means unlimited.
* ``Subscription`` (one per company) holds the plan, billing cycle, status and the paid period.
  Its dates are the agency's local days and are valid through the end date.
* ``Company.max_users`` stays the account limit every account check reads (services/users.py). It
  follows the plan's staff limit unless the owner set a custom limit for the company
  (``Subscription.max_users_custom``); this module keeps it in sync when plans change.

The status the owner stores (trial, active, past_due, expired, cancelled) is combined with today's
date into an access *state*: after the end date a paid plan has a grace period (platform setting,
7 days by default) in which everything keeps working; after it the AI and the customer page pause
and staff see a renewal banner. Staff keep their dashboard and nothing is ever deleted.
A company without a subscription row (never the case after the migration) is not limited at all.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import (
    BillingCycle,
    Company,
    Conversation,
    Plan,
    PlatformSetting,
    Subscription,
    SubscriptionStatus,
    TravelPackage,
    utcnow,
)
from ..timeutil import local_today, start_of_local_day

log = logging.getLogger(__name__)

GRACE_SETTING_KEY = "subscription_grace_days"
DEFAULT_GRACE_DAYS = 7
TRIAL_ENDING_DAYS = 7  # the staff banner warns this many days before a trial ends

STATE_PAUSED = "expired"
PAYING_STATES = ("active", "past_due", "grace")

THOUSANDTH = Decimal("0.001")


def today() -> date:
    """The agency's local date (tests move it with monkeypatch)."""
    return local_today()


def omr(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(THOUSANDTH, rounding=ROUND_HALF_UP)


def add_months(day: date, months: int) -> date:
    """Same day `months` later; the 31st becomes the month's last day."""
    month0 = day.month - 1 + months
    year, month = day.year + month0 // 12, month0 % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def cycle_months(cycle: str) -> int:
    return 12 if cycle == BillingCycle.YEARLY else 1


# --- Default catalogue ----------------------------------------------------------------------------

# Placeholder prices in OMR: the platform owner edits them on the Plans page.
DEFAULT_PLANS = [
    dict(name="Starter", name_ar="البداية", sort_order=1, price_monthly=Decimal("15.000"),
         price_yearly=Decimal("150.000"), trial_days=14, max_users=3, max_packages=20, max_ai_conversations=300,
         allow_whatsapp=True, allow_instagram=False, allow_page_editor=False, allow_remove_powered_by=False,
         priority_support=False,
         description="For a small agency starting online: your customer page, the AI consultant and WhatsApp.",
         description_ar="لوكالة صغيرة تبدأ على الإنترنت: صفحة عملائك ومستشار السفر الذكي وواتساب.",
         features=["Customer page with AI chat", "WhatsApp channel", "Booking tickets", "3 staff accounts"],
         features_ar=["صفحة عملاء مع محادثة ذكية", "قناة واتساب", "تذاكر الحجز", "3 حسابات للموظفين"]),
    dict(name="Business", name_ar="الأعمال", sort_order=2, price_monthly=Decimal("35.000"),
         price_yearly=Decimal("350.000"), trial_days=14, max_users=10, max_packages=100, max_ai_conversations=1500,
         allow_whatsapp=True, allow_instagram=True, allow_page_editor=True, allow_remove_powered_by=False,
         priority_support=False,
         description="For a growing team: WhatsApp and Instagram, your own page design and more AI conversations.",
         description_ar="لفريق ينمو: واتساب وإنستغرام وتصميم صفحتك الخاص ومحادثات ذكية أكثر.",
         features=["Everything in Starter", "Instagram Direct", "Customer page editor", "10 staff accounts"],
         features_ar=["كل ما في باقة البداية", "رسائل إنستغرام المباشرة", "محرر صفحة العملاء", "10 حسابات للموظفين"]),
    dict(name="Pro", name_ar="الاحترافية", sort_order=3, price_monthly=Decimal("75.000"),
         price_yearly=Decimal("750.000"), trial_days=14, max_users=25, max_packages=None, max_ai_conversations=5000,
         allow_whatsapp=True, allow_instagram=True, allow_page_editor=True, allow_remove_powered_by=True,
         priority_support=True, is_default=True,
         description="For established agencies: unlimited packages, your own brand only and priority support.",
         description_ar="للوكالات الكبيرة: باقات سفر بلا حدود وعلامتك التجارية فقط ودعم ذو أولوية.",
         features=["Everything in Business", "Unlimited packages", "Hide \"Powered by Ghanjah\"", "Priority support",
                   "25 staff accounts"],
         features_ar=["كل ما في باقة الأعمال", "باقات سفر بلا حدود", "إخفاء \"بدعم من غنجة\"", "دعم ذو أولوية",
                      "25 حساباً للموظفين"]),
]

LEGACY_PLAN = dict(
    name="Legacy", name_ar="الباقة السابقة", sort_order=99, price_monthly=Decimal("0"), price_yearly=Decimal("0"),
    trial_days=0, max_users=10000, max_packages=None, max_ai_conversations=None, allow_whatsapp=True,
    allow_instagram=True, allow_page_editor=True, allow_remove_powered_by=True, priority_support=False,
    is_archived=True,
    description="Everything a company used before plans existed. Move the company to a real plan when you can.",
    description_ar="كل ما كانت الشركة تستخدمه قبل وجود الباقات. انقل الشركة إلى باقة حقيقية عندما تستطيع.",
    features=[], features_ar=[],
)


def ensure_default_plans(db: Session) -> None:
    """First start: three editable plans (Starter, Business, Pro)."""
    if db.scalar(select(func.count(Plan.id))):
        return
    for data in DEFAULT_PLANS:
        db.add(Plan(**data))
    db.flush()
    log.info("Created the default plans: %s", ", ".join(p["name"] for p in DEFAULT_PLANS))


def default_plan(db: Session) -> Plan | None:
    plan = db.scalar(select(Plan).where(Plan.is_default.is_(True), Plan.is_archived.is_(False)).limit(1))
    if plan is None:
        plan = db.scalar(select(Plan).where(Plan.is_archived.is_(False)).order_by(Plan.sort_order, Plan.id).limit(1))
    return plan


def _sync_max_users(company: Company, sub: Subscription, plan: Plan) -> None:
    if not sub.max_users_custom:
        company.max_users = plan.max_users


def start_subscription(db: Session, company: Company, plan: Plan | None = None, *,
                       custom_max_users: int | None = None, cycle: str = BillingCycle.MONTHLY,
                       trial: bool | None = None) -> Subscription | None:
    """The subscription of a new company: a trial of the plan when it has trial days, otherwise one
    active cycle. A given account limit is kept as the company's custom limit."""
    plan = plan or default_plan(db)
    if plan is None:
        return None
    start = today()
    use_trial = plan.trial_days > 0 if trial is None else trial
    sub = Subscription(
        company_id=company.id, plan_id=plan.id, billing_cycle=cycle,
        status=SubscriptionStatus.TRIAL if use_trial else SubscriptionStatus.ACTIVE,
        current_period_start=start,
        current_period_end=None if use_trial else add_months(start, cycle_months(cycle)) - timedelta(days=1),
        trial_end=start + timedelta(days=max(plan.trial_days, 1)) if use_trial else None,
        max_users_custom=custom_max_users is not None and custom_max_users != plan.max_users,
        notes="",
    )
    sub.plan = plan
    db.add(sub)
    if custom_max_users is not None:
        company.max_users = custom_max_users
    _sync_max_users(company, sub, plan)
    return sub


def ensure_subscription(db: Session, company: Company) -> Subscription | None:
    """Companies created outside the owner's form (demo companies) get the default plan."""
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company.id))
    if sub is None:
        sub = start_subscription(db, company, custom_max_users=company.max_users)
    return sub


# --- Backfill for companies that existed before plans --------------------------------------------


def _plan_fits(plan: Plan, usage: dict) -> bool:
    def within(limit, used) -> bool:
        return limit is None or used <= limit

    return (
        within(plan.max_users, usage["max_users"])
        and within(plan.max_packages, usage["packages"])
        and within(plan.max_ai_conversations, usage["ai_month"])
        and (plan.allow_whatsapp or not usage["whatsapp"])
        and (plan.allow_instagram or not usage["instagram"])
        and (plan.allow_page_editor or not usage["page_edited"])
        and (plan.allow_remove_powered_by or not usage["powered_by_hidden"])
    )


def backfill_subscriptions(db: Session) -> int:
    """Every company without a subscription gets one: status active until a year from today, on the
    cheapest plan that allows everything it already uses (its channels, design, packages, account
    limit), or on an archived "Legacy" plan with no limits. Nobody is locked out by the upgrade."""
    missing = db.scalars(
        select(Company).outerjoin(Subscription, Subscription.company_id == Company.id)
        .where(Subscription.id.is_(None)).order_by(Company.id)
    ).all()
    if not missing:
        return 0
    ensure_default_plans(db)
    plans = db.scalars(select(Plan).where(Plan.is_archived.is_(False))
                       .order_by(Plan.price_monthly, Plan.sort_order, Plan.id)).all()
    ids = [c.id for c in missing]
    packages = dict(db.execute(
        select(TravelPackage.company_id, func.count(TravelPackage.id))
        .where(TravelPackage.company_id.in_(ids), TravelPackage.is_active.is_(True)).group_by(TravelPackage.company_id)
    ).all())
    since = utcnow() - timedelta(days=31)
    chats = dict(db.execute(
        select(Conversation.company_id, func.count(Conversation.id))
        .where(Conversation.company_id.in_(ids), Conversation.created_at >= since).group_by(Conversation.company_id)
    ).all())
    legacy = None
    start = today()
    for company in missing:
        branding = company.branding if isinstance(company.branding, dict) else {}
        elements = branding.get("elements") if isinstance(branding.get("elements"), dict) else {}
        usage = {
            "max_users": company.max_users or 1,
            "packages": packages.get(company.id, 0),
            "ai_month": chats.get(company.id, 0),
            "whatsapp": bool(company.whatsapp_phone_number_id),
            "instagram": bool(company.instagram_account_id),
            "page_edited": bool(branding),
            "powered_by_hidden": elements.get("powered_by") is False,
        }
        plan = next((p for p in plans if _plan_fits(p, usage)), None)
        if plan is None:
            if legacy is None:
                legacy = db.scalar(select(Plan).where(Plan.name == LEGACY_PLAN["name"]).limit(1))
                if legacy is None:
                    legacy = Plan(**LEGACY_PLAN)
                    db.add(legacy)
                    db.flush()
            plan = legacy
        db.add(Subscription(
            company_id=company.id, plan_id=plan.id, billing_cycle=BillingCycle.YEARLY,
            status=SubscriptionStatus.ACTIVE, current_period_start=start,
            current_period_end=add_months(start, 12),
            # The account limit the owner had set stays exactly as it was.
            max_users_custom=company.max_users != plan.max_users,
            notes="Moved to plans automatically: check the plan and price.",
        ))
        log.info("Database upgrade: company %s gets the %s plan", company.id, plan.name)
    db.flush()
    return len(missing)


# --- Access state and entitlements ----------------------------------------------------------------


def grace_days(db: Session) -> int:
    row = db.get(PlatformSetting, GRACE_SETTING_KEY)
    try:
        return max(0, min(int(row.value), 365)) if row is not None and row.value else DEFAULT_GRACE_DAYS
    except ValueError:
        return DEFAULT_GRACE_DAYS


def period_end(sub: Subscription) -> date | None:
    return sub.trial_end if sub.status == SubscriptionStatus.TRIAL else sub.current_period_end


def access_state(sub: Subscription, on: date, grace: int) -> str:
    """trial, active, past_due, cancelled while the period runs; grace for a paid plan in its grace
    period; expired (the AI and the customer page pause) afterwards."""
    if sub.status == SubscriptionStatus.EXPIRED:
        return STATE_PAUSED
    end = period_end(sub)
    if end is None or on <= end:
        return sub.status
    if sub.status == SubscriptionStatus.CANCELLED:
        return STATE_PAUSED
    if on <= end + timedelta(days=grace):
        return "grace"
    return STATE_PAUSED


@dataclass
class Entitlements:
    has_plan: bool
    plan_id: int | None = None
    plan_name: str = ""
    plan_name_ar: str = ""
    max_users: int | None = None
    max_packages: int | None = None
    max_ai_conversations: int | None = None
    whatsapp: bool = True
    instagram: bool = True
    page_editor: bool = True
    remove_powered_by: bool = True
    priority_support: bool = False
    status: str = SubscriptionStatus.ACTIVE
    state: str = SubscriptionStatus.ACTIVE
    ends_on: date | None = None
    grace_until: date | None = None
    days_left: int | None = None

    @property
    def paused(self) -> bool:
        return self.state == STATE_PAUSED

    def allows_channel(self, channel: str) -> bool:
        return {"whatsapp": self.whatsapp, "instagram": self.instagram}.get(str(channel), True)


UNLIMITED = Entitlements(has_plan=False)


def entitlements_for(sub: Subscription | None, plan: Plan | None, grace: int, on: date | None = None,
                     max_users: int | None = None) -> Entitlements:
    if sub is None or plan is None:
        return UNLIMITED
    on = on or today()
    end = period_end(sub)
    state = access_state(sub, on, grace)
    return Entitlements(
        has_plan=True, plan_id=plan.id, plan_name=plan.name, plan_name_ar=plan.name_ar or "",
        max_users=max_users, max_packages=plan.max_packages, max_ai_conversations=plan.max_ai_conversations,
        whatsapp=plan.allow_whatsapp, instagram=plan.allow_instagram, page_editor=plan.allow_page_editor,
        remove_powered_by=plan.allow_remove_powered_by, priority_support=plan.priority_support,
        status=sub.status, state=state, ends_on=end,
        grace_until=end + timedelta(days=grace) if end and sub.status not in (
            SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED) else end,
        days_left=(end - on).days if end else None,
    )


def entitlements(db: Session, company_id: int) -> Entitlements:
    """What the company may use right now: one query for subscription and plan, one primary-key read."""
    row = db.execute(
        select(Subscription, Plan, Company.max_users)
        .join(Plan, Plan.id == Subscription.plan_id)
        .join(Company, Company.id == Subscription.company_id)
        .where(Subscription.company_id == company_id)
    ).first()
    if row is None:
        return UNLIMITED
    return entitlements_for(row[0], row[1], grace_days(db), max_users=row[2])


# --- Checks ---------------------------------------------------------------------------------------

CHANNEL_NAMES = {"whatsapp": "WhatsApp", "instagram": "Instagram"}


def require_channel(db: Session, company_id: int, channel: str) -> None:
    ent = entitlements(db, company_id)
    if not ent.allows_channel(channel):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"The {ent.plan_name} plan does not include {CHANNEL_NAMES[channel]}. "
                            "Upgrade the plan to connect it.")


def require_page_editor(db: Session, company_id: int) -> Entitlements:
    ent = entitlements(db, company_id)
    if not ent.page_editor:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"The {ent.plan_name} plan does not include the page editor. "
                            "Contact the platform to upgrade.")
    return ent


def active_packages(db: Session, company_id: int) -> int:
    return db.scalar(select(func.count(TravelPackage.id)).where(
        TravelPackage.company_id == company_id, TravelPackage.is_active.is_(True))) or 0


def check_package_limit(db: Session, company_id: int) -> None:
    """Called before a package is created or shown again (hidden packages don't count)."""
    ent = entitlements(db, company_id)
    if ent.max_packages is None:
        return
    used = active_packages(db, company_id)
    if used >= ent.max_packages:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Package limit reached ({used}/{ent.max_packages}) on the {ent.plan_name} plan. "
                            "Hide a package or contact the platform to upgrade.")


def month_start_utc(on: date | None = None):
    return start_of_local_day((on or today()).replace(day=1))


def ai_conversations_this_month(db: Session, company_id: int) -> int:
    return db.scalar(select(func.count(Conversation.id)).where(
        Conversation.company_id == company_id, Conversation.ai_started_at >= month_start_utc())) or 0


AI_LIMIT_REASON = "AI monthly conversation limit reached, please answer the customer"
AI_PAUSED_REASON = "AI paused: the subscription has expired, please answer the customer"
# What the customer sees instead of an AI answer (no word about limits or plans).
TEAM_WILL_REPLY = (
    "Thank you for your message! One of our travel consultants will reply to you shortly.\n"
    "شكراً لرسالتك! سيرد عليك أحد مستشاري السفر لدينا قريباً."
)


def ai_gate(db: Session, conversation: Conversation) -> tuple[str, str] | None:
    """Before the AI answers: None when it may, else (handover reason, system note) for the team.

    A chat counts towards the monthly limit once, when the AI first answers it in the month, so
    chats already running continue and only new chats go to the team when the limit is reached."""
    ent = entitlements(db, conversation.company_id)
    if not ent.has_plan:
        return None
    if ent.paused:
        return AI_PAUSED_REASON, "Handed over to the team: the AI is paused because the subscription has expired"
    start = month_start_utc()
    if conversation.ai_started_at is not None and conversation.ai_started_at >= start:
        return None
    limit = ent.max_ai_conversations
    if limit is not None and ai_conversations_this_month(db, conversation.company_id) >= limit:
        log.warning("Company %s reached its %s AI conversations this month", conversation.company_id, limit)
        return AI_LIMIT_REASON, (f"Handed over to the team: the plan's limit of {limit} AI conversations "
                                 "this month was reached")
    conversation.ai_started_at = utcnow()
    return None


# --- Money ----------------------------------------------------------------------------------------


def cycle_price(sub: Subscription, plan: Plan) -> Decimal:
    if sub.custom_price is not None:
        return omr(sub.custom_price)
    return omr(plan.price_yearly if sub.billing_cycle == BillingCycle.YEARLY else plan.price_monthly)


def monthly_value(sub: Subscription, plan: Plan) -> Decimal:
    price = cycle_price(sub, plan)
    return omr(price / 12) if sub.billing_cycle == BillingCycle.YEARLY else price


def next_period(sub: Subscription, on: date | None = None) -> tuple[date, date]:
    """The period a payment received today would pay for: right after the paid period, or from
    today when it has lapsed (or was a trial)."""
    on = on or today()
    end = sub.current_period_end if sub.status != SubscriptionStatus.TRIAL else None
    start = end + timedelta(days=1) if end is not None and end >= on - timedelta(days=1) else on
    return start, add_months(start, cycle_months(sub.billing_cycle)) - timedelta(days=1)


def extend(sub: Subscription, months: int, on: date | None = None) -> None:
    """+1 month / +1 year: from the end of the paid period, or from today when it has lapsed."""
    on = on or today()
    end = sub.current_period_end if sub.status != SubscriptionStatus.TRIAL else None
    if end is None or end < on:
        sub.current_period_start = on
        base = on - timedelta(days=1)
    else:
        base = end
    sub.current_period_end = add_months(base + timedelta(days=1), months) - timedelta(days=1)
    sub.status = SubscriptionStatus.ACTIVE
    sub.trial_end = None


def change_plan(db: Session, company: Company, sub: Subscription, plan: Plan) -> None:
    """Moves the company to another plan; its account limit follows unless it is custom."""
    if not sub.max_users_custom:
        from .users import seats_used  # noqa: PLC0415 (users imports schemas)

        used = seats_used(db, company.id)
        if plan.max_users < used:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"This company has {used} active accounts and the {plan.name} plan allows "
                                f"{plan.max_users}. Disable some accounts or set a custom account limit.")
    sub.plan_id = plan.id
    sub.plan = plan
    _sync_max_users(company, sub, plan)


def follow_plan_limit(db: Session, plan: Plan) -> None:
    """After the owner changed a plan's staff limit: companies without a custom limit follow it."""
    db.execute(
        update(Company)
        .where(Company.id.in_(select(Subscription.company_id).where(
            Subscription.plan_id == plan.id, Subscription.max_users_custom.is_(False))))
        .values(max_users=plan.max_users)
        .execution_options(synchronize_session="fetch")
    )
