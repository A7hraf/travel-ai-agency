"""Error capture for the owner's System health page.

Records unhandled server exceptions, 5xx answers, errors logged by the app (for example a WhatsApp
message that could not be processed in the background) and errors reported by browsers.

Privacy rules: never a request body, header, token, password or query string. Paths lose their
query string and any segment that looks like a key; messages are cut to 300 characters and scrubbed
of long tokens, key=value secrets and email addresses. A repeat of the same error within an hour only
raises its count. Rows older than 30 days, and beyond the newest 5000, are removed on insert.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

KEEP_DAYS = 30
MAX_ROWS = 5000
REPEAT_WINDOW = timedelta(hours=1)
MAX_MESSAGE = 300
MAX_PATH = 200
STARTED_AT = datetime.now(timezone.utc)

# --- Scrubbing -----------------------------------------------------------------------------------

_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_BEARER = re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{6,}")
_KEY_VALUE = re.compile(
    r"(?i)\b([\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|auth|session|"
    r"cookie|signature|access[_-]?key|private[_-]?key|credential)[\w-]*)(\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&}]+"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
# Long runs of key-like characters (API keys, access tokens, webhook keys, hashes).
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{24,}")
# Phone numbers (8 digits in Oman) and other long numbers (card numbers, ids of people).
_LONG_NUMBER = re.compile(r"\+?\d[\d \-]{6,}\d")
# user:password@ in connection addresses (database, SMTP, proxies).
_URL_PASSWORD = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Parts of database errors that quote the statement or its values.
_SQL_TAIL = re.compile(r"\s*\[(SQL|parameters|Background on this error)[^\]]*\].*", re.S)
_INPUT_VALUE = re.compile(r"input_value=.*?(?=, input_type=|\]|$)", re.S)


def _mask_email(m: re.Match) -> str:
    return f"{m.group(1)}***@{m.group(2)}"


def scrub(text: str | None, limit: int = MAX_MESSAGE) -> str:
    """A short, secret-free version of an error text."""
    if not text:
        return ""
    s = str(text)
    s = _SQL_TAIL.sub("", s)
    s = _INPUT_VALUE.sub("input_value=[hidden]", s)
    s = _URL_PASSWORD.sub(r"\1[hidden]@", s)
    s = _JWT.sub("[token]", s)
    s = _BEARER.sub(lambda m: f"{m.group(1)} [hidden]", s)
    s = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[hidden]", s)
    s = _EMAIL.sub(_mask_email, s)
    s = _LONG_TOKEN.sub(lambda m: m.group(0) if _looks_like_words(m.group(0)) else "[key]", s)
    s = _LONG_NUMBER.sub(lambda m: m.group(0) if _DATE.match(m.group(0)) else "[number]", s)
    s = " ".join(s.split())
    return s[: limit - 1] + "…" if len(s) > limit else s


_CAMEL = re.compile(r"^(?:[A-Z][a-z]{2,})+$")


def _looks_like_words(chunk: str) -> bool:
    """Long identifiers made of words (module paths, CamelCase error names) are kept; random keys are not."""
    if any(ch.isdigit() for ch in chunk):
        return False
    if _CAMEL.match(chunk):
        return True
    parts = [p for p in re.split(r"[_\-/.]", chunk) if p]
    return len(parts) > 1 and all(len(p) <= 16 for p in parts)


_SLUG = re.compile(r"^[a-z]{1,16}(?:[-_.][a-z0-9]{1,16})+$")
_SEGMENT_KEY = re.compile(r"^[A-Za-z0-9_\-=.~+]{16,}$")


def clean_path(path: str | None) -> str:
    """The path only: no query string or fragment, and key-like segments replaced by ":key"."""
    if not path:
        return ""
    p = str(path).split("?", 1)[0].split("#", 1)[0]
    if "://" in p:  # a full address: keep only the path
        p = "/" + p.split("://", 1)[1].partition("/")[2]
    segments = []
    for seg in p.split("/"):
        if "@" in seg:
            seg = ":email"
        elif _SEGMENT_KEY.match(seg) and (any(c.isdigit() for c in seg) or (len(seg) >= 20 and not _SLUG.match(seg))):
            seg = ":key"
        elif seg.isdigit() and len(seg) >= 7:
            seg = ":number"
        segments.append(seg)
    return "/".join(segments)[:MAX_PATH]


def release() -> str:
    """Which version runs: the commit the host built (Render sets RENDER_GIT_COMMIT), else the app version."""
    for name in ("RENDER_GIT_COMMIT", "GIT_COMMIT", "SOURCE_COMMIT", "COMMIT_SHA"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value[:12]
    from .main import app  # noqa: PLC0415

    return f"v{app.version}"


# --- Recording -----------------------------------------------------------------------------------

_busy = threading.local()


def _fingerprint(*parts) -> str:
    return hashlib.sha1("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def record_error(source: str, *, method: str | None = None, path: str | None = None, page: str | None = None,
                 status: int | None = None, error_type: str | None = None, message: str | None = None,
                 user_id: int | None = None, company_id: int | None = None, release_name: str | None = None) -> None:
    """Stores one error (or counts a repeat). Never raises: error capture must not cause errors."""
    if getattr(_busy, "on", False):
        return
    _busy.on = True
    try:
        _record(source, method, path, page, status, error_type, message, user_id, company_id, release_name)
    except Exception:  # noqa: BLE001
        log.debug("Could not record an error event", exc_info=True)
    finally:
        _busy.on = False


def _record(source, method, path, page, status, error_type, message, user_id, company_id, release_name) -> None:
    from .database import SessionLocal  # noqa: PLC0415
    from .models import ErrorEvent, User  # noqa: PLC0415

    path = clean_path(path) or None
    page = clean_path(page) or None
    message = scrub(message) or None
    error_type = scrub(error_type, 80) or None
    method = (method or "").upper()[:10] or None
    rel = (scrub(release_name, 64) if release_name else release()) or None
    now = datetime.now(timezone.utc)
    fp = _fingerprint(source, method, path, page if source == "client" else None, status, error_type,
                      (message or "")[:120], company_id)
    with SessionLocal() as db:
        if user_id is not None and company_id is None:
            user = db.get(User, user_id)
            if user is None:
                user_id = None
            else:
                company_id = user.company_id
                fp = _fingerprint(source, method, path, page if source == "client" else None, status, error_type,
                                  (message or "")[:120], company_id)
        recent = db.scalar(
            select(ErrorEvent).where(ErrorEvent.fingerprint == fp, ErrorEvent.last_seen_at >= now - REPEAT_WINDOW)
            .order_by(ErrorEvent.id.desc()).limit(1)
        )
        if recent is not None:
            recent.count = (recent.count or 1) + 1
            recent.last_seen_at = now
            db.commit()
            return
        db.add(ErrorEvent(created_at=now, last_seen_at=now, source=source, method=method, path=path, page=page,
                          status=status, error_type=error_type, message=message, user_id=user_id,
                          company_id=company_id, release=rel, count=1, fingerprint=fp))
        db.flush()
        _prune(db, now)
        db.commit()


def _prune(db, now: datetime) -> None:
    """Age, then a row cap per source: a flood of (anonymous) browser reports never pushes the
    server's own errors out of the list."""
    from .models import ErrorEvent  # noqa: PLC0415

    db.execute(delete(ErrorEvent).where(ErrorEvent.last_seen_at < now - timedelta(days=KEEP_DAYS)))
    for source in ("server", "client"):
        mine = ErrorEvent.source == source
        total = db.scalar(select(func.count(ErrorEvent.id)).where(mine)) or 0
        if total > MAX_ROWS:
            cutoff = db.scalar(select(ErrorEvent.id).where(mine).order_by(ErrorEvent.id.desc())
                               .offset(MAX_ROWS - 1).limit(1))
            if cutoff is not None:
                db.execute(delete(ErrorEvent).where(mine, ErrorEvent.id < cutoff))


