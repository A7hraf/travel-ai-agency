import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import CompanyStatus, Role, TicketStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth --------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class CompanyBrief(ORM):
    id: int
    name: str
    slug: str
    status: str


class UserOut(ORM):
    id: int
    email: str
    full_name: str
    role: str
    permissions: list[str]
    is_active: bool
    company_id: int | None
    created_at: datetime
    last_login_at: datetime | None


class MeOut(UserOut):
    company: CompanyBrief | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


# --- Users (company admin) ------------------------------------------------------


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    # None = use the role's default permissions
    permissions: list[str] | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    permissions: list[str] | None = None
    is_active: bool | None = None


class UserListOut(BaseModel):
    users: list[UserOut]
    max_users: int
    used: int


class PermissionCatalogOut(BaseModel):
    permissions: dict[str, str]
    role_defaults: dict[str, list[str]]


# --- Companies (system admin) ---------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    max_users: int = Field(default=5, ge=1, le=10000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    admin_email: EmailStr
    admin_full_name: str = Field(min_length=1, max_length=200)
    admin_password: str = Field(min_length=8, max_length=128)

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str | None) -> str | None:
        if v is not None and not SLUG_RE.match(v):
            raise ValueError("slug may only contain lowercase letters, digits and dashes")
        return v


class CompanyAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    max_users: int | None = Field(default=None, ge=1, le=10000)
    status: CompanyStatus | None = None


class CompanyAdminOut(ORM):
    id: int
    name: str
    slug: str
    status: str
    max_users: int
    user_count: int
    currency: str
    contact_email: str | None
    contact_phone: str | None
    whatsapp_connected: bool
    package_count: int
    open_tickets: int
    created_at: datetime


class SystemUserCreate(UserCreate):
    pass


class PlatformStats(BaseModel):
    companies: int
    active_companies: int
    users: int
    conversations: int
    tickets: int


# --- Company settings --------------------------------------------------------------


class CompanySettingsOut(ORM):
    id: int
    name: str
    slug: str
    status: str
    max_users: int
    currency: str
    contact_email: str | None
    contact_phone: str | None
    ai_agent_name: str
    ai_welcome_message: str | None
    ai_instructions: str
    knowledge_base: str
    whatsapp_phone_number_id: str | None
    whatsapp_display_number: str | None
    whatsapp_token_set: bool


class CompanySettingsUpdate(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    ai_agent_name: str | None = Field(default=None, min_length=1, max_length=80)
    ai_welcome_message: str | None = Field(default=None, max_length=1000)
    ai_instructions: str | None = Field(default=None, max_length=8000)
    knowledge_base: str | None = Field(default=None, max_length=30000)
    whatsapp_phone_number_id: str | None = Field(default=None, max_length=64)
    whatsapp_display_number: str | None = Field(default=None, max_length=50)
    # Write-only; send "" to remove the stored token.
    whatsapp_access_token: str | None = None


# --- Packages -------------------------------------------------------------------------


class PackageBase(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10000)
    duration_days: int = Field(ge=1, le=365)
    price_per_person: float = Field(ge=0)
    child_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    departure_dates: list[date] = []
    includes: list[str] = []
    excludes: list[str] = []
    tags: list[str] = []
    hotel_name: str | None = Field(default=None, max_length=200)
    hotel_stars: int | None = Field(default=None, ge=1, le=7)
    seats_available: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True
    is_featured: bool = False

    @field_validator("image_url")
    @classmethod
    def check_image_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("https://", "http://")):
            raise ValueError("image_url must start with https://")
        return v or None


class PackageIn(PackageBase):
    pass


class PackageOut(ORM):
    id: int
    title: str
    destination: str
    country: str
    description: str
    duration_days: int
    price_per_person: float
    child_price: float | None
    currency: str
    departure_dates: list[str]
    includes: list[str]
    excludes: list[str]
    tags: list[str]
    hotel_name: str | None
    hotel_stars: int | None
    seats_available: int | None
    image_url: str | None
    is_active: bool
    is_featured: bool
    created_at: datetime
    updated_at: datetime


# --- Conversations ----------------------------------------------------------------------


class CustomerOut(ORM):
    id: int
    name: str | None
    phone: str | None
    email: str | None
    whatsapp_id: str | None


class UserBrief(ORM):
    id: int
    full_name: str


class MessageOut(ORM):
    id: int
    sender: str
    kind: str
    content: str
    meta: dict | None
    author_name: str | None = None
    delivery_status: str | None
    created_at: datetime


class ConversationSummary(ORM):
    id: int
    channel: str
    status: str
    handover_reason: str | None
    customer: CustomerOut
    assigned_to: UserBrief | None
    created_at: datetime
    last_message_at: datetime
    last_message_preview: str = ""


class TicketBrief(ORM):
    id: int
    reference: str
    status: str


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]
    tickets: list[TicketBrief]


class AgentMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


# --- Tickets ------------------------------------------------------------------------------


class TicketOut(ORM):
    id: int
    reference: str
    status: str
    package_id: int | None
    package_title: str
    departure_date: str | None
    adults: int
    children: int
    lead_traveler_name: str
    contact_phone: str | None
    contact_email: str | None
    special_requests: str
    total_price: float
    currency: str
    internal_notes: str
    payment_reference: str | None
    created_by: str
    conversation_id: int | None
    customer: CustomerOut
    assigned_to: UserBrief | None
    created_at: datetime
    updated_at: datetime


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    assigned_to_id: int | None = None
    unassign: bool = False
    internal_notes: str | None = Field(default=None, max_length=10000)
    payment_reference: str | None = Field(default=None, max_length=200)
    total_price: float | None = Field(default=None, ge=0)


# --- Dashboard -------------------------------------------------------------------------------


class DashboardOut(BaseModel):
    conversations_by_status: dict[str, int]
    tickets_by_status: dict[str, int]
    pipeline_value: float
    confirmed_value: float
    currency: str
    packages_active: int
    users: int
    max_users: int
    conversations_waiting: int
    my_open_tickets: int


# --- Public storefront / web chat -------------------------------------------------------------


class PublicCompanyOut(BaseModel):
    name: str
    slug: str
    ai_agent_name: str
    welcome_message: str
    currency: str
    whatsapp_number: str | None
    contact_email: str | None
    contact_phone: str | None


class PublicPackageOut(ORM):
    id: int
    title: str
    destination: str
    country: str
    description: str
    duration_days: int
    price_per_person: float
    child_price: float | None
    currency: str
    departure_dates: list[str]
    includes: list[str]
    excludes: list[str]
    tags: list[str]
    hotel_name: str | None
    hotel_stars: int | None
    seats_available: int | None
    image_url: str | None
    is_featured: bool


class StartChatIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None


class PublicMessageOut(BaseModel):
    id: int
    sender: str
    content: str
    created_at: datetime


class StartChatOut(BaseModel):
    token: str
    status: str
    messages: list[PublicMessageOut]


class CustomerMessageIn(BaseModel):
    content: str = Field(min_length=1)


class ChatMessagesOut(BaseModel):
    status: str
    messages: list[PublicMessageOut]
