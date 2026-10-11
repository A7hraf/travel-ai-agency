"""WhatsApp Cloud API webhook. Point your Meta app's webhook to /api/webhooks/whatsapp."""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..config import get_settings
from ..services.conversations import process_whatsapp_payload
from ..services.whatsapp import verify_signature

router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["whatsapp"])


@router.get("", response_class=PlainTextResponse)
def verify(
    mode: str = Query(alias="hub.mode", default=""),
    token: str = Query(alias="hub.verify_token", default=""),
    challenge: str = Query(alias="hub.challenge", default=""),
):
    """Meta calls this once when you register the webhook."""
    if mode == "subscribe" and token == get_settings().whatsapp_verify_token:
        return challenge
    raise HTTPException(403, "Verification failed")


@router.post("")
async def receive(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403, "Invalid signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    # Answer Meta right away; the AI reply is generated in the background.
    background.add_task(process_whatsapp_payload, payload)
    return {"status": "received"}
