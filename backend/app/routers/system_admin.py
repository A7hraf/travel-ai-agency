"""Platform owner area: travel companies (tenants) and their account limits."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.health import check_ai
from ..branding import Branding, BrandingUpdate, apply_update, get_branding
from ..database import get_db
from ..deps import require_system_admin
from ..models import Company, CompanyStatus, Conversation, Role, Ticket, User
from ..ratelimit import limiter
from ..schemas import (
    AICheckOut,
    CompanyAdminOut,
    CompanyAdminUpdate,
    CompanyCreate,
    PlatformStats,
    SystemUserCreate,
    UserCreate,
    UserListOut,
    UserOut,
    UserUpdate,
)
from ..security import revoke_sessions_now
from ..serializers import company_admin_out, user_out
from ..services import plans as plans_service
from ..services.users import (
    create_company_user,
    delete_company_user,
    seats_used,
    update_company_user,
)

router = APIRouter(prefix="/api/system", tags=["system admin"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70] or "company"


def _unique_slug(db: Session, base: str) -> str:
    slug, n = base, 2
    while db.scalar(select(Company.id).where(Company.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def _get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


def _get_company_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.company_id is None or user.partner_id is not None:
        raise HTTPException(404, "User not found")
    return user


@router.get("/stats", response_model=PlatformStats)
def stats(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return PlatformStats(
        companies=db.scalar(select(func.count(Company.id))) or 0,
        active_companies=db.scalar(select(func.count(Company.id)).where(Company.status == CompanyStatus.ACTIVE)) or 0,
        users=db.scalar(select(func.count(User.id)).where(User.company_id.is_not(None),
                                                          User.partner_id.is_(None))) or 0,
        conversations=db.scalar(select(func.count(Conversation.id))) or 0,
        tickets=db.scalar(select(func.count(Ticket.id))) or 0,
    )


@router.post("/ai-check", response_model=AICheckOut)
def ai_check(me: User = Depends(require_system_admin)):
    """Send one real request to the AI provider and report the exact result."""
    limiter.check(f"ai-check:{me.id}", 6, "Please wait a minute before testing again")
    return check_ai()


@router.get("/companies", response_model=list[CompanyAdminOut])
def list_companies(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return [company_admin_out(db, c) for c in db.scalars(select(Company).order_by(Company.id)).all()]


@router.post("/companies", response_model=CompanyAdminOut, status_code=201)
def create_company(body: CompanyCreate, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    if body.slug:
        if db.scalar(select(Company.id).where(Company.slug == body.slug)):
            raise HTTPException(409, "This web address is already used by another company")
        slug = body.slug
    else:
        base = _slugify(body.name)
        if base == "company":
            raise HTTPException(422, "Please choose a web address in English letters for this company, "
                                     "for example sunrise-travel")
        slug = _unique_slug(db, base)

    # The company and its first admin are saved together: never a company without an admin.
    company = Company(
        name=body.name,
        slug=slug,
        max_users=body.max_users or 5,
        currency=body.currency.upper(),
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    plan = _plan_for_new_company(db, body.plan_id)
    db.add(company)
    try:
        db.flush()
        # The subscription first: the account limit follows the plan unless a limit was given.
        plans_service.start_subscription(db, company, plan, custom_max_users=body.max_users,
                                         cycle=body.billing_cycle)
        create_company_user(
            db,
            company,
            UserCreate(
                email=body.admin_email,
                full_name=body.admin_full_name,
                password=body.admin_password,
                role=Role.COMPANY_ADMIN,
            ),
            commit=False,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This web address is already used by another company") from exc
    except HTTPException:
        db.rollback()
        raise
    db.refresh(company)
    return company_admin_out(db, company)


def _plan_for_new_company(db: Session, plan_id: int | None):
    if plan_id is None:
        return None  # the default plan
    from ..models import Plan  # noqa: PLC0415

    plan = db.get(Plan, plan_id)
    if plan is None or plan.is_archived:
        raise HTTPException(400, "Choose a plan that is not archived")
    return plan


@router.get("/companies/{company_id}", response_model=CompanyAdminOut)
def get_company(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return company_admin_out(db, _get_company(db, company_id))


@router.patch("/companies/{company_id}", response_model=CompanyAdminOut)
def update_company(company_id: int, body: CompanyAdminUpdate, _: User = Depends(require_system_admin),
                   db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    if body.name is not None:
        company.name = body.name.strip()
    if body.max_users is not None:
        used = seats_used(db, company.id)
        if body.max_users < used:
            raise HTTPException(400, f"This company has {used} active accounts. Disable or delete some "
                                     f"before lowering the limit to {body.max_users}.")
        company.max_users = body.max_users
        # A limit typed here is this company's own limit (it no longer follows the plan).
        sub = plans_service.ensure_subscription(db, company)
        if sub is not None:
            sub.max_users_custom = True
    if body.whatsapp_phone_number_id is not None:
        number = body.whatsapp_phone_number_id.strip() or None
        if number and number != company.whatsapp_phone_number_id:
            plans_service.require_channel(db, company.id, "whatsapp")
        if number and db.scalar(select(Company.id).where(Company.whatsapp_phone_number_id == number,
                                                         Company.id != company.id)):
            raise HTTPException(409, "This WhatsApp number is already connected to another company")
        company.whatsapp_phone_number_id = number
    if body.status is not None:
        if body.status == CompanyStatus.SUSPENDED and company.status != CompanyStatus.SUSPENDED:
            # Log the staff out for good: reactivating the company must not revive old sessions.
            revoked = revoke_sessions_now()
            for user in db.scalars(select(User).where(User.company_id == company.id)):
                user.tokens_valid_after = revoked
        company.status = body.status
    db.commit()
    return company_admin_out(db, company)


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    db.delete(_get_company(db, company_id))
    db.commit()


@router.get("/companies/{company_id}/users", response_model=UserListOut)
def company_users(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    users = db.scalars(select(User).where(User.company_id == company.id, User.partner_id.is_(None))
                       .order_by(User.id)).all()
    return UserListOut(users=[user_out(u) for u in users], max_users=company.max_users,
                       used=seats_used(db, company.id))


@router.post("/companies/{company_id}/users", response_model=UserOut, status_code=201)
def create_user_for_company(company_id: int, body: SystemUserCreate, _: User = Depends(require_system_admin),
                            db: Session = Depends(get_db)):
    return user_out(create_company_user(db, _get_company(db, company_id), body))


@router.patch("/users/{user_id}", response_model=UserOut)
def update_any_user(user_id: int, body: UserUpdate, me: User = Depends(require_system_admin),
                    db: Session = Depends(get_db)):
    return user_out(update_company_user(db, _get_company_user(db, user_id), body, me))


@router.delete("/users/{user_id}", status_code=204)
def delete_any_user(user_id: int, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    delete_company_user(db, _get_company_user(db, user_id), me)


@router.get("/companies/{company_id}/branding", response_model=Branding)
def company_branding(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return get_branding(_get_company(db, company_id))


@router.patch("/companies/{company_id}/branding", response_model=Branding)
def update_company_branding(company_id: int, body: BrandingUpdate, _: User = Depends(require_system_admin),
                            db: Session = Depends(get_db)):
    """The platform owner can set everything, including the employee dashboard colours."""
    from .media import media_belongs_to

    company = _get_company(db, company_id)
    for url in body.image_urls():
        if not media_belongs_to(db, url, company.id):
            raise HTTPException(400, "Use an image uploaded for this company")
    branding = apply_update(company, body, allow_dashboard=True)
    db.commit()
    return branding



# --- AI training and WhatsApp of any company (same service functions as the company's own pages) ---

from ..ai import training as training_service  # noqa: E402
from ..schemas import (  # noqa: E402
    AIKnowledgeOut,
    AIKnowledgeUpdate,
    TrainingImportIn,
    TrainingImportOut,
    TrainingIn,
    TrainingOut,
    TryAIIn,
    TryAIOut,
    WhatsAppStatusOut,
    WhatsAppTestMessageIn,
    WhatsAppTestMessageOut,
    WhatsAppTestOut,
)
from ..services import whatsapp as whatsapp_service  # noqa: E402


@router.get("/companies/{company_id}/training", response_model=list[TrainingOut])
def company_training(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return training_service.list_examples(db, _get_company(db, company_id).id)


@router.post("/companies/{company_id}/training", response_model=TrainingOut, status_code=201)
def add_company_training(company_id: int, body: TrainingIn, _: User = Depends(require_system_admin),
                         db: Session = Depends(get_db)):
    return training_service.add_example(db, _get_company(db, company_id).id, body.question, body.answer)


@router.post("/companies/{company_id}/training/import", response_model=TrainingImportOut)
def import_company_training(company_id: int, body: TrainingImportIn, _: User = Depends(require_system_admin),
                            db: Session = Depends(get_db)):
    return training_service.import_examples(db, _get_company(db, company_id).id, body.text, body.preview)


@router.post("/companies/{company_id}/training/try", response_model=TryAIOut)
def try_company_ai(company_id: int, body: TryAIIn, me: User = Depends(require_system_admin),
                   db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    return training_service.try_ai(db, company, me.id, body.message, [t.model_dump() for t in body.history])


@router.get("/companies/{company_id}/training/knowledge", response_model=AIKnowledgeOut)
def company_knowledge(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return training_service.knowledge_out(db, _get_company(db, company_id))


@router.patch("/companies/{company_id}/training/knowledge", response_model=AIKnowledgeOut)
def update_company_knowledge(company_id: int, body: AIKnowledgeUpdate, _: User = Depends(require_system_admin),
                             db: Session = Depends(get_db)):
    return training_service.update_knowledge(db, _get_company(db, company_id), body.model_dump(exclude_unset=True))


@router.put("/companies/{company_id}/training/{example_id}", response_model=TrainingOut)
def update_company_training(company_id: int, example_id: int, body: TrainingIn,
                            _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    company = _get_company(db, company_id)
    return training_service.update_example(db, company.id, example_id, body.question, body.answer)


@router.delete("/companies/{company_id}/training/{example_id}", status_code=204)
def delete_company_training(company_id: int, example_id: int, _: User = Depends(require_system_admin),
                            db: Session = Depends(get_db)):
    training_service.delete_example(db, _get_company(db, company_id).id, example_id)


@router.get("/companies/{company_id}/whatsapp", response_model=WhatsAppStatusOut)
def company_whatsapp(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return whatsapp_service.connection_status(_get_company(db, company_id))


@router.post("/companies/{company_id}/whatsapp/test", response_model=WhatsAppTestOut)
def test_company_whatsapp(company_id: int, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return whatsapp_service.run_connection_test(_get_company(db, company_id), me.id)


@router.post("/companies/{company_id}/whatsapp/test-message", response_model=WhatsAppTestMessageOut)
def company_whatsapp_test_message(company_id: int, body: WhatsAppTestMessageIn,
                                  me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return whatsapp_service.send_test_whatsapp(_get_company(db, company_id), me.id, body.phone)


# --- Instagram Direct of any company ------------------------------------------------------------

from ..models import utcnow  # noqa: E402
from ..schemas import InstagramOwnerUpdate, InstagramStatusOut, InstagramTestOut  # noqa: E402
from ..services import instagram as instagram_service  # noqa: E402


@router.get("/companies/{company_id}/instagram", response_model=InstagramStatusOut)
def company_instagram(company_id: int, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return instagram_service.connection_status(_get_company(db, company_id))


@router.patch("/companies/{company_id}/instagram", response_model=InstagramStatusOut)
def update_company_instagram(company_id: int, body: InstagramOwnerUpdate, _: User = Depends(require_system_admin),
                             db: Session = Depends(get_db)):
    """The platform owner sets up a company's Instagram for it. Unlike the company itself, the owner may
    assign an account ID without Instagram's ownership check (only never one used by another company)."""
    company = _get_company(db, company_id)
    data = body.model_dump(exclude_unset=True)
    for secret in ("instagram_access_token", "instagram_app_secret"):
        if secret in data:
            setattr(company, secret, (data[secret] or "").strip() or None)
    if "instagram_access_token" in data:
        company.instagram_token_refreshed_at = utcnow() if company.instagram_access_token else None
    if "instagram_account_id" in data:
        account_id = (data["instagram_account_id"] or "").strip() or None
        if account_id and db.scalar(select(Company.id).where(Company.instagram_account_id == account_id,
                                                             Company.id != company.id)):
            raise HTTPException(409, "This Instagram account is already connected to another company")
        if account_id and account_id != company.instagram_account_id:
            plans_service.require_channel(db, company.id, "instagram")
        if account_id != company.instagram_account_id:
            company.instagram_username = None
        company.instagram_account_id = account_id
    if "instagram_username" in data:
        company.instagram_username = (data["instagram_username"] or "").strip().lstrip("@")[:100] or None
    try:
        db.commit()
    except IntegrityError as exc:  # the same account saved for another company at the same moment
        db.rollback()
        raise HTTPException(409, "This Instagram account is already connected to another company") from exc
    return instagram_service.connection_status(company)


