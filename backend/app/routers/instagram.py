"""Instagram Direct webhooks (Instagram API with Instagram Login).

Every company has its own address /api/webhooks/instagram/c/<key>, with its own verify token,
and Meta signs each delivery with the company's own Meta app secret. There is no shared
platform address: each company connects its own Meta app (see services/instagram.py).
"""

import json
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Company
from ..services.conversations import process_instagram_payload
from ..services.instagram import verify_signature

router = APIRouter(prefix="/api/webhooks/instagram", tags=["instagram"])

MAX_BODY_BYTES = 1_000_000


def _company_by_key(db: Session, key: str) -> Company:
    company = db.scalar(select(Company).where(Company.instagram_webhook_key == key)) if key else None
    if company is None:
        raise HTTPException(404, "Not found")
    return company


@router.get("/c/{key}", response_class=PlainTextResponse)
def verify_company(
    key: str,
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
    db: Session = Depends(get_db),
):
    """Meta calls this once when the company saves the webhook in its app."""
    expected = _company_by_key(db, key).instagram_verify_token
    if mode == "subscribe" and expected and secrets.compare_digest(token.encode(), expected.encode()):
        return challenge
    raise HTTPException(403, "Verification failed")


@router.post("/c/{key}")
async def receive_company(key: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    company = _company_by_key(db, key)
    secret = company.instagram_app_secret
    if not secret:
        # Without the company's own app secret anybody could post fake Instagram messages.
        raise HTTPException(503, "Instagram app secret is not configured")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, "Payload too large")
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), secret):
        raise HTTPException(403, "Invalid signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid payload")
    # Answer Meta right away; the AI reply is generated in the background, for this company only.
    if payload.get("object") in (None, "instagram"):
        background.add_task(process_instagram_payload, payload, company.id)
    return {"status": "received"}
