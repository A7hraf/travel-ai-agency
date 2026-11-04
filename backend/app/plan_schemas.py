"""API shapes of subscription plans, company subscriptions and the payments ledger."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_PRICE = 1_000_000.0
PaymentMethod = Literal["bank_transfer", "card", "cash"]
Cycle = Literal["monthly", "yearly"]
Status = Literal["trial", "active", "past_due", "expired", "cancelled"]


def _three_decimals(v: float | None) -> float | None:
    if v is None:
        return v
    if round(v, 3) != round(v, 6):
        raise ValueError("Use at most 3 decimals (1 rial = 1000 baisa)")
    return round(v, 3)


def _clean_list(items: list[str]) -> list[str]:
    return [" ".join(s.split()) for s in items if s and s.strip()]


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    name_ar: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    description_ar: str = Field(default="", max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=20)
    features_ar: list[str] = Field(default_factory=list, max_length=20)
    price_monthly: float = Field(ge=0, le=MAX_PRICE)
    price_yearly: float = Field(ge=0, le=MAX_PRICE)
    trial_days: int = Field(default=14, ge=0, le=365)
    max_users: int = Field(ge=1, le=10000)
    max_packages: int | None = Field(default=None, ge=1, le=100000)
    max_ai_conversations: int | None = Field(default=None, ge=0, le=10_000_000)
    allow_whatsapp: bool = True
    allow_instagram: bool = False
    allow_page_editor: bool = True
    allow_remove_powered_by: bool = False
    priority_support: bool = False
    is_default: bool = False
    sort_order: int = Field(default=0, ge=0, le=1000)

    @field_validator("price_monthly", "price_yearly")
    @classmethod
    def _price(cls, v: float) -> float:
        return _three_decimals(v)

    @field_validator("name", "name_ar")
    @classmethod
    def _name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("features", "features_ar")
    @classmethod
    def _features(cls, v: list[str]) -> list[str]:
        v = _clean_list(v)
        if any(len(s) > 200 for s in v):
            raise ValueError("A feature can have at most 200 characters")
        return v

    @field_validator("description", "description_ar")
    @classmethod
    def _text(cls, v: str) -> str:
        return v.strip()


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_ar: str
    description: str
    description_ar: str
    features: list[str]
    features_ar: list[str]
    price_monthly: float
    price_yearly: float
    trial_days: int
    max_users: int
    max_packages: int | None
    max_ai_conversations: int | None
    allow_whatsapp: bool
    allow_instagram: bool
    allow_page_editor: bool
    allow_remove_powered_by: bool
    priority_support: bool
    is_default: bool
    is_archived: bool
    sort_order: int
    companies: int = 0


class PlanArchiveIn(BaseModel):
    archived: bool


class UsageOut(BaseModel):
    users: int
    max_users: int | None
    packages: int
    max_packages: int | None
    ai_conversations: int
    max_ai_conversations: int | None


class PeriodOut(BaseModel):
    start: date
    end: date
    amount: float


class SubscriptionOut(BaseModel):
    company_id: int
    plan: PlanOut
    billing_cycle: str
    status: str
    # status combined with today's date: trial, active, past_due, cancelled, grace or expired (paused)
    state: str
    current_period_start: date | None
    current_period_end: date | None
    trial_end: date | None
    ends_on: date | None
    days_left: int | None
    grace_until: date | None
    custom_price: float | None
    cycle_price: float
    monthly_value: float
    notes: str
    max_users: int
    max_users_custom: bool
    usage: UsageOut
    next_period: PeriodOut
    payments_total: float


class SubscriptionBrief(BaseModel):
    company_id: int
    plan_id: int
    plan_name: str
    plan_name_ar: str
    billing_cycle: str
    status: str
    state: str
    ends_on: date | None
    days_left: int | None
    monthly_value: float


class SubscriptionUpdate(BaseModel):
    plan_id: int | None = None
    billing_cycle: Cycle | None = None
    status: Status | None = None
    current_period_start: date | None = None
    current_period_end: date | None = None
    trial_end: date | None = None
    # null: the plan's price
    custom_price: float | None = Field(default=None, ge=0, le=MAX_PRICE)
    notes: str | None = Field(default=None, max_length=4000)
    # null: follow the plan's staff limit
    account_limit: int | None = Field(default=None, ge=1, le=10000)

    @field_validator("custom_price")
    @classmethod
    def _price(cls, v: float | None) -> float | None:
        return _three_decimals(v)


class ExtendIn(BaseModel):
    months: Literal[1, 12]


class TrialIn(BaseModel):
    days: int | None = Field(default=None, ge=1, le=365)


class PaymentIn(BaseModel):
    amount: float = Field(gt=0, le=MAX_PRICE)
    paid_on: date
    method: PaymentMethod
    reference: str = Field(default="", max_length=200)
    period_start: date | None = None
    period_end: date | None = None
    notes: str = Field(default="", max_length=2000)
    # Move the subscription's paid period to the end of the period this payment covers.
    extend: bool = True

    @field_validator("amount")
    @classmethod
    def _amount(cls, v: float) -> float:
        return _three_decimals(v)

    @model_validator(mode="after")
    def _period(self) -> "PaymentIn":
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("Enter both the first and the last day of the period, or neither")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("The period can't end before it starts")
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    invoice_number: str
    amount: float
    currency: str
    paid_on: date
    method: str
    reference: str
    period_start: date | None
    period_end: date | None
    plan_name: str
    billing_cycle: str
    notes: str
    created_by: str | None
    created_at: datetime


class PaymentListOut(BaseModel):
    payments: list[PaymentOut]
    total: float


class InvoiceCompany(BaseModel):
    name: str
    slug: str
    contact_email: str | None
    contact_phone: str | None


class InvoiceOut(BaseModel):
    payment: PaymentOut
    company: InvoiceCompany


class BillingOverviewOut(BaseModel):
    mrr: float
    currency: str = "OMR"
    counts: dict[str, int]
    expiring_soon: int
    grace_days: int


class BillingSettingsIn(BaseModel):
    grace_days: int = Field(ge=0, le=90)


class CompanyPlanOut(BaseModel):
    """The company admin's "My plan" page (no internal notes of the platform)."""
    plan: PlanOut
    billing_cycle: str
    status: str
    state: str
    ends_on: date | None
    days_left: int | None
    grace_until: date | None
    current_period_start: date | None
    current_period_end: date | None
    trial_end: date | None
    cycle_price: float
    usage: UsageOut
    payments: list[PaymentOut]
    payments_total: float


class PlanNoticeOut(BaseModel):
    """For every employee: the banner and what the plan includes."""
    has_plan: bool
    plan_name: str
    plan_name_ar: str
    status: str
    state: str
    ends_on: date | None
    days_left: int | None
    grace_until: date | None
    # trial_ending, past_due, expired, cancelled or None (no banner)
    banner: str | None
    whatsapp: bool
    instagram: bool
    page_editor: bool
    remove_powered_by: bool
    max_packages: int | None
    max_ai_conversations: int | None
