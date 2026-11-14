"""Advanced features the platform owner switches on or off for each travel company.

They are separate from the plans so the owner can open a feature for one company (a pilot, a pitch, a
paying add-on) without changing its plan. Everything is off until the owner switches it on. Some features have
parts the owner can give separately (for example the supplier library without its spending figures); a part
only works while its feature is on.
"""

from pydantic import BaseModel, ConfigDict

from .models import Company

ADDONS: dict[str, str] = {
    "members": "Members community: ranks, VIP, perks and special requests",
    "trip_planner": "AI trip planner: drafts up to 3 choices per part (with web search) and learns from your team",
    "insights": "AI insights: business analysis, customer needs and growth plan",
    "library": "Supplier library: saved hotels, airlines, transport and activities, suggested again for similar requests",
    "quotes": "Branded quotations: draft and final quotations as printable PDF pages with photos",
    "reports": "Reports: business reports as branded PDF pages",
    "calendar": "Calendar and reminders: appointments, airport meetings and reminders on WhatsApp",
    "advisor": "AI advisor: a chat with the AI about the business, with its recommendations",
}

# The parts of a feature (feature -> part key -> label). A part key is "<feature>_<part>".
PARTS: dict[str, dict[str, str]] = {
    "library": {
        "library_analytics": "Spending figures: how much is spent with each supplier, what clients book most",
        "library_margins": "Margin learning: suggests the client price from the company's usual margin",
    },
    "reports": {"reports_excel": "Excel downloads of the reports"},
    "calendar": {"calendar_client_reminders": "Reminders to clients on WhatsApp"},
}
PARENT = {part: feature for feature, parts in PARTS.items() for part in parts}


class AddonSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    members: bool = False
    trip_planner: bool = False
    insights: bool = False
    library: bool = False
    library_analytics: bool = False
    library_margins: bool = False
    quotes: bool = False
    reports: bool = False
    reports_excel: bool = False
    calendar: bool = False
    calendar_client_reminders: bool = False
    advisor: bool = False


ALL_KEYS = [*ADDONS, *PARENT]


def addon_settings(company: Company) -> AddonSettings:
    raw = company.addons if isinstance(company.addons, dict) else {}
    try:
        return AddonSettings.model_validate(raw)
    except ValueError:
        return AddonSettings()


def has_addon(company: Company, key: str) -> bool:
    s = addon_settings(company)
    if key in PARENT and not getattr(s, PARENT[key], False):
        return False
    return bool(getattr(s, key, False))


def enabled_addons(company: Company) -> list[str]:
    return [k for k in ALL_KEYS if has_addon(company, k)]


def require_addon(company: Company, key: str) -> None:
    from fastapi import HTTPException  # noqa: PLC0415

    if not has_addon(company, key):
        raise HTTPException(403, "This feature is not switched on for your company")
