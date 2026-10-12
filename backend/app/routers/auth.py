from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import CompanyStatus, User, utcnow
from ..ratelimit import limiter
from ..schemas import ChangePasswordIn, DemoAccount, LoginIn, MeOut, TokenOut
from ..security import create_access_token, hash_password, revoke_sessions_now, verify_password
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


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    limiter.check(f"login:{ip}:{email}", 10, "Too many login attempts, try again in a minute")
    limiter.check(f"login-account:{email}", 30, "Too many login attempts for this account, try again later",
                  window=900)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
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
