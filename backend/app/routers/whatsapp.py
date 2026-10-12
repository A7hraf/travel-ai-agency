"""WhatsApp Cloud API webhooks.

Two ways to connect, both supported at the same time:
* Shared platform app: every company's number is added to the platform owner's Meta app,
  which calls /api/webhooks/whatsapp. Messages are routed by the receiving number.
* Company's own Meta app: the company points its app to its own address
  /api/webhooks/whatsapp/c/<key> with its own verify token and app secret.
"""

import json
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Company
from ..services.conversations import process_whatsapp_payload
from ..services.whatsapp import verify_signature

router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["whatsapp"])


def _challenge(mode: str, token: str, challenge: str, expected: str | None) -> str:
    if mode == "subscribe" and expected and secrets.compare_digest(token.encode(), expected.encode()):
        return challenge
    raise HTTPException(403, "Verification failed")


async def _read_signed_payload(request: Request, app_secret: str | None) -> dict:
    if not app_secret and get_settings().environment == "production":
        # Without an app secret anybody could post fake WhatsApp messages.
        raise HTTPException(503, "WhatsApp app secret is not configured")
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), app_secret):
        raise HTTPException(403, "Invalid signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload")
    return payload


def _company_by_key(db: Session, key: str) -> Company:
    company = db.scalar(select(Company).where(Company.whatsapp_webhook_key == key)) if key else None
    if company is None:
        raise HTTPException(404, "Not found")
    return company


@router.get("", response_class=PlainTextResponse)
def verify(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta calls this once when the platform's webhook is registered."""
    return _challenge(mode, token, challenge, get_settings().whatsapp_verify_token)


@router.post("")
async def receive(request: Request, background: BackgroundTasks):
    payload = await _read_signed_payload(request, get_settings().whatsapp_app_secret)
    # Answer Meta right away; the AI reply is generated in the background.
    background.add_task(process_whatsapp_payload, payload)
    return {"status": "received"}


@router.get("/c/{key}", response_class=PlainTextResponse)
def verify_company(
    key: str,
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
    db: Session = Depends(get_db),
):
    company = _company_by_key(db, key)
    return _challenge(mode, token, challenge, company.whatsapp_verify_token)


@router.post("/c/{key}")
async def receive_company(key: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    company = _company_by_key(db, key)
    secret = company.whatsapp_app_secret or get_settings().whatsapp_app_secret
    payload = await _read_signed_payload(request, secret)
    background.add_task(process_whatsapp_payload, payload, company.id)
    return {"status": "received"}
