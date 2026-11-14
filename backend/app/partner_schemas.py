"""Request and response shapes of the business accounts (clients and vendors)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .b2b import B2BSettings

Kind = Literal["client", "vendor"]


def _one_line(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


class PartnerIn(BaseModel):
    kind: Kind
    name: str = Field(min_length=2, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=50)
    whatsapp_numbers: list[str] = Field(default_factory=list, max_length=20)
    is_active: bool = True

    @field_validator("name", "contact_name", "contact_phone")
    @classmethod
    def one_line(cls, v: str | None) -> str | None:
        return _one_line(v)

    @field_validator("contact_email", mode="before")
    @classmethod
    def empty_email(cls, v):
        return v or None


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    features: list[str] | None = Field(default=None, max_length=50)
    whatsapp_numbers: list[str] | None = Field(default=None, max_length=20)
    is_active: bool | None = None

    @field_validator("name", "contact_name", "contact_phone")
    @classmethod
    def one_line(cls, v: str | None) -> str | None:
        return _one_line(v)

    @field_validator("contact_email", mode="before")
    @classmethod
    def empty_email(cls, v):
        return v or None


class PartnerLoginOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class PartnerOut(BaseModel):
    id: int
    kind: str
    name: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    notes: str | None
    features: list[str]            # what the travel company chose
    active_features: list[str]     # what really works now (also allowed by the platform owner)
    whatsapp_numbers: list[str]
    is_active: bool
    created_at: datetime
    logins: list[PartnerLoginOut]


class B2BUsage(BaseModel):
    clients: int
    vendors: int


class B2BOverview(BaseModel):
    """What a travel company sees: the owner's limits and allowed features, and its use of them."""

    settings: B2BSettings
    usage: B2BUsage
    catalog: dict[str, str]


class PartnerListOut(B2BOverview):
    partners: list[PartnerOut]


class PartnerLoginIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def one_line(cls, v: str) -> str:
        return " ".join(v.split())


class PartnerLoginUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    is_active: bool | None = None
    new_password: bool = False  # True: make a new password (shown once)


class PartnerLoginCreated(BaseModel):
    login: PartnerLoginOut
    password: str | None = None  # shown once, never stored


class PartnerHome(BaseModel):
    """The business portal: who you are, for which travel company, and what you can use."""

    partner_id: int
    partner_name: str
    kind: str
    company_name: str
    company_slug: str
    logo: str | None
    features: list[str]
    catalog: dict[str, str]
    whatsapp_numbers: list[str]
    company_whatsapp: str | None
