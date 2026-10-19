"""Turn ORM objects into API schemas where computed fields are needed."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .branding import dashboard_branding
from .models import (
    Company,
    Conversation,
    Message,
    MessageKind,
    Sender,
    Ticket,
    TicketStatus,
    TravelPackage,
    User,
)
from .permissions import effective_permissions
from .schemas import (
    CompanyAdminOut,
    CompanyBrief,
    CompanySettingsOut,
    ConversationDetail,
    ConversationSummary,
    CustomerOut,
    MeOut,
    MessageOut,
    PublicMessageOut,
    TicketBrief,
    UserBrief,
    UserOut,
)

OPEN_TICKET_STATUSES = (TicketStatus.PENDING_PAYMENT, TicketStatus.IN_PROGRESS, TicketStatus.PAID)


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        permissions=effective_permissions(user),
        is_active=user.is_active,
        company_id=user.company_id,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def me_out(user: User) -> MeOut:
    company = None
    if user.company:
        c = user.company
        company = CompanyBrief(id=c.id, name=c.name, slug=c.slug, status=c.status, branding=dashboard_branding(c))
    return MeOut(**user_out(user).model_dump(), company=company)


def company_admin_out(db: Session, company: Company) -> CompanyAdminOut:
    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    return CompanyAdminOut(
        id=company.id,
        name=company.name,
        slug=company.slug,
        status=company.status,
        max_users=company.max_users,
        user_count=count(select(func.count(User.id)).where(User.company_id == company.id)),
        currency=company.currency,
        contact_email=company.contact_email,
        contact_phone=company.contact_phone,
        whatsapp_connected=bool(company.whatsapp_phone_number_id),
        whatsapp_phone_number_id=company.whatsapp_phone_number_id,
        package_count=count(select(func.count(TravelPackage.id)).where(TravelPackage.company_id == company.id)),
        open_tickets=count(
            select(func.count(Ticket.id)).where(
                Ticket.company_id == company.id, Ticket.status.in_(OPEN_TICKET_STATUSES)
            )
        ),
        created_at=company.created_at,
    )


def company_settings_out(company: Company, can_manage: bool = False) -> CompanySettingsOut:
    return CompanySettingsOut(
        id=company.id,
        name=company.name,
        slug=company.slug,
        status=company.status,
        max_users=company.max_users,
        currency=company.currency,
        contact_email=company.contact_email,
        contact_phone=company.contact_phone,
        ai_agent_name=company.ai_agent_name,
        ai_welcome_message=company.ai_welcome_message,
        ai_welcome_message_ar=company.ai_welcome_message_ar,
        ai_instructions=company.ai_instructions or "",
        knowledge_base=company.knowledge_base or "",
        whatsapp_phone_number_id=company.whatsapp_phone_number_id,
        whatsapp_display_number=company.whatsapp_display_number,
        whatsapp_token_set=bool(company.whatsapp_access_token),
        whatsapp_app_secret_set=bool(company.whatsapp_app_secret),
        whatsapp_webhook_path=f"/api/webhooks/whatsapp/c/{company.whatsapp_webhook_key}" if can_manage else None,
        whatsapp_verify_token=company.whatsapp_verify_token if can_manage else None,
    )


def message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        sender=m.sender,
        kind=m.kind,
        content=m.content,
        meta=m.meta,
        author_name=m.author.full_name if m.author else None,
        delivery_status=m.delivery_status,
        created_at=m.created_at,
    )


def public_message_out(m: Message) -> PublicMessageOut:
    cards = (m.meta or {}).get("cards") if m.sender == "ai" else None
    return PublicMessageOut(id=m.id, sender=m.sender, content=m.content, created_at=m.created_at,
                            cards=cards if isinstance(cards, list) else [])


def _last_preview(db: Session, conversation_id: int) -> str:
    content = db.scalar(
        select(Message.content)
        .where(
            Message.conversation_id == conversation_id,
            Message.kind == MessageKind.TEXT,
            Message.sender != Sender.SYSTEM,
        )
        .order_by(Message.id.desc())
        .limit(1)
    )
    return (content or "")[:140]


def conversation_summary(db: Session, c: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=c.id,
        channel=c.channel,
        status=c.status,
        handover_reason=c.handover_reason,
        customer=CustomerOut.model_validate(c.customer),
        assigned_to=UserBrief.model_validate(c.assigned_to) if c.assigned_to else None,
        created_at=c.created_at,
        last_message_at=c.last_message_at,
        last_message_preview=_last_preview(db, c.id),
    )


def conversation_detail(db: Session, c: Conversation) -> ConversationDetail:
    tickets = db.scalars(select(Ticket).where(Ticket.conversation_id == c.id).order_by(Ticket.id)).all()
    return ConversationDetail(
        **conversation_summary(db, c).model_dump(),
        messages=[message_out(m) for m in c.messages],
        tickets=[TicketBrief.model_validate(t) for t in tickets],
    )
