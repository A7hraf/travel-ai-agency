"""Company branding: customer page look and content, and the employee dashboard colours.

Stored as JSON on the company. The customer-page part is edited by the company admin and the
platform owner; the dashboard colours are set by the platform owner only.
"""

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator

from .models import Company

HEX = r"^#[0-9a-fA-F]{6}$"
SECTIONS = ("search", "featured", "offers", "about", "contact")
DASHBOARD_FIELDS = {"dashboard_color", "dashboard_sidebar"}

Section = Literal["search", "featured", "offers", "about", "contact"]


def _image_ref(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("/api/media/") or value.startswith("https://"):
        return value
    raise ValueError("must be an uploaded image or an https:// address")


class Branding(BaseModel):
    # Defaults follow the Ghanjah brand: Gulf Cyan for actions, Ink for the sidebar.
    # Customer page
    primary_color: str = Field(default="#0088b0", pattern=HEX)
    accent_color: str = Field(default="#4fb6dc", pattern=HEX)
    logo: str | None = Field(default=None, max_length=500)
    hero_style: Literal["gradient", "image", "solid"] = "gradient"
    hero_image: str | None = Field(default=None, max_length=500)
    hero_title_en: str = Field(default="", max_length=120)
    hero_title_ar: str = Field(default="", max_length=120)
    hero_text_en: str = Field(default="", max_length=400)
    hero_text_ar: str = Field(default="", max_length=400)
    about_title_en: str = Field(default="", max_length=120)
    about_title_ar: str = Field(default="", max_length=120)
    about_en: str = Field(default="", max_length=3000)
    about_ar: str = Field(default="", max_length=3000)
    sections: list[Section] = Field(default_factory=lambda: list(SECTIONS))
    card_style: Literal["rounded", "square"] = "rounded"
    layout: Literal["grid", "list"] = "grid"
    # Employee dashboard (platform owner only)
    dashboard_color: str = Field(default="#0088b0", pattern=HEX)
    dashboard_sidebar: str = Field(default="#0f0e0d", pattern=HEX)

    @field_validator("logo", "hero_image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return _image_ref(v)

    @field_validator("sections")
    @classmethod
    def unique_sections(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for s in v:
            if s not in seen:
                seen.append(s)
        return seen


class BrandingUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    primary_color: str | None = Field(default=None, pattern=HEX)
    accent_color: str | None = Field(default=None, pattern=HEX)
    logo: str | None = None
    hero_style: Literal["gradient", "image", "solid"] | None = None
    hero_image: str | None = None
    hero_title_en: str | None = Field(default=None, max_length=120)
    hero_title_ar: str | None = Field(default=None, max_length=120)
    hero_text_en: str | None = Field(default=None, max_length=400)
    hero_text_ar: str | None = Field(default=None, max_length=400)
    about_title_en: str | None = Field(default=None, max_length=120)
    about_title_ar: str | None = Field(default=None, max_length=120)
    about_en: str | None = Field(default=None, max_length=3000)
    about_ar: str | None = Field(default=None, max_length=3000)
    sections: list[Section] | None = None
    card_style: Literal["rounded", "square"] | None = None
    layout: Literal["grid", "list"] | None = None
    dashboard_color: str | None = Field(default=None, pattern=HEX)
    dashboard_sidebar: str | None = Field(default=None, pattern=HEX)

    @field_validator("logo", "hero_image")
    @classmethod
    def check_image(cls, v: str | None) -> str | None:
        return _image_ref(v)


class PublicBranding(BaseModel):
    primary_color: str
    accent_color: str
    logo: str | None
    hero_style: str
    hero_image: str | None
    hero_title_en: str
    hero_title_ar: str
    hero_text_en: str
    hero_text_ar: str
    about_title_en: str
    about_title_ar: str
    about_en: str
    about_ar: str
    sections: list[str]
    card_style: str
    layout: str


class DashboardBranding(BaseModel):
    logo: str | None
    dashboard_color: str
    dashboard_sidebar: str


def get_branding(company: Company) -> Branding:
    try:
        return Branding.model_validate(company.branding or {})
    except ValueError:
        return Branding()


def apply_update(company: Company, update: BrandingUpdate, allow_dashboard: bool) -> Branding:
    data = update.model_dump(exclude_unset=True)
    if not allow_dashboard:
        for key in DASHBOARD_FIELDS:
            data.pop(key, None)
    merged = get_branding(company).model_dump() | data
    try:
        branding = Branding.model_validate(merged)  # re-validates every field
    except ValidationError as exc:
        raise HTTPException(422, str(exc.errors()[0].get("msg", "Invalid branding"))) from exc
    company.branding = branding.model_dump()
    return branding


def public_branding(company: Company) -> PublicBranding:
    return PublicBranding(**get_branding(company).model_dump(exclude=DASHBOARD_FIELDS))


def dashboard_branding(company: Company) -> DashboardBranding:
    b = get_branding(company)
    return DashboardBranding(logo=b.logo, dashboard_color=b.dashboard_color, dashboard_sidebar=b.dashboard_sidebar)
