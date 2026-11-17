"""Features and AI capabilities the platform owner gives each travel company.

Each one is a grant: on or off, an optional use limit per month or in total, an optional number of employees who
may use it (the company admin picks them), an optional monthly price, and for analytics the levels of data shown.
A part (for example the supplier library's spending figures) only works while its feature is on. Everything is off
until the platform owner switches it on.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Company, FeatureUsage, User
from .timeutil import local_today


@dataclass(frozen=True)
class Feature:
    label: str
    kind: Literal["tab", "ai", "part", "extra"]  # extra: on/off and a price (customer page designs, service packs)
    parent: str | None = None
    metered: bool = False  # each use counts against the limit
    levels: tuple[str, ...] = ()


FEATURES: dict[str, Feature] = {
    "members": Feature("Members community: ranks, VIP, perks and special requests", "tab"),
    "library": Feature("Supplier library: saved hotels, airlines, transport and activities, suggested again for similar requests", "tab"),
    "library_analytics": Feature("Spending figures: how much is spent with each supplier, what clients book most", "part", "library"),
    "library_margins": Feature("Margin learning: suggests the client price from the company's usual margin", "part", "library"),
    "quotes": Feature("Branded quotations: draft and final quotations as printable PDF pages with photos", "tab"),
    "reports": Feature("Reports: business reports as branded PDF pages", "tab"),
    "reports_excel": Feature("Excel downloads of the reports", "part", "reports"),
    "calendar": Feature("Calendar and reminders: appointments, airport meetings and reminders on WhatsApp", "tab"),
    "calendar_client_reminders": Feature("Reminders to clients on WhatsApp", "part", "calendar"),
    "broadcasts": Feature("Broadcasts and custom feedback to groups of clients", "tab"),
    "trip_planner": Feature("AI trip planner: drafts up to 3 choices per part (with web search) and learns from your team", "ai", metered=True),
    "plan_writer": Feature("AI day-by-day trip plans", "ai", metered=True),
    "quote_writer": Feature("AI writes the messages and quotation details the team sends to clients", "ai", metered=True),
    "service_builder": Feature("AI builds services and their process from the owner's description", "ai", metered=True),
    "package_builder": Feature("AI creates packages and experiences", "ai", metered=True),
    "daily_brief": Feature("AI work plan for each employee: today, this week, this month", "ai", metered=True),
    "insights": Feature("AI insights: business analysis, customer needs and growth plan", "ai", metered=True,
                        levels=("basic", "marketing", "deep", "finance")),
    "advisor": Feature("AI advisor: a chat with the AI about the business, with its recommendations", "ai", metered=True),
    "ai_training": Feature("The company edits its AI: knowledge, welcome message and training examples (you can always "
                           "edit them from the company page)", "extra"),
    "page_editorial": Feature("Editorial customer page: a magazine-style design with full-width photos, large serif titles, "
                              "a strip of experiences and numbered offerings", "extra"),
    "page_more_sections": Feature("More brand sections on the customer page: mission, philosophy, our promise and questions (FAQ)", "extra"),
    "concierge_services": Feature("Luxury concierge services: private aviation, yacht charters, villas, cruises, dining and nightlife, "
                                  "VIP access and events, chauffeur and car rental", "extra"),
}
PARTS = {key: {k: f.label for k, f in FEATURES.items() if f.parent == key} for key in FEATURES if FEATURES[key].kind != "part"}
PARTS = {k: v for k, v in PARTS.items() if v}
ADDONS = {k: f.label for k, f in FEATURES.items() if f.kind != "part"}


class Grant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    on: bool = False
    limit: int | None = Field(default=None, ge=1, le=1_000_000)  # uses per period (metered features)
    period: Literal["month", "total"] = "month"
    seats: int | None = Field(default=None, ge=1, le=10_000)  # employees allowed (None: every staff member)
    price: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000"), decimal_places=3)  # per month
    levels: list[Literal["basic", "marketing", "deep", "finance"]] = Field(default_factory=list)


def grants(company: Company) -> dict[str, Grant]:
    """The company's grants; an old on/off value reads as a grant."""
    raw = company.addons if isinstance(company.addons, dict) else {}
    out = {}
    for key in FEATURES:
        value = raw.get(key)
        try:
            out[key] = Grant(on=value) if isinstance(value, bool) else Grant.model_validate(value or {})
        except ValueError:
            out[key] = Grant()
    return out


def grant(company: Company, key: str) -> Grant:
    return grants(company).get(key, Grant())


def has_addon(company: Company, key: str) -> bool:
    """The company has the feature (and its parent feature)."""
    feature = FEATURES.get(key)
    if feature is None:
        return False
    g = grants(company)
    if feature.parent and not g[feature.parent].on:
        return False
    return g[key].on


def user_may(user: User, key: str) -> bool:
    """The company has it, and this employee is one of those allowed when the grant counts employees."""
    if user.company is None or not has_addon(user.company, key):
        return False
    top = FEATURES[key].parent or key
    if grant(user.company, top).seats is None:
        return True
    return top in (user.ai_features or [])


def enabled_addons(company: Company, user: User | None = None) -> list[str]:
    return [k for k in FEATURES if (user_may(user, k) if user is not None else has_addon(company, k))]


def require_addon(company: Company, key: str) -> None:
    if not has_addon(company, key):
        raise HTTPException(403, "This feature is not switched on for your company")


def period_key(g: Grant) -> str:
    return "total" if g.period == "total" else local_today().strftime("%Y-%m")


def usage(db: Session, company_id: int, key: str, g: Grant) -> int:
    return db.scalar(select(FeatureUsage.count).where(FeatureUsage.company_id == company_id, FeatureUsage.key == key,
                                                      FeatureUsage.period == period_key(g))) or 0


def use(db: Session, user: User, key: str) -> None:
    """Checks the employee may use the feature now and counts one use (for metered features with a limit)."""
    require_addon(user.company, key)
    if not user_may(user, key):
        raise HTTPException(403, "Your company admin has not given you this feature")
    feature = FEATURES[key]
    if not feature.metered:
        return
    g = grant(user.company, key)
    period = period_key(g)
    row = db.scalar(select(FeatureUsage).where(FeatureUsage.company_id == user.company_id, FeatureUsage.key == key,
                                               FeatureUsage.period == period).with_for_update())
    if row is None:
        row = FeatureUsage(company_id=user.company_id, key=key, period=period, count=0)
        db.add(row)
    if g.limit is not None and row.count >= g.limit:
        when = "this month" if g.period == "month" else "in total"
        raise HTTPException(429, f"Your company used all {g.limit} uses of this feature {when}")
    row.count += 1
    db.flush()

