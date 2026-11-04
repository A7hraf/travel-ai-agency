"""System health (platform owner) and error reports from browsers.

* POST /api/client-errors: the web app reports a failed page or request (login optional, strictly
  rate limited, small bodies only).
* GET /api/system/health: version, database, webhook activity and error counts.
* GET /api/system/errors: the recorded errors, newest first.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import diagnostics
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..deps import require_system_admin
from ..models import Channel, Company, Conversation, ErrorEvent, Message, Sender, User
from ..netutil import client_ip
from ..ratelimit import limiter
from ..security import decode_access_token

router = APIRouter(prefix="/api", tags=["system health"])

MAX_CLIENT_ERROR_BYTES = 4096
CLIENT_ERRORS_PER_IP_PER_MINUTE = 20
CLIENT_ERRORS_PER_IP_PER_HOUR = 200
CLIENT_ERRORS_PER_USER_PER_MINUTE = 10


class ClientErrorIn(BaseModel):
    kind: Literal["error", "unhandledrejection", "crash", "api", "network", "bad_response", "poll"]
    message: str = Field(default="", max_length=1000)
    page: str | None = Field(default=None, max_length=500)
    api_path: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=10)
    status: int | None = Field(default=None, ge=0, le=999)
    build: str | None = Field(default=None, max_length=64)


def _optional_user_id(request: Request) -> int | None:
    """The reporter's account, when the request carries a valid login (never required)."""
    auth = request.headers.get("authorization") or ""
    if auth[:7].lower() != "bearer ":
        return None
    decoded = decode_access_token(auth[7:].strip())
    return decoded[0] if decoded else None


async def _read_small_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_CLIENT_ERROR_BYTES:
        raise HTTPException(413, "Error report too large")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_CLIENT_ERROR_BYTES:
            raise HTTPException(413, "Error report too large")
    return body


@router.post("/client-errors", status_code=204)
async def client_error(request: Request):
    ip = client_ip(request)
    too_many = "Too many error reports"
    limiter.check(f"client-errors-ip:{ip}", CLIENT_ERRORS_PER_IP_PER_MINUTE, too_many)
    limiter.check(f"client-errors-ip-hour:{ip}", CLIENT_ERRORS_PER_IP_PER_HOUR, too_many, window=3600)
    user_id = _optional_user_id(request)
    if user_id is not None:
        limiter.check(f"client-errors-user:{user_id}", CLIENT_ERRORS_PER_USER_PER_MINUTE, too_many)
    raw = await _read_small_body(request)
    try:
        body = ClientErrorIn.model_validate(json.loads(raw or b"{}"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "Invalid error report") from exc
    has_api = bool(body.api_path)
    diagnostics.record_error(
        "client",
        method=(body.method or "GET") if has_api else "PAGE",
        path=body.api_path if has_api else body.page,
        page=body.page,
        status=body.status,
        error_type=body.kind,
        message=body.message,
        user_id=user_id,
        release_name=f"web {body.build}" if body.build else None,
    )
    return Response(status_code=204)


# --- Owner: System health ------------------------------------------------------------------------

def _database_check() -> dict:
    started = time.perf_counter()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            dialect = db.get_bind().dialect.name
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "dialect": dialect,
                "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "dialect": None,
                "error": diagnostics.scrub(f"{type(exc).__name__}: {exc}")}


def _channel_activity(db: Session, channel: str, since: datetime) -> dict:
    base = select(func.count(Message.id)).join(Conversation, Message.conversation_id == Conversation.id).where(
        Conversation.channel == channel, Message.created_at >= since)
    incoming = db.scalar(base.where(Message.sender == Sender.CUSTOMER)) or 0
    replies = db.scalar(base.where(Message.sender.in_([Sender.AI, Sender.AGENT]), Message.kind == "text")) or 0
    failed = db.scalar(base.where(Message.delivery_status == "failed")) or 0
    last_in = db.scalar(
        select(func.max(Message.created_at)).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.channel == channel, Message.sender == Sender.CUSTOMER))
    column = Company.whatsapp_phone_number_id if channel == Channel.WHATSAPP else Company.instagram_account_id
    connected = db.scalar(select(func.count(Company.id)).where(column.is_not(None))) or 0
    return {"channel": channel, "incoming_24h": incoming, "replies_24h": replies, "failed_24h": failed,
            "last_incoming_at": last_in, "companies_connected": connected}


@router.get("/system/health")
def system_health(_: User = Depends(require_system_admin), db: Session = Depends(get_db)):
    from ..main import app  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    counts = dict(db.execute(
        select(ErrorEvent.source, func.coalesce(func.sum(ErrorEvent.count), 0))
        .where(ErrorEvent.last_seen_at >= since).group_by(ErrorEvent.source)).all())
    settings = get_settings()
    return {
        "version": app.version,
        "release": diagnostics.release(),
        "environment": settings.environment or "development",
        "started_at": diagnostics.STARTED_AT,
        "server_time": now,
        "database": _database_check(),
        "channels": [_channel_activity(db, Channel.WHATSAPP, since), _channel_activity(db, Channel.INSTAGRAM, since)],
        "errors_24h": {"server": int(counts.get("server", 0)), "client": int(counts.get("client", 0))},
    }


@router.get("/system/errors")
def list_errors(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    source: Literal["server", "client"] | None = None,
    company_id: int | None = None,
    limit: int = Query(default=300, ge=1, le=1000),
    _: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(ErrorEvent).where(ErrorEvent.last_seen_at >= since)
    if source:
        stmt = stmt.where(ErrorEvent.source == source)
    if company_id is not None:
        stmt = stmt.where(ErrorEvent.company_id == company_id)
    rows = db.scalars(stmt.order_by(ErrorEvent.last_seen_at.desc(), ErrorEvent.id.desc()).limit(limit)).all()
    names = dict(db.execute(select(Company.id, Company.name).where(
        Company.id.in_({r.company_id for r in rows if r.company_id is not None}))).all()) if rows else {}
    return [
        {"id": r.id, "created_at": r.created_at, "last_seen_at": r.last_seen_at, "source": r.source,
         "method": r.method, "path": r.path, "page": r.page, "status": r.status, "error_type": r.error_type,
         "message": r.message, "user_id": r.user_id, "company_id": r.company_id,
         "company_name": names.get(r.company_id), "release": r.release, "count": r.count}
        for r in rows
    ]


class DiagnosticTestError(RuntimeError):
    """Raised on purpose by the "Send a test error" button."""


@router.post("/system/health/test-error")
def test_error(me: User = Depends(require_system_admin)):
    """Fails on purpose, so the owner can check that errors of the live site reach this page."""
    limiter.check(f"test-error:{me.id}", 5, "Please wait a minute before sending another test error")
    raise DiagnosticTestError("Test error sent from the System health page")
