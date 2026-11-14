from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import CompanyStatus, Role, User
from .permissions import effective_permissions
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is None:
        raise unauthorized
    decoded = decode_access_token(creds.credentials)
    if decoded is None:
        raise unauthorized
    user_id, issued_ms = decoded
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    # A token older than the account belongs to a deleted user whose id was given out again
    # (SQLite reuses ids), so it must not log in as the new account.
    if user.created_at is not None and issued_ms < int(user.created_at.timestamp() * 1000):
        raise unauthorized
    # Suspension first: suspending also ends every session, but "suspended" says why.
    if user.company is not None and user.company.status != CompanyStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your company account is suspended")
    if user.partner is not None and not user.partner.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your business account is paused")
    if user.tokens_valid_after is not None and issued_ms < int(user.tokens_valid_after.timestamp() * 1000):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended, please log in again")
    return user


def require_system_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.SYSTEM_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System admin only")
    return user


def get_company_user(user: User = Depends(get_current_user)) -> User:
    """Staff of a travel company. Logins of business clients and vendors never pass here, so no staff
    area (inbox, customers, tickets, settings, uploads…) is open to them."""
    if user.company_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This area is for travel company accounts")
    if user.partner_id is not None or user.role == Role.PARTNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This area is for travel company staff")
    return user


def get_partner_user(user: User = Depends(get_current_user)) -> User:
    """A login of a business client or vendor whose account is on and whose travel company still has
    business accounts switched on."""
    from .b2b import b2b_settings  # noqa: PLC0415

    if user.partner_id is None or user.role != Role.PARTNER or user.partner is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This area is for business accounts")
    if user.partner.company_id != user.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This area is for business accounts")
    if not b2b_settings(user.company).enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Business accounts are switched off for this travel company")
    return user


def require_permission(*needed: str):
    def dependency(user: User = Depends(get_company_user)) -> User:
        perms = effective_permissions(user)
        missing = [p for p in needed if p not in perms]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {', '.join(missing)}")
        return user

    return dependency
