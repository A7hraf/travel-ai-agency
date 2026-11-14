"""Database tables.

Every business table carries a ``company_id`` so that each travel company (tenant)
only ever sees its own data. The only account without a company is the platform
owner (system admin).
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .crypto import EncryptedText
from .database import Base
from .security import random_token


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every database (SQLite drops the timezone)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            # Always store UTC: naive values are UTC, aware values are converted.
            value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Role(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    COMPANY_ADMIN = "company_admin"
    SUPPORT = "support"
    TICKET_AGENT = "ticket_agent"
    # A login of a business client or vendor of a travel company (User.partner_id). Never staff: the
    # staff areas refuse it (deps.get_company_user) and it has no staff permissions.
    PARTNER = "partner"


class PartnerKind(StrEnum):
    CLIENT = "client"  # a business that requests travel for its people
    VENDOR = "vendor"  # a supplier agency that arranges flights, hotels, transport…


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"


class ConversationStatus(StrEnum):
    AI = "ai"  # the AI agent is answering
    HUMAN = "human"  # handed over to a company employee
    CLOSED = "closed"


class Sender(StrEnum):
    CUSTOMER = "customer"
    AI = "ai"
    AGENT = "agent"  # a company employee
    SYSTEM = "system"  # internal event, never shown to the customer


class MessageKind(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class TicketStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"  # created by the AI, waiting for an employee
    IN_PROGRESS = "in_progress"  # an employee is handling the payment
    PAID = "paid"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=CompanyStatus.ACTIVE)
    # Set by the system admin: how many employee accounts this company may have.
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    currency: Mapped[str] = mapped_column(String(3), default="OMR")
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))

    # AI persona for this company (same brain, different personality and knowledge)
    ai_agent_name: Mapped[str] = mapped_column(String(80), default="Sara")
    ai_welcome_message: Mapped[str | None] = mapped_column(Text)
    ai_welcome_message_ar: Mapped[str | None] = mapped_column(Text)
    ai_instructions: Mapped[str] = mapped_column(Text, default="")
    knowledge_base: Mapped[str] = mapped_column(Text, default="")

    # WhatsApp Cloud API: every company has its own channel (number + Meta app credentials).
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    whatsapp_access_token: Mapped[str | None] = mapped_column(EncryptedText())
    whatsapp_app_secret: Mapped[str | None] = mapped_column(EncryptedText())
    whatsapp_display_number: Mapped[str | None] = mapped_column(String(50))
    # The company's own webhook address (/api/webhooks/whatsapp/c/<key>) and verify token.
    whatsapp_webhook_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=lambda: random_token(18)
    )
    whatsapp_verify_token: Mapped[str | None] = mapped_column(String(64), default=lambda: random_token(18))

    # Instagram Direct (Instagram API with Instagram Login): the company's professional account and
    # its own Meta app. Messages arrive at /api/webhooks/instagram/c/<key>, signed with its app secret.
    instagram_account_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    instagram_username: Mapped[str | None] = mapped_column(String(100))
    instagram_access_token: Mapped[str | None] = mapped_column(EncryptedText())
    instagram_app_secret: Mapped[str | None] = mapped_column(EncryptedText())
    instagram_webhook_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=lambda: random_token(18)
    )
    instagram_verify_token: Mapped[str | None] = mapped_column(String(64), default=lambda: random_token(18))
    # Instagram tokens last 60 days: they are renewed automatically some weeks after this moment.
    instagram_token_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # Logo, colours and customer-page content (see app/branding.py).
    branding: Mapped[dict | None] = mapped_column(JSON)
    # Business accounts (clients and vendors), set by the platform owner only: on/off, limits and the
    # features the company may give (see app/b2b.py).
    b2b: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    # Deleting a company lets the database cascade (ON DELETE CASCADE) instead of loading every row.
    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan",
                                               passive_deletes=True)
    packages: Mapped[list["TravelPackage"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    customers: Mapped[list["Customer"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    conversations: Mapped[list["Conversation"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    tickets: Mapped[list["Ticket"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    training_examples: Mapped[list["TrainingExample"]] = relationship(cascade="all, delete-orphan",
                                                                      passive_deletes=True)
    media: Mapped[list["MediaFile"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    partners: Mapped[list["Partner"]] = relationship(back_populates="company", cascade="all, delete-orphan",
                                                     passive_deletes=True)


class User(Base):
    __tablename__ = "users"
    # One email may have an account in several companies (and the platform owner may test a
    # company with their own email), but only once per company and once on the platform.
    __table_args__ = (
        Index("uq_users_company_email", "company_id", "email", unique=True),
        Index("uq_users_platform_email", "email", unique=True,
              postgresql_where=text("company_id IS NULL"), sqlite_where=text("company_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    # Custom permission list (company admins always have every permission).
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Login tokens issued before this moment are rejected (set on password change).
    tokens_valid_after: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set for the logins of a business client or vendor (role "partner"); None for staff and the owner.
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"), index=True)

    company: Mapped[Company | None] = relationship(back_populates="users")
    partner: Mapped["Partner | None"] = relationship(back_populates="users")


class Partner(Base):
    """A business client or a vendor of one travel company. Belongs to that company only."""

    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    # Features the travel company gives this account (only those the platform owner allows count).
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    company: Mapped[Company] = relationship(back_populates="partners")
    users: Mapped[list["User"]] = relationship(back_populates="partner", passive_deletes=True)
    phones: Mapped[list["PartnerPhone"]] = relationship(cascade="all, delete-orphan", passive_deletes=True,
                                                        order_by="PartnerPhone.id")


class PartnerPhone(Base):
    """A WhatsApp number of a business client: messages from it are known to come from that business.
    One number belongs to one account per travel company."""

    __tablename__ = "partner_phones"
    __table_args__ = (UniqueConstraint("company_id", "phone", name="uq_partner_phones_company_phone"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20))  # digits only, country code first (as WhatsApp sends it)


class TravelPackage(Base):
    __tablename__ = "travel_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_days: Mapped[int] = mapped_column(Integer)
    # 3 decimals: the Omani rial has 1000 baisa.
    price_per_person: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    child_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3), default="OMR")
    # ISO dates (YYYY-MM-DD). Empty list means "flexible dates on request".
    departure_dates: Mapped[list[str]] = mapped_column(JSON, default=list)
    includes: Mapped[list[str]] = mapped_column(JSON, default=list)
    excludes: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    hotel_name: Mapped[str | None] = mapped_column(String(200))
    hotel_stars: Mapped[int | None] = mapped_column(Integer)
    seats_available: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "whatsapp_id"),
        Index("uq_customers_company_instagram", "company_id", "instagram_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    whatsapp_id: Mapped[str | None] = mapped_column(String(50))
    # Instagram-scoped user id (IGSID) of a customer who wrote to the company's Instagram account.
    instagram_id: Mapped[str | None] = mapped_column(String(64))
    # Staff notes and labels on the Customers page (business tools).
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    # The business client this customer writes for (their WhatsApp number is linked to it).
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    partner: Mapped["Partner | None"] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=ConversationStatus.AI, index=True)
    handover_reason: Mapped[str | None] = mapped_column(String(300))
    # Secret used by the web chat widget to continue the conversation.
    public_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_customer_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Stays true once the team was involved (for "handled fully by the AI" statistics).
    was_handed_over: Mapped[bool] = mapped_column(Boolean, default=False)
    # The last price the AI quoted in this chat (package, date, travellers, total). A booking must match
    # it, so the customer is never booked at a total they did not see (see ai/tools.py).
    booking_quote: Mapped[dict | None] = mapped_column(JSON)
    # When the AI first answered this chat in the current month: counts towards the plan's monthly
    # AI conversation limit (see services/plans.py). Indexed with company_id in migrations.py.
    ai_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    customer: Mapped[Customer] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id", passive_deletes=True
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), default=MessageKind.TEXT)
    content: Mapped[str] = mapped_column(Text, default="")
    # tool_call: {"tool_calls": [...]}, tool_result: {"tool_call_id": ..., "name": ...}
    meta: Mapped[dict | None] = mapped_column(JSON)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # WhatsApp message id or Instagram message id (mid), used to ignore duplicate webhook deliveries.
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    delivery_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship()


class Ticket(Base):
    """A booking request. The AI fills it in; an employee takes the payment."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    package_id: Mapped[int | None] = mapped_column(ForeignKey("travel_packages.id", ondelete="SET NULL"))
    package_title: Mapped[str] = mapped_column(String(200))
    departure_date: Mapped[str | None] = mapped_column(String(20))
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    lead_traveler_name: Mapped[str] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    special_requests: Mapped[str] = mapped_column(Text, default="")
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default=TicketStatus.PENDING_PAYMENT, index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    payment_reference: Mapped[str | None] = mapped_column(String(200))
    # Seats this booking holds on its package and departure date (taken when booked, given back when
    # cancelled or when an unpaid hold expires).
    seats_held: Mapped[int] = mapped_column(Integer, default=0)
    # When the seats were last taken. Unpaid bookings give them back after SEAT_HOLD_HOURS.
    seats_held_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[str] = mapped_column(String(20), default="ai")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship()
    package: Mapped[TravelPackage | None] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    conversation: Mapped[Conversation | None] = relationship()