# --- Server side: middleware and logging handler ---------------------------------------------------

def _user_from_scope(scope) -> int | None:
    """Only the user id is taken from the login token; the token itself is never stored."""
    from .security import decode_access_token  # noqa: PLC0415

    for key, value in scope.get("headers") or []:
        if key == b"authorization":
            raw = value.decode("latin-1")
            if raw[:7].lower() == "bearer ":
                decoded = decode_access_token(raw[7:].strip())
                return decoded[0] if decoded else None
    return None


class ErrorCapture:
    """ASGI middleware: records exceptions and 5xx answers of the API (then lets them through)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        status_box: dict[str, int] = {}

        async def send_watch(message):
            if message["type"] == "http.response.start":
                status_box["status"] = message["status"]
            await send(message)

        # The database write runs in a worker thread: a slow or unreachable database must never
        # hold up the event loop (and with it every other request).
        try:
            await self.app(scope, receive, send_watch)
        except Exception as exc:
            await run_in_threadpool(self._record, scope, status_box.get("status") or 500, type(exc).__name__,
                                    str(exc))
            raise
        status = status_box.get("status", 0)
        if status >= 500:
            await run_in_threadpool(self._record, scope, status, f"HTTP {status}", None)

    @staticmethod
    def _record(scope, status, error_type, message):
        try:
            user_id = _user_from_scope(scope)
        except Exception:  # noqa: BLE001
            user_id = None
        record_error("server", method=scope.get("method"), path=scope.get("path"), status=status,
                     error_type=error_type, message=message, user_id=user_id)


class ErrorLogHandler(logging.Handler):
    """Errors the app logs itself (log.exception in background work such as webhooks)."""

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_busy, "on", False) or record.name == __name__:
            return
        try:
            exc_type = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else "Logged error"
            text = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                text = f"{text}: {record.exc_info[1]}"
            record_error("server", method="LOG", path=record.name.replace(".", "/"), error_type=exc_type,
                         message=text)
        except Exception:  # noqa: BLE001
            pass


_handler: ErrorLogHandler | None = None


def install_log_handler() -> None:
    global _handler
    if _handler is None:
        _handler = ErrorLogHandler()
        logging.getLogger("app").addHandler(_handler)
