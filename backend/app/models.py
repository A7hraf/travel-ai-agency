"""Database tables.

Every business table carries a ``company_id`` so that each travel company (tenant)
only ever sees its own data. The only account without a company is the platform
owner (system admin).
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
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


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"


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

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    packages: Mapped[list["TravelPackage"]] = relationship(cascade="all, delete-orphan")
    customers: Mapped[list["Customer"]] = relationship(cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(cascade="all, delete-orphan")
    tickets: Mapped[list["Ticket"]] = relationship(cascade="all, delete-orphan")
    training_examples: Mapped[list["TrainingExample"]] = relationship(cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
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

    company: Mapped[Company | None] = relationship(back_populates="users")


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
    __table_args__ = (UniqueConstraint("company_id", "whatsapp_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    whatsapp_id: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


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

    customer: Mapped[Customer] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
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
    # WhatsApp message id, used to ignore duplicate webhook deliveries.
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
    created_by: Mapped[str] = mapped_column(String(20), default="ai")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship()
    package: Mapped[TravelPackage | None] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    conversation: Mapped[Conversation | None] = relationship()


class TrainingExample(Base):
    """A question and the company's approved answer. The AI uses the closest ones when it replies."""

    __tablename__ = "training_examples"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
