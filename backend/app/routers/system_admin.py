"""Platform owner area: travel companies (tenants) and their account limits."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_system_admin
from ..models import Company, CompanyStatus, Conversation, Role, Ticket, User
from ..schemas import (
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
from ..serializers import company_admin_out, user_out
from ..services.users import create_company_user, delete_company_user, seats_used, update_company_user

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
    if user is None or user.company_id is None:
        raise HTTPException(404, "User not found")
    return user


@router.get("/stats", response_model=PlatformStats)
def stats(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return PlatformStats(
        companies=db.scalar(select(func.count(Company.id))) or 0,
        active_companies=db.scalar(select(func.count(Company.id)).where(Company.status == CompanyStatus.ACTIVE)) or 0,
        users=db.scalar(select(func.count(User.id)).where(User.company_id.is_not(None))) or 0,
        conversations=db.scalar(select(func.count(Conversation.id))) or 0,
        tickets=db.scalar(select(func.count(Ticket.id))) or 0,
    )


@router.get("/companies", response_model=list[CompanyAdminOut])
def list_companies(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    return [company_admin_out(db, c) for c in db.scalars(select(Company).order_by(Company.id)).all()]


@router.post("/companies", response_model=CompanyAdminOut, status_code=201)
def create_company(body: CompanyCreate, _: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    if body.slug:
        if db.scalar(select(Company.id).where(Company.slug == body.slug)):
            raise HTTPException(409, "This slug is already used by another company")
        slug = body.slug
    else:
        slug = _unique_slug(db, _slugify(body.name))
    if db.scalar(select(User.id).where(User.email == body.admin_email.lower())):
        raise HTTPException(409, "An account with the admin email already exists")

    company = Company(
        name=body.name.strip(),
        slug=slug,
        max_users=body.max_users,
        currency=body.currency.upper(),
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    db.add(company)
    db.commit()
    create_company_user(
        db,
        company,
        UserCreate(
            email=body.admin_email,
            full_name=body.admin_full_name,
            password=body.admin_password,
            role=Role.COMPANY_ADMIN,
        ),
    )
    return company_admin_out(db, company)


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
        company.max_users = body.max_users
    if body.status is not None:
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
    users = db.scalars(select(User).where(User.company_id == company.id).order_by(User.id)).all()
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
