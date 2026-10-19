from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import CompanyStatus, User, utcnow
from ..netutil import client_ip
from ..ratelimit import limiter
from ..schemas import ChangePasswordIn, DemoAccount, LoginChoice, LoginChoicesOut, LoginIn, MeOut, TokenOut
from ..security import (
    create_access_token,
    hash_password,
    revoke_sessions_now,
    verify_password,
)
from ..seed import demo_accounts
from ..serializers import me_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/demo-accounts", response_model=list[DemoAccount])
def list_demo_accounts():
    """Demo logins for the login page, only on development setups with demo data."""
    s = get_settings()
    if not s.seed_demo_data or s.environment == "production":
        return []
    return demo_accounts()


# Checked when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password")


def _account_key(user: User) -> str:
    return user.company.slug if user.company is not None else "platform"


@router.post("/login", response_model=TokenOut | LoginChoicesOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    ip = client_ip(request)
    too_many = HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts, try again in a minute")
    limiter.check(f"login-ip:{ip}", 40, too_many.detail)
    # The per-email limits count failed attempts only, and the per-account one does not stop the
    # right password: otherwise anyone could lock a colleague (or the owner) out by guessing wrong.
    ip_email_key, account_key = f"login:{ip}:{email}", f"login-account:{email}"
    if limiter.blocked(ip_email_key, 10):
        raise too_many
    account_locked = limiter.blocked(account_key, 30, window=900)
    candidates = db.scalars(select(User).where(User.email == email).order_by(User.id)).all()
    if not candidates:
        verify_password(body.password, _DUMMY_HASH)
    # Only accounts whose password matches are ever mentioned, so nobody learns where an
    # email has accounts without knowing the password.
    matches = [u for u in candidates if verify_password(body.password, u.password_hash)]
    if body.account:
        matches = [u for u in matches if _account_key(u) == body.account]
    if not matches:
        limiter.hit(ip_email_key)
        limiter.hit(account_key)
        if account_locked:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many login attempts for this account, try again later")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    if len(matches) > 1:
        return LoginChoicesOut(choose=[
            LoginChoice(account=_account_key(u), company=u.company.name if u.company else None, role=u.role)
            for u in matches
        ])
    user = matches[0]
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    if user.company is not None and user.company.status != CompanyStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your company account is suspended")
    user.last_login_at = utcnow()
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=me_out(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return me_out(user)


@router.post("/change-password", response_model=TokenOut)
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Changes the password and logs out every other session; returns a fresh token for this one."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    user.tokens_valid_after = revoke_sessions_now()
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=me_out(user))


class ProfileUpdate(BaseModel):
    """Only the name and the login email can be changed here (never the role or permissions)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    # Needed to change the email: whoever has an open session must not take over the login.
    current_password: str | None = Field(default=None, max_length=200)


@router.patch("/profile", response_model=MeOut)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name is not None:
        name = body.full_name.strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter your name")
        user.full_name = name
    if body.email is not None:
        email = str(body.email).strip().lower()
        if email != user.email:
            if not body.current_password or not verify_password(body.current_password, user.password_hash):
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Enter your current password to change your email")
            # Unique within the same company (or among platform owner accounts).
            same_place = User.company_id.is_(None) if user.company_id is None else User.company_id == user.company_id
            taken = db.scalar(select(User.id).where(User.email == email, same_place, User.id != user.id))
            if taken:
                raise HTTPException(status.HTTP_409_CONFLICT, "Another account already uses this email")
            user.email = email
    db.commit()
    db.refresh(user)
    return me_out(user)


@router.post("/logout-others", response_model=TokenOut)
def logout_other_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ends every other session of this account; returns a fresh token for this one."""
    user.tokens_valid_after = revoke_sessions_now()
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=me_out(user))