@router.post("/companies/{company_id}/instagram/test", response_model=InstagramTestOut)
def test_company_instagram(company_id: int, me: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    result = instagram_service.run_connection_test(_get_company(db, company_id), me.id)
    db.commit()
    return result


# --- Demo company: a ready-made Omani agency with sample activity, for presentations ---------------

from typing import Literal  # noqa: E402

from pydantic import BaseModel as _DemoBase, EmailStr as _DemoEmail, Field as _DemoField  # noqa: E402
from pydantic import field_validator as _demo_validator  # noqa: E402

from ..schemas import RESERVED_SLUGS as _DEMO_RESERVED, SLUG_RE as _DEMO_SLUG_RE  # noqa: E402
from ..services import demo as demo_service  # noqa: E402

DEMO_LIMIT_PER_HOUR = 3


class DemoCompanyIn(_DemoBase):
    name: str = _DemoField(min_length=2, max_length=200)
    slug: str | None = _DemoField(default=None, max_length=80)
    include_activity: bool = True
    # Language of the package texts: both (English · Arabic), en or ar.
    language: Literal["both", "en", "ar"] = "both"
    # Kind of agency: a family travel agency, or a luxury travel & private concierge brand.
    profile: Literal["family", "luxury"] = "family"
    # Optional: the admin login uses this email instead of admin@<web address>.example.
    admin_email: _DemoEmail | None = None

    @_demo_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Enter the company name")
        return v

    @_demo_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        # Same rules as a normal company (CompanyCreate).
        v = (v or "").strip() or None
        if v is not None and not _DEMO_SLUG_RE.match(v):
            raise ValueError("The web address may only contain English lowercase letters, digits and dashes")
        if v in _DEMO_RESERVED:
            raise ValueError("This web address is reserved, choose another one")
        return v


class DemoLoginOut(_DemoBase):
    role: str
    label: str
    full_name: str
    email: str
    password: str


class DemoCompanyOut(_DemoBase):
    company: CompanyAdminOut
    logins: list[DemoLoginOut]
    customer_page: str
    counts: dict[str, int]


@router.post("/demo-company", response_model=DemoCompanyOut, status_code=201)
def create_demo_company(body: DemoCompanyIn, me: User = Depends(require_system_admin),
                        db: Session = Depends(get_db)):
    """Create a demo travel agency (packages, staff, trained answers and, optionally, 30 days of sample
    chats and bookings). The staff passwords are random and returned only in this response."""
    # Only demo companies really created count (a taken web address does not use up the limit).
    limit_key = f"demo-company:{me.id}"
    if limiter.blocked(limit_key, DEMO_LIMIT_PER_HOUR, window=3600):
        raise HTTPException(429, "You can create 3 demo companies per hour. Please try again later.")
    if body.slug:
        if db.scalar(select(Company.id).where(Company.slug == body.slug)):
            raise HTTPException(409, "This web address is already used by another company")
        slug = body.slug
    else:
        base = _slugify(body.name)
        slug = _unique_slug(db, "demo-travel" if base == "company" else base)
    try:
        result = demo_service.create_demo_company(
            db, body.name, slug, admin_email=str(body.admin_email) if body.admin_email else None,
            language=body.language, include_activity=body.include_activity,
            profile=body.profile)
        db.commit()
        limiter.hit(limit_key)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This web address is already used by another company") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(result.company)
    return DemoCompanyOut(
        company=company_admin_out(db, result.company),
        logins=[DemoLoginOut(**vars(login)) for login in result.logins],
        customer_page=f"/c/{result.company.slug}",
        counts=result.counts,
    )
