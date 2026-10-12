"""Employee account rules shared by company admins and the system admin."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Company, Role, User
from ..permissions import COMPANY_ROLES, ROLE_DEFAULT_PERMISSIONS, clean_permissions
from ..schemas import UserCreate, UserUpdate
from ..security import hash_password, revoke_sessions_now


def seats_used(db: Session, company_id: int) -> int:
    return db.scalar(select(func.count(User.id)).where(User.company_id == company_id)) or 0


def _check_email_free(db: Session, email: str, exclude_user_id: int | None = None) -> None:
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None and existing.id != exclude_user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")


def _active_admins(db: Session, company_id: int) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.company_id == company_id, User.role == Role.COMPANY_ADMIN, User.is_active.is_(True)
        )
    ) or 0


def create_company_user(db: Session, company: Company, data: UserCreate) -> User:
    if data.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role for a company account")
    used = seats_used(db, company.id)
    if used >= company.max_users:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Account limit reached ({used}/{company.max_users}). Ask the platform admin to raise the limit.",
        )
    email = data.email.lower()
    _check_email_free(db, email)
    perms = ROLE_DEFAULT_PERMISSIONS[data.role] if data.permissions is None else clean_permissions(data.permissions)
    user = User(
        company_id=company.id,
        email=email,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        role=data.role,
        permissions=list(perms),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_company_user(db: Session, user: User, data: UserUpdate, acting_user: User) -> User:
    is_self = user.id == acting_user.id
    if data.role is not None and data.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role for a company account")
    if is_self and data.role is not None and data.role != user.role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't change your own role")
    if is_self and data.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't disable your own account")

    losing_admin = user.role == Role.COMPANY_ADMIN and user.is_active and (
        (data.role is not None and data.role != Role.COMPANY_ADMIN) or data.is_active is False
    )
    if losing_admin and _active_admins(db, user.company_id) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The company must keep at least one active admin")

    if data.email is not None:
        email = data.email.lower()
        _check_email_free(db, email, exclude_user_id=user.id)
        user.email = email
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.password:
        user.password_hash = hash_password(data.password)
        user.tokens_valid_after = revoke_sessions_now()
    if data.role is not None and data.role != user.role:
        user.role = data.role
        if data.permissions is None:
            user.permissions = list(ROLE_DEFAULT_PERMISSIONS[data.role])
    if data.permissions is not None:
        user.permissions = clean_permissions(data.permissions)
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


def delete_company_user(db: Session, user: User, acting_user: User) -> None:
    if user.id == acting_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete your own account")
    if user.role == Role.COMPANY_ADMIN and user.is_active and _active_admins(db, user.company_id) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The company must keep at least one active admin")
    db.delete(user)
    db.commit()
