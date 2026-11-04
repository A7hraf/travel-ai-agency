"""Subscription plans.

Platform owner (/api/system/...): the plan catalogue, each company's subscription (change plan,
extend, trial, cancel), the manual payments ledger with invoices, MRR and the grace period.
Companies (/api/company/plan...): the admin's "My plan" page and the renewal banner for staff.
"""

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_company_user, require_system_admin
from ..models import (
    Company,
    Plan,
    PlatformSetting,
    Role,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
    User,
    utcnow,
)
from ..plan_schemas import (
    BillingOverviewOut,
    BillingSettingsIn,
    CompanyPlanOut,
    ExtendIn,
    InvoiceCompany,
    InvoiceOut,
    PaymentIn,
    PaymentListOut,
    PaymentOut,
    PeriodOut,
    PlanArchiveIn,
    PlanIn,
    PlanNoticeOut,
    PlanOut,
    SubscriptionBrief,
    SubscriptionOut,
    SubscriptionUpdate,
    TrialIn,
    UsageOut,
)
from ..security import random_token
from ..services import plans as svc
from ..services.users import seats_used

router = APIRouter(tags=["plans"])

EXPIRING_DAYS = 14


# --- Helpers --------------------------------------------------------------------------------------


def _plan_out(plan: Plan, companies: int = 0) -> PlanOut:
    out = PlanOut.model_validate(plan)
    out.features = list(plan.features or [])
    out.features_ar = list(plan.features_ar or [])
    out.companies = companies
    return out


def _get_plan(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return plan


def _get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def _subscription(db: Session, company: Company) -> Subscription:
    """The company's subscription (created on the default plan if it somehow has none)."""
    sub = svc.ensure_subscription(db, company)
    if sub is None:
        raise HTTPException(409, "Create a plan first")
    db.flush()
    return sub


def _usage(db: Session, company: Company, plan: Plan) -> UsageOut:
    return UsageOut(
        users=seats_used(db, company.id), max_users=company.max_users,
        packages=svc.active_packages(db, company.id), max_packages=plan.max_packages,
        ai_conversations=svc.ai_conversations_this_month(db, company.id),
        max_ai_conversations=plan.max_ai_conversations,
    )


def _payments_total(db: Session, company_id: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(SubscriptionPayment.amount), 0))
                           .where(SubscriptionPayment.company_id == company_id)) or 0)


def _subscription_out(db: Session, company: Company, sub: Subscription) -> SubscriptionOut:
    plan = sub.plan
    ent = svc.entitlements_for(sub, plan, svc.grace_days(db), max_users=company.max_users)
    start, end = svc.next_period(sub)
    return SubscriptionOut(
        company_id=company.id, plan=_plan_out(plan), billing_cycle=sub.billing_cycle, status=sub.status,
        state=ent.state, current_period_start=sub.current_period_start, current_period_end=sub.current_period_end,
        trial_end=sub.trial_end, ends_on=ent.ends_on, days_left=ent.days_left, grace_until=ent.grace_until,
        custom_price=float(sub.custom_price) if sub.custom_price is not None else None,
        cycle_price=float(svc.cycle_price(sub, plan)), monthly_value=float(svc.monthly_value(sub, plan)),
        notes=sub.notes or "", max_users=company.max_users, max_users_custom=sub.max_users_custom,
        usage=_usage(db, company, plan),
        next_period=PeriodOut(start=start, end=end, amount=float(svc.cycle_price(sub, plan))),
        payments_total=_payments_total(db, company.id),
    )


def _payments(db: Session, company_id: int) -> list[PaymentOut]:
    rows = db.scalars(select(SubscriptionPayment).where(SubscriptionPayment.company_id == company_id)
                      .order_by(SubscriptionPayment.paid_on.desc(), SubscriptionPayment.id.desc())).all()
    return [PaymentOut.model_validate(p) for p in rows]


def _set_default(db: Session, plan: Plan) -> None:
    db.execute(update(Plan).where(Plan.id != plan.id).values(is_default=False)
               .execution_options(synchronize_session="fetch"))
    plan.is_default = True


# --- Plan catalogue (owner) -------------------------------------------------------------------------


