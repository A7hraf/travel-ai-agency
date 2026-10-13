"""Employee account rules shared by company admins and the system admin.

Rules that count accounts (the account limit, "keep at least one active admin") lock the company
row first, so two requests at the same moment cannot both pass the check.

An employee who is not a company admin but has the ``users.manage`` permission is a *delegate*:
they manage support and ticket accounts only, can only give permissions they have themselves,
and cannot touch company admins.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Company, Role, User
from ..permissions import (
    COMPANY_ROLES,
    ROLE_DEFAULT_PERMISSIONS,
    clean_permissions,
    effective_permissions,
)
from ..schemas import UserCreate, UserUpdate
from ..security import hash_password, revoke_sessions_now


def seats_used(db: Session, company_id: int) -> int:
    """Active accounts; disabled accounts don't use a seat."""
    return db.scalar(
        select(func.count(User.id)).where(User.company_id == company_id, User.is_active.is_(True))
    ) or 0


def _lock_company(db: Session, company_id: int) -> None:
    db.execute(select(Company.id).where(Company.id == company_id).with_for_update())


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


def _check_seat(db: Session, company: Company) -> None:
    used = seats_used(db, company.id)
    if used >= company.max_users:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Account limit reached ({used}/{company.max_users}). Ask the platform admin to raise the limit.",
        )


def _is_delegate(acting_user: User | None) -> bool:
    return acting_user is not None and acting_user.role not in (Role.COMPANY_ADMIN, Role.SYSTEM_ADMIN)


def _check_delegate_permissions(acting_user: User | None, permissions: list[str]) -> None:
    if not _is_delegate(acting_user):
        return
    extra = set(permissions) - set(effective_permissions(acting_user))
    if extra:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"You can only give permissions you have yourself (not: {', '.join(sorted(extra))})")


def create_company_user(db: Session, company: Company, data: UserCreate, acting_user: User | None = None,
                        commit: bool = True) -> User:
    if data.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role for a company account")
    if _is_delegate(acting_user) and data.role == Role.COMPANY_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a company admin can create admin accounts")
    perms = list(ROLE_DEFAULT_PERMISSIONS[data.role] if data.permissions is None
                 else clean_permissions(data.permissions))
    _check_delegate_permissions(acting_user, perms)
    password_hash = hash_password(data.password)  # slow: done before taking the lock

    _lock_company(db, company.id)
    _check_seat(db, company)
    email = data.email.lower()
    _check_email_free(db, email)
    user = User(
        company_id=company.id,
        email=email,
        full_name=" ".join(data.full_name.split()),
        password_hash=password_hash,
        role=data.role,
        permissions=perms,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # the same email created at the same moment
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from exc
    if commit:
        db.commit()
        db.refresh(user)
    return user


def update_company_user(db: Session, user: User, data: UserUpdate, acting_user: User) -> User:
    is_self = user.id == acting_user.id
    delegate = _is_delegate(acting_user)
    if data.role is not None and data.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role for a company account")
    if is_self and data.role is not None and data.role != user.role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't change your own role")
    if is_self and data.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't disable your own account")
    if is_self and data.permissions is not None and set(clean_permissions(data.permissions)) != set(
        effective_permissions(user)
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't change your own permissions")
    if delegate and not is_self and (user.role == Role.COMPANY_ADMIN or data.role == Role.COMPANY_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a company admin can manage admin accounts")
    if data.permissions is not None and not is_self:
        _check_delegate_permissions(acting_user, clean_permissions(data.permissions))
    if delegate and data.role is not None and data.permissions is None and data.role != user.role:
        _check_delegate_permissions(acting_user, list(ROLE_DEFAULT_PERMISSIONS[data.role]))
    password_hash = hash_password(data.password) if data.password else None

    _lock_company(db, user.company_id)
    db.refresh(user)
    losing_admin = user.role == Role.COMPANY_ADMIN and user.is_active and (
        (data.role is not None and data.role != Role.COMPANY_ADMIN) or data.is_active is False
    )
    if losing_admin and _active_admins(db, user.company_id) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The company must keep at least one active admin")
    if data.is_active and not user.is_active:
        _check_seat(db, user.company)

    if data.email is not None:
        email = data.email.lower()
        _check_email_free(db, email, exclude_user_id=user.id)
        user.email = email
    if data.full_name is not None:
        user.full_name = " ".join(data.full_name.split())
    if password_hash:
        user.password_hash = password_hash
        user.tokens_valid_after = revoke_sessions_now()
    if data.role is not None and data.role != user.role:
        user.role = data.role
        if data.permissions is None:
            user.permissions = list(ROLE_DEFAULT_PERMISSIONS[data.role])
    if data.permissions is not None and not is_self:
        user.permissions = clean_permissions(data.permissions)
    if data.is_active is not None and data.is_active != user.is_active:
        user.is_active = data.is_active
        if not data.is_active:
            user.tokens_valid_after = revoke_sessions_now()  # old logins stay dead after re-enabling
    db.commit()
    db.refresh(user)
    return user


def delete_company_user(db: Session, user: User, acting_user: User) -> None:
    if user.id == acting_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete your own account")
    if _is_delegate(acting_user) and user.role == Role.COMPANY_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a company admin can delete admin accounts")
    _lock_company(db, user.company_id)
    db.refresh(user)
    if user.role == Role.COMPANY_ADMIN and user.is_active and _active_admins(db, user.company_id) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The company must keep at least one active admin")
    db.delete(user)
    db.commit()
