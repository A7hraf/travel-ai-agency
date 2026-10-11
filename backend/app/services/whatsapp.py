"""WhatsApp Cloud API (Meta) integration.

Each company connects its own WhatsApp Business phone number. Incoming webhooks are
routed to the right company by ``metadata.phone_number_id``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import get_settings
from ..models import Company

log = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4000  # WhatsApp allows 4096 characters per text message


class WhatsAppError(RuntimeError):
    pass


@dataclass
class IncomingMessage:
    phone_number_id: str
    wa_id: str
    message_id: str
    text: str
    profile_name: str | None


@dataclass
class StatusUpdate:
    message_id: str
    status: str  # sent, delivered, read, failed


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret:
        return True  # verification disabled (development)
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def _message_text(m: dict) -> str:
    kind = m.get("type")
    if kind == "text":
        return (m.get("text") or {}).get("body", "")
    if kind == "button":
        return (m.get("button") or {}).get("text", "")
    if kind == "interactive":
        inter = m.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return reply.get("title", "")
    if kind == "location":
        loc = m.get("location") or {}
        return f"[Location shared: {loc.get('name') or ''} {loc.get('address') or ''}]".strip()
    return f"[The customer sent a {kind} message that can't be read. Ask them to type their request.]"


def parse_webhook(payload: dict) -> tuple[list[IncomingMessage], list[StatusUpdate]]:
    messages: list[IncomingMessage] = []
    statuses: list[StatusUpdate] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []
            }
            for m in value.get("messages") or []:
                if not phone_number_id or not m.get("from") or not m.get("id"):
                    continue
                text = _message_text(m).strip()
                if not text:
                    continue
                messages.append(
                    IncomingMessage(
                        phone_number_id=phone_number_id,
                        wa_id=m["from"],
                        message_id=m["id"],
                        text=text,
                        profile_name=names.get(m["from"]),
                    )
                )
            for s in value.get("statuses") or []:
                if s.get("id") and s.get("status"):
                    statuses.append(StatusUpdate(message_id=s["id"], status=s["status"]))
    return messages, statuses


def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    parts: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


class WhatsAppSender(Protocol):
    def send_text(self, company: Company, to: str, text: str) -> str | None: ...

    def mark_read(self, company: Company, message_id: str) -> None: ...


class CloudAPISender:
    def _endpoint(self, company: Company) -> tuple[str, dict]:
        s = get_settings()
        token = company.whatsapp_access_token or s.whatsapp_default_access_token
        if not company.whatsapp_phone_number_id or not token:
            raise WhatsAppError("WhatsApp is not configured for this company")
        url = f"{s.whatsapp_graph_url}/{s.whatsapp_api_version}/{company.whatsapp_phone_number_id}/messages"
        return url, {"Authorization": f"Bearer {token}"}

    def send_text(self, company: Company, to: str, text: str) -> str | None:
        url, headers = self._endpoint(company)
        last_id = None
        for part in split_text(text):
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": part},
            }
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=20)
                resp.raise_for_status()
                last_id = (resp.json().get("messages") or [{}])[0].get("id")
            except (httpx.HTTPError, ValueError) as exc:
                detail = getattr(getattr(exc, "response", None), "text", "")
                raise WhatsAppError(f"WhatsApp send failed: {exc} {detail}".strip()) from exc
        return last_id

    def mark_read(self, company: Company, message_id: str) -> None:
        try:
            url, headers = self._endpoint(company)
            httpx.post(
                url,
                json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
                headers=headers,
                timeout=10,
            )
        except (WhatsAppError, httpx.HTTPError) as exc:
            log.info("Could not mark WhatsApp message as read: %s", exc)


_sender_override: WhatsAppSender | None = None


def set_whatsapp_sender(sender: WhatsAppSender | None) -> None:
    """Used by tests to capture outgoing messages."""
    global _sender_override
    _sender_override = sender


def get_whatsapp_sender() -> WhatsAppSender:
    return _sender_override or CloudAPISender()