@router.get("/api/system/plans", response_model=list[PlanOut])
def list_plans(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Subscription.plan_id, func.count(Subscription.id))
                             .group_by(Subscription.plan_id)).all())
    plans = db.scalars(select(Plan).order_by(Plan.is_archived, Plan.sort_order, Plan.id)).all()
    return [_plan_out(p, counts.get(p.id, 0)) for p in plans]


@router.post("/api/system/plans", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    data = body.model_dump()
    is_default = data.pop("is_default")
    plan = Plan(**data, is_default=False)
    db.add(plan)
    db.flush()
    if is_default:
        _set_default(db, plan)
    db.commit()
    return _plan_out(plan)


@router.put("/api/system/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, body: PlanIn, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    plan = _get_plan(db, plan_id)
    data = body.model_dump()
    is_default = data.pop("is_default")
    if plan.is_default and not is_default:
        raise HTTPException(400, "Choose another plan as the default for new companies first")
    if is_default and plan.is_archived:
        raise HTTPException(400, "An archived plan can't be the default for new companies")
    users_changed = data["max_users"] != plan.max_users
    for key, value in data.items():
        setattr(plan, key, value)
    if is_default:
        _set_default(db, plan)
    db.flush()
    if users_changed:
        svc.follow_plan_limit(db, plan)
    db.commit()
    count = db.scalar(select(func.count(Subscription.id)).where(Subscription.plan_id == plan.id)) or 0
    return _plan_out(plan, count)


@router.post("/api/system/plans/{plan_id}/archive", response_model=PlanOut)
def archive_plan(plan_id: int, body: PlanArchiveIn, _: User = Depends(require_system_admin),
                 db: Session = Depends(get_db)):
    """Archived plans can't be chosen any more; companies already on them keep them."""
    plan = _get_plan(db, plan_id)
    if body.archived and plan.is_default:
        raise HTTPException(400, "Choose another plan as the default for new companies first")
    plan.is_archived = body.archived
    db.commit()
    count = db.scalar(select(func.count(Subscription.id)).where(Subscription.plan_id == plan.id)) or 0
    return _plan_out(plan, count)


# --- Overview, grace period ----------------------------------------------------------------------


@router.get("/api/system/billing", response_model=BillingOverviewOut)
def billing_overview(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Monthly recurring revenue (paying companies, yearly prices divided by 12) and status counts."""
    grace = svc.grace_days(db)
    on = svc.today()
    counts = {"trial": 0, "active": 0, "past_due": 0, "expired": 0, "cancelled": 0}
    mrr = Decimal("0")
    expiring = 0
    for sub, plan in db.execute(select(Subscription, Plan).join(Plan, Plan.id == Subscription.plan_id)).all():
        state = svc.access_state(sub, on, grace)
        key = "past_due" if state == "grace" else state
        counts[key] = counts.get(key, 0) + 1
        if state in svc.PAYING_STATES:
            mrr += svc.monthly_value(sub, plan)
        end = svc.period_end(sub)
        if end is not None and state != svc.STATE_PAUSED and 0 <= (end - on).days <= EXPIRING_DAYS:
            expiring += 1
    return BillingOverviewOut(mrr=float(svc.omr(mrr)), counts=counts, expiring_soon=expiring, grace_days=grace)


@router.put("/api/system/billing/settings", response_model=BillingOverviewOut)
def update_billing_settings(body: BillingSettingsIn, me: User = Depends(require_system_admin),
                            db: Session = Depends(get_db)):
    row = db.get(PlatformSetting, svc.GRACE_SETTING_KEY)
    if row is None:
        row = PlatformSetting(key=svc.GRACE_SETTING_KEY)
        db.add(row)
    row.value, row.updated_at, row.updated_by = str(body.grace_days), utcnow(), me.email
    db.commit()
    return billing_overview(me, db)


# --- Company subscriptions (owner) ---------------------------------------------------------------


@router.get("/api/system/subscriptions", response_model=list[SubscriptionBrief])
def list_subscriptions(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Plan, status and renewal date of every company (one query, for the companies list)."""
    grace = svc.grace_days(db)
    on = svc.today()
    out = []
    for sub, plan in db.execute(select(Subscription, Plan).join(Plan, Plan.id == Subscription.plan_id)
                                .order_by(Subscription.company_id)).all():
        ent = svc.entitlements_for(sub, plan, grace, on)
        out.append(SubscriptionBrief(
            company_id=sub.company_id, plan_id=plan.id, plan_name=plan.name, plan_name_ar=plan.name_ar or "",
            billing_cycle=sub.billing_cycle, status=sub.status, state=ent.state, ends_on=ent.ends_on,
            days_left=ent.days_left, monthly_value=float(svc.monthly_value(sub, plan))))
    return out


@router.get("/api/system/companies/{company_id}/subscription", response_model=SubscriptionOut)
def get_subscription(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    db.commit()
    return _subscription_out(db, company, sub)


@router.patch("/api/system/companies/{company_id}/subscription", response_model=SubscriptionOut)
def update_subscription(company_id: int, body: SubscriptionUpdate, _: User = Depends(require_system_admin),
                        db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    fields = body.model_fields_set
    if body.plan_id is not None and body.plan_id != sub.plan_id:
        plan = _get_plan(db, body.plan_id)
        if plan.is_archived:
            raise HTTPException(400, "This plan is archived. Choose another plan or unarchive it first.")
        svc.change_plan(db, company, sub, plan)
    if body.billing_cycle is not None:
        sub.billing_cycle = body.billing_cycle
    if body.status is not None:
        sub.status = body.status
    for key in ("current_period_start", "current_period_end", "trial_end"):
        if key in fields:
            setattr(sub, key, getattr(body, key))
    if sub.current_period_start and sub.current_period_end and sub.current_period_end < sub.current_period_start:
        raise HTTPException(400, "The period can't end before it starts")
    if sub.status == SubscriptionStatus.TRIAL and sub.trial_end is None:
        raise HTTPException(400, "Enter the last day of the trial")
    if "custom_price" in fields:
        sub.custom_price = Decimal(str(body.custom_price)) if body.custom_price is not None else None
    if body.notes is not None:
        sub.notes = body.notes.strip()
    if "account_limit" in fields:
        limit = body.account_limit if body.account_limit is not None else sub.plan.max_users
        used = seats_used(db, company.id)
        if limit < used:
            raise HTTPException(400, f"This company has {used} active accounts. Disable or delete some "
                                     f"before lowering the limit to {limit}.")
        sub.max_users_custom = body.account_limit is not None
        company.max_users = limit
    db.commit()
    return _subscription_out(db, company, sub)


@router.post("/api/system/companies/{company_id}/subscription/extend", response_model=SubscriptionOut)
def extend_subscription(company_id: int, body: ExtendIn, _: User = Depends(require_system_admin),
                        db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    svc.extend(sub, body.months)
    db.commit()
    return _subscription_out(db, company, sub)


@router.post("/api/system/companies/{company_id}/subscription/trial", response_model=SubscriptionOut)
def start_trial(company_id: int, body: TrialIn, _: User = Depends(require_system_admin),
                db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    days = body.days or sub.plan.trial_days or 14
    on = svc.today()
    sub.status = SubscriptionStatus.TRIAL
    sub.trial_end = on + timedelta(days=days)
    db.commit()
    return _subscription_out(db, company, sub)


@router.post("/api/system/companies/{company_id}/subscription/cancel", response_model=SubscriptionOut)
def cancel_subscription(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Cancelled: everything keeps working until the end of the paid period, then pauses (no grace)."""
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    if sub.status == SubscriptionStatus.TRIAL:
        sub.current_period_end = sub.trial_end
    sub.status = SubscriptionStatus.CANCELLED
    db.commit()
    return _subscription_out(db, company, sub)


# --- Payments (owner) ----------------------------------------------------------------------------


@router.get("/api/system/companies/{company_id}/payments", response_model=PaymentListOut)
def list_payments(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    return PaymentListOut(payments=_payments(db, company.id), total=_payments_total(db, company.id))


@router.post("/api/system/companies/{company_id}/payments", response_model=PaymentOut, status_code=201)
def record_payment(company_id: int, body: PaymentIn, me: User = Depends(require_system_admin),
                   db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    sub = _subscription(db, company)
    payment = SubscriptionPayment(
        company_id=company.id, invoice_number=f"tmp-{random_token(8)}", amount=Decimal(str(body.amount)),
        currency="OMR", paid_on=body.paid_on, method=body.method, reference=body.reference.strip(),
        period_start=body.period_start, period_end=body.period_end, plan_name=sub.plan.name,
        billing_cycle=sub.billing_cycle, notes=body.notes.strip(), created_by=me.email,
    )
    db.add(payment)
    db.flush()
    payment.invoice_number = f"INV-{body.paid_on.year}-{payment.id:05d}"
    if body.extend and body.period_end is not None:
        if sub.current_period_end is None or sub.status == SubscriptionStatus.TRIAL \
                or body.period_end > sub.current_period_end:
            sub.current_period_end = body.period_end
            sub.current_period_start = body.period_start
        sub.status = SubscriptionStatus.ACTIVE
        sub.trial_end = None
    db.commit()
    return PaymentOut.model_validate(payment)


@router.delete("/api/system/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    """Removes a payment recorded by mistake (the subscription's period is not changed)."""
    payment = db.get(SubscriptionPayment, payment_id)
    if payment is None:
        raise HTTPException(404, "Payment not found")
    db.delete(payment)
    db.commit()


def _invoice(db: Session, payment: SubscriptionPayment | None) -> InvoiceOut:
    if payment is None:
        raise HTTPException(404, "Payment not found")
    company = db.get(Company, payment.company_id)
    return InvoiceOut(payment=PaymentOut.model_validate(payment), company=InvoiceCompany(
        name=company.name, slug=company.slug, contact_email=company.contact_email,
        contact_phone=company.contact_phone))


@router.get("/api/system/payments/{payment_id}/invoice", response_model=InvoiceOut)
def owner_invoice(payment_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return _invoice(db, db.get(SubscriptionPayment, payment_id))


# --- The company's own plan --------------------------------------------------------------------------


def require_company_admin(user: User = Depends(get_company_user)) -> User:
    if user.role != Role.COMPANY_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a company admin can see the plan and payments")
    return user


@router.get("/api/company/plan", response_model=CompanyPlanOut)
def my_plan(me: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    company = me.company
    sub = _subscription(db, company)
    db.commit()
    plan = sub.plan
    ent = svc.entitlements_for(sub, plan, svc.grace_days(db), max_users=company.max_users)
    return CompanyPlanOut(
        plan=_plan_out(plan), billing_cycle=sub.billing_cycle, status=sub.status, state=ent.state,
        ends_on=ent.ends_on, days_left=ent.days_left, grace_until=ent.grace_until,
        current_period_start=sub.current_period_start, current_period_end=sub.current_period_end,
        trial_end=sub.trial_end, cycle_price=float(svc.cycle_price(sub, plan)), usage=_usage(db, company, plan),
        payments=_payments(db, company.id), payments_total=_payments_total(db, company.id),
    )


@router.get("/api/company/plan/payments/{payment_id}/invoice", response_model=InvoiceOut)
def my_invoice(payment_id: int, me: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    payment = db.get(SubscriptionPayment, payment_id)
    if payment is None or payment.company_id != me.company_id:
        raise HTTPException(404, "Payment not found")
    return _invoice(db, payment)


def banner_for(ent: svc.Entitlements) -> str | None:
    if not ent.has_plan:
        return None
    if ent.state == svc.STATE_PAUSED:
        return "expired"
    if ent.state in ("grace", "past_due"):
        return "past_due"
    if ent.days_left is not None and ent.days_left <= svc.TRIAL_ENDING_DAYS:
        if ent.state == "trial":
            return "trial_ending"
        if ent.state == "cancelled":
            return "cancelled"
    return None


@router.get("/api/company/plan/notice", response_model=PlanNoticeOut)
def plan_notice(me: User = Depends(get_company_user), db: Session = Depends(get_db)):
    """What every employee's app needs: the renewal banner and which features the plan includes."""
    ent = svc.entitlements(db, me.company_id)
    return PlanNoticeOut(
        has_plan=ent.has_plan, plan_name=ent.plan_name, plan_name_ar=ent.plan_name_ar, status=ent.status,
        state=ent.state, ends_on=ent.ends_on, days_left=ent.days_left, grace_until=ent.grace_until,
        banner=banner_for(ent), whatsapp=ent.whatsapp, instagram=ent.instagram, page_editor=ent.page_editor,
        remove_powered_by=ent.remove_powered_by, max_packages=ent.max_packages,
        max_ai_conversations=ent.max_ai_conversations,
    )
