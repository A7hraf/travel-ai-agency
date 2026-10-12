import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"


def _pw_bytes(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes (and bcrypt>=5 refuses longer input).
    return password.encode()[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    claims = {"sub": str(user_id), "iat": int(now.timestamp()), "iat_ms": int(now.timestamp() * 1000), "exp": expires}
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[int, int] | None:
    """(user id, issued-at in unix milliseconds) for a valid token, else None."""
    try:
        payload = jwt.decode(
            token, get_settings().secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub"]}
        )
        return int(payload["sub"]), int(payload.get("iat_ms") or int(payload["iat"]) * 1000)
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def revoke_sessions_now() -> datetime:
    """Value for User.tokens_valid_after: every token issued before this moment stops working."""
    return datetime.now(timezone.utc)


def random_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def ticket_reference() -> str:
    # No 0/O/1/I so customers can read it back over the phone.
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
    return "TRV-" + "".join(secrets.choice(alphabet) for _ in range(6))
