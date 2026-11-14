"""Advanced features the platform owner switches on or off for each travel company.

They are separate from the plans so the owner can open a feature for one company (a pilot, a pitch, a
paying add-on) without changing its plan. Everything is off until the owner switches it on.
"""

from pydantic import BaseModel, ConfigDict

from .models import Company

ADDONS: dict[str, str] = {
    "members": "Members community: ranks, VIP, perks and special requests",
}


class AddonSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    members: bool = False


def addon_settings(company: Company) -> AddonSettings:
    raw = company.addons if isinstance(company.addons, dict) else {}
    try:
        return AddonSettings.model_validate(raw)
    except ValueError:
        return AddonSettings()


def has_addon(company: Company, key: str) -> bool:
    return bool(getattr(addon_settings(company), key, False))


def enabled_addons(company: Company) -> list[str]:
    s = addon_settings(company)
    return [k for k in ADDONS if getattr(s, k, False)]