class TicketEvent(Base):
    """History of a booking: every status, assignment, price, payment or note change, and who made it."""

    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(30))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class TrainingExample(Base):
    """A question and the company's approved answer. The AI uses the closest ones when it replies."""

    __tablename__ = "training_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class MediaFile(Base):
    """An uploaded image (logo, package photo, page banner). Kept in the database so it survives
    redeploys on hosts without a permanent disk."""

    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(30))
    size: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)



class PlatformSetting(Base):
    """A platform-wide setting the owner changed on the Platform settings page (AI brain, shared
    WhatsApp app). Overrides the environment variable of the same name; secrets are encrypted."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    secret_value: Mapped[str | None] = mapped_column(EncryptedText())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(200))


# --- Business tools: error capture (System health) and the staff activity log -------------------

class ErrorEvent(Base):
    """An unhandled server error, a 5xx answer, or an error a browser reported (System health page).

    Never holds request bodies, headers, tokens or query strings; messages are scrubbed of anything
    that looks like a secret (see app/diagnostics.py). Repeats within an hour only raise ``count``.
    """

    __tablename__ = "error_events"
    __table_args__ = (Index("ix_error_events_fingerprint_seen", "fingerprint", "last_seen_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(10))  # "server" or "client"
    method: Mapped[str | None] = mapped_column(String(10))
    path: Mapped[str | None] = mapped_column(String(200))
    # Client errors: the page the person was on (path only).
    page: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(String(300))
    # Plain ids (no foreign keys): an error report must never block deleting a user or company.
    user_id: Mapped[int | None] = mapped_column(Integer)
    company_id: Mapped[int | None] = mapped_column(Integer, index=True)
    release: Mapped[str | None] = mapped_column(String(64))
    count: Mapped[int] = mapped_column(Integer, default=1)
    fingerprint: Mapped[str] = mapped_column(String(40))


class AuditEvent(Base):
    """An important staff action (login, accounts, packages, bookings, design, AI, channels).
    Short texts only, never secrets. Shown on the company's Activity page and in the owner's console."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_company_time", "company_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"))
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(40), index=True)
    target: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


