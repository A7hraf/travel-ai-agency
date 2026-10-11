"""The logged-in employee's company: settings and dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_company_user, require_permission
from ..models import Company, Conversation, ConversationStatus, Ticket, TicketStatus, TravelPackage, User
from ..schemas import CompanySettingsOut, CompanySettingsUpdate, DashboardOut
from ..serializers import OPEN_TICKET_STATUSES, company_settings_out
from ..services.users import seats_used

router = APIRouter(prefix="/api", tags=["company"])


@router.get("/company", response_model=CompanySettingsOut)
def get_company(me: User = Depends(get_company_user)):
    return company_settings_out(me.company)


@router.patch("/company", response_model=CompanySettingsOut)
def update_company(body: CompanySettingsUpdate, me: User = Depends(require_permission("settings.manage")),
                   db: Session = Depends(get_db)):
    company = me.company
    data = body.model_dump(exclude_unset=True)

    if "whatsapp_phone_number_id" in data:
        number_id = (data.pop("whatsapp_phone_number_id") or "").strip() or None
        if number_id:
            taken = db.scalar(
                select(Company.id).where(Company.whatsapp_phone_number_id == number_id, Company.id != company.id)
            )
            if taken:
                raise HTTPException(409, "This WhatsApp number is already connected to another company")
        company.whatsapp_phone_number_id = number_id
    if "whatsapp_access_token" in data:
        token = (data.pop("whatsapp_access_token") or "").strip()
        company.whatsapp_access_token = token or None
    if data.get("currency"):
        data["currency"] = data["currency"].upper()
    for key, value in data.items():
        if key in ("ai_agent_name", "currency") and not value:
            continue  # required fields can't be blanked
        setattr(company, key, value)
    db.commit()
    return company_settings_out(company)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(me: User = Depends(require_permission("reports.view")), db: Session = Depends(get_db)):
    cid = me.company_id

    def grouped(model, column) -> dict[str, int]:
        rows = db.execute(select(column, func.count(model.id)).where(model.company_id == cid).group_by(column))
        return {str(k): v for k, v in rows}

    def total(statuses) -> float:
        value = db.scalar(
            select(func.coalesce(func.sum(Ticket.total_price), 0)).where(
                Ticket.company_id == cid, Ticket.status.in_(statuses)
            )
        )
        return float(value or 0)

    return DashboardOut(
        conversations_by_status=grouped(Conversation, Conversation.status),
        tickets_by_status=grouped(Ticket, Ticket.status),
        pipeline_value=total(OPEN_TICKET_STATUSES),
        confirmed_value=total([TicketStatus.CONFIRMED]),
        currency=me.company.currency,
        packages_active=db.scalar(
            select(func.count(TravelPackage.id)).where(TravelPackage.company_id == cid, TravelPackage.is_active)
        ) or 0,
        users=seats_used(db, cid),
        max_users=me.company.max_users,
        conversations_waiting=db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.company_id == cid,
                Conversation.status == ConversationStatus.HUMAN,
                Conversation.assigned_to_id.is_(None),
            )
        ) or 0,
        my_open_tickets=db.scalar(
            select(func.count(Ticket.id)).where(
                Ticket.company_id == cid, Ticket.assigned_to_id == me.id, Ticket.status.in_(OPEN_TICKET_STATUSES)
            )
        ) or 0,
    )
