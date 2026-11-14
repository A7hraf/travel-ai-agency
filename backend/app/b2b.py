"""Business accounts: the business clients and vendors of a travel company.

Three levels decide what a business account can do:

1. The platform owner switches business accounts on for a travel company, sets how many client and
   vendor accounts it may open, how many logins each may have, and which features it may give
   (``Company.b2b``, edited on the owner console only).
2. The travel company gives each of its accounts some of those features (``Partner.features``).
3. A feature works only while both allow it: when the owner takes a feature back, every account of
   that company loses it at once, without its saved choice being changed.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Company, Partner, PartnerKind

# Feature keys are "<kind>.<feature>". The English text is the label shown in the apps.
FEATURES: dict[str, str] = {
    "client.requests": "Request trips from the dashboard",
    "client.whatsapp": "Request trips by WhatsApp from linked numbers",
    "client.ai_chat": "Chat with the AI assistant",
    "client.history": "Travel history",
    "client.exclusive_packages": "Exclusive packages",
    "client.reports": "Spending reports",
    "vendor.requests": "Receive trip requests",
    "vendor.quotes": "Send options and prices",
    "vendor.history": "Job history",
}

KINDS = (PartnerKind.CLIENT, PartnerKind.VENDOR)


def features_of(kind: str) -> list[str]:
    return [f for f in FEATURES if f.startswith(f"{kind}.")]


def clean_features(features: list[str] | None, kind: str | None = None) -> list[str]:
    """Known features (of one kind), in catalog order, without repeats."""
    wanted = set(features or [])
    return [f for f in FEATURES if f in wanted and (kind is None or f.startswith(f"{kind}."))]


class B2BSettings(BaseModel):
    """What the platform owner allows a travel company. Business accounts are off until switched on."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_clients: int = Field(default=0, ge=0, le=10000)
    max_vendors: int = Field(default=0, ge=0, le=1000)
    max_users_per_partner: int = Field(default=3, ge=1, le=1000)
    features: list[str] = Field(default_factory=list)

    @field_validator("features")
    @classmethod
    def known_features(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(FEATURES))
        if unknown:
            raise ValueError(f"Unknown feature: {', '.join(unknown)}")
        return clean_features(v)

    def limit(self, kind: str) -> int:
        return self.max_clients if kind == PartnerKind.CLIENT else self.max_vendors


def b2b_settings(company: Company) -> B2BSettings:
    raw: Any = company.b2b if isinstance(company.b2b, dict) else {}
    try:
        return B2BSettings.model_validate(raw)
    except ValueError:
        # A feature removed from the catalog must not switch everything off: keep what is still valid.
        cleaned = {k: v for k, v in raw.items() if k in B2BSettings.model_fields}
        cleaned["features"] = clean_features(cleaned.get("features") if isinstance(cleaned.get("features"), list) else [])
        try:
            return B2BSettings.model_validate(cleaned)
        except ValueError:
            return B2BSettings()


def effective_features(partner: Partner, company: Company | None = None) -> list[str]:
    """Features an account can really use now: given by its travel company and allowed by the owner."""
    company = company or partner.company
    settings = b2b_settings(company)
    if not settings.enabled or not partner.is_active:
        return []
    allowed = set(settings.features)
    return [f for f in clean_features(partner.features, partner.kind) if f in allowed]