# --- Subscription plans (platform owner) ------------------------------------------------------------


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Plan(Base):
    """A plan of the platform's catalogue: prices in OMR and what a company on it may use.
    A limit of None means unlimited. Plans are archived, never deleted (companies keep them)."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_ar: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_ar: Mapped[str] = mapped_column(Text, default="")
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    features_ar: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    price_yearly: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    trial_days: Mapped[int] = mapped_column(Integer, default=14)
    max_users: Mapped[int] = mapped_column(Integer, default=5)
    max_packages: Mapped[int | None] = mapped_column(Integer)
    max_ai_conversations: Mapped[int | None] = mapped_column(Integer)  # per calendar month
    allow_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_instagram: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_page_editor: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_remove_powered_by: Mapped[bool] = mapped_column(Boolean, default=False)
    priority_support: Mapped[bool] = mapped_column(Boolean, default=False)
    # New companies start on the default plan (exactly one plan has it).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Subscription(Base):
    """A company's plan, billing cycle and paid period. Dates are the agency's local days
    (valid through the end date). Company.max_users follows the plan unless max_users_custom."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), unique=True, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    billing_cycle: Mapped[str] = mapped_column(String(10), default=BillingCycle.MONTHLY)
    status: Mapped[str] = mapped_column(String(20), default=SubscriptionStatus.ACTIVE)
    current_period_start: Mapped[date | None] = mapped_column(Date)
    current_period_end: Mapped[date | None] = mapped_column(Date)
    trial_end: Mapped[date | None] = mapped_column(Date)
    # Price per billing cycle agreed with this company (None: the plan's price).
    custom_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    max_users_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    plan: Mapped[Plan] = relationship(lazy="joined")


class SubscriptionPayment(Base):
    """A payment the platform owner received from a company (recorded by hand)."""

    __tablename__ = "subscription_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(String(3), default="OMR")
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(20))  # bank_transfer, card, cash
    reference: Mapped[str] = mapped_column(String(200), default="")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    # Plan and cycle at the time of the payment (shown on the invoice even after a plan change).
    plan_name: Mapped[str] = mapped_column(String(100), default="")
    billing_cycle: Mapped[str] = mapped_column(String(10), default=BillingCycle.MONTHLY)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
