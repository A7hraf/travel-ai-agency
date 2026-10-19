"""WhatsApp Cloud API (Meta) integration.

Each company connects its own WhatsApp Business phone number. Incoming webhooks are
routed to the right company by ``metadata.phone_number_id``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
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


def verify_signature(raw_body: bytes, signature_header: str | None, secret: str | None) -> bool:
    """Checks Meta's X-Hub-Signature-256 header with the app secret.

    No secret: nothing to check; the webhook refuses that case unless unsigned webhooks
    are explicitly allowed (local development).
    """
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest().encode()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256=").encode("utf-8", "replace"))


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


def verify_phone_number(phone_number_id: str, token: str) -> bool:
    """True when Meta confirms that this access token may use this phone number.

    Proves that a company really owns the number it types in, so it can't take over
    another company's number (and its customers' messages).
    """
    return check_phone_number(phone_number_id, token, fields="id")["result"] == "connected"


# Results of check_phone_number, shown on the "Test connection" button.
CHECK_MESSAGES = {
    "connected": "Connected: Meta confirmed this phone number ID for this access token.",
    "token_invalid": "The access token is not valid or has expired. Create a permanent token in Meta "
                     "Business settings → System users and save it again.",
    "number_not_found": "Meta could not find this phone number ID. Copy it again from your Meta app → "
                        "WhatsApp → API Setup.",
    "no_access": "This access token has no access to this phone number. Give the system user access to the "
                 "WhatsApp Business account of this number.",
    "network": "Could not reach Meta (WhatsApp). Check the internet connection of the server and try again.",
    "not_configured": "Add the phone number ID and the access token first.",
}


def check_phone_number(phone_number_id: str, token: str,
                       fields: str = "id,display_phone_number,verified_name") -> dict:
    """Asks Meta whether this token may use this phone number. Returns {"result", "message",
    "display_number", "verified_name"}; result is one of CHECK_MESSAGES' keys."""
    if not phone_number_id or not token:
        return {"result": "not_configured", "message": CHECK_MESSAGES["not_configured"]}
    s = get_settings()
    try:
        resp = httpx.get(
            f"{s.whatsapp_graph_url}/{s.whatsapp_api_version}/{phone_number_id}",
            params={"fields": fields},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        log.info("Could not reach Meta to check WhatsApp number %s: %s", phone_number_id, exc)
        return {"result": "network", "message": CHECK_MESSAGES["network"]}
    try:
        data = resp.json()
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    if resp.status_code == 200 and str(data.get("id")) == str(phone_number_id):
        return {"result": "connected", "message": CHECK_MESSAGES["connected"],
                "display_number": data.get("display_phone_number"), "verified_name": data.get("verified_name")}
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    code = error.get("code")
    if resp.status_code == 401 or code in (190, 102):
        result = "token_invalid"
    elif code in (10, 200) or resp.status_code == 403:
        result = "no_access"
    elif resp.status_code >= 500:
        result = "network"
    else:
        result = "number_not_found"
    log.info("WhatsApp number check %s: HTTP %s %s", phone_number_id, resp.status_code, error.get("message"))
    return {"result": result, "message": CHECK_MESSAGES[result]}


def normalize_phone(text: str) -> str | None:
    """An international phone number as WhatsApp wants it (digits only, country code first),
    or None when it is not one: "+968 9123 4567" -> "96891234567"."""
    cleaned = re.sub(r"[\s\-().]", "", (text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    cleaned = cleaned.removeprefix("+")
    if not re.fullmatch(r"[1-9]\d{7,14}", cleaned):
        return None
    return cleaned


def connection_status(company: Company) -> dict:
    """How the company's WhatsApp is connected, for the settings page and the platform console.

    status: connected | not_connected | needs_app_secret | needs_token
    mode: own (the company's own Meta app) | platform (a number on the platform's Meta app) | none
    """
    s = get_settings()
    own = bool(company.whatsapp_access_token)
    platform_token = bool(s.whatsapp_default_access_token and s.whatsapp_share_default_token)
    if not company.whatsapp_phone_number_id:
        status, mode = "not_connected", "own" if own else "none"
    elif own:
        mode = "own"
        status = "connected" if company.whatsapp_app_secret else "needs_app_secret"
    else:
        mode = "platform"
        status = "connected" if platform_token else "needs_token"
    return {
        "status": status,
        "mode": mode,
        "phone_number_id": company.whatsapp_phone_number_id,
        "display_number": company.whatsapp_display_number,
        "token_set": own,
        "app_secret_set": bool(company.whatsapp_app_secret),
        "platform_available": platform_token,
        "webhook_path": f"/api/webhooks/whatsapp/c/{company.whatsapp_webhook_key}" if company.whatsapp_webhook_key else None,
        "verify_token": company.whatsapp_verify_token,
    }


def access_token_for(company: Company) -> str | None:
    """The company's own token, or the platform's shared one when the platform shares its app."""
    s = get_settings()
    if company.whatsapp_access_token:
        return company.whatsapp_access_token
    return s.whatsapp_default_access_token if s.whatsapp_share_default_token else None


class WhatsAppSender(Protocol):
    def send_text(self, company: Company, to: str, text: str) -> str | None: ...

    def mark_read(self, company: Company, message_id: str) -> None: ...


class CloudAPISender:
    def _endpoint(self, company: Company) -> tuple[str, dict]:
        s = get_settings()
        token = access_token_for(company)
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


# --- "Test connection" and "Send a test message" (settings page and platform console) -----

TEST_LIMIT_PER_MINUTE = 10
TEST_MESSAGE_LIMIT_PER_HOUR = 5
TEST_MESSAGE_TEXT = (
    "✅ Test message from {company}: your WhatsApp is connected to your AI travel consultant.\n"
    "✅ رسالة تجريبية من {company}: تم ربط واتساب بمستشار السفر الذكي."
)


def run_connection_test(company: Company, user_id: int) -> dict:
    from ..ratelimit import limiter

    limiter.check(f"wa-test:{user_id}", TEST_LIMIT_PER_MINUTE, "Please wait a minute before testing again")
    token = access_token_for(company)
    result = check_phone_number(company.whatsapp_phone_number_id or "", token or "")
    return {**result, "status": connection_status(company)}


def send_test_whatsapp(company: Company, user_id: int, phone: str) -> dict:
    from fastapi import HTTPException

    from ..ratelimit import limiter

    to = normalize_phone(phone)
    if to is None:
        raise HTTPException(400, "Enter the phone number with its country code, for example +968 9123 4567")
    if not company.whatsapp_phone_number_id or not access_token_for(company):
        raise HTTPException(400, "Connect WhatsApp first: add the phone number ID and the access token.")
    limiter.check(f"wa-test-msg:{user_id}", 2, "Please wait a minute before sending another test message")
    limiter.check(f"wa-test-msg-co:{company.id}", TEST_MESSAGE_LIMIT_PER_HOUR,
                  "Too many test messages. Please try again in an hour.", window=3600)
    try:
        get_whatsapp_sender().send_text(company, to, TEST_MESSAGE_TEXT.format(company=company.name))
    except WhatsAppError as exc:
        log.info("Test WhatsApp message of company %s failed: %s", company.id, exc)
        raise HTTPException(502, "WhatsApp did not send the test message. First send any message from this "
                                 "phone to your WhatsApp business number (Meta only allows replies within "
                                 "24 hours), then try again.") from exc
    return {"sent": True, "to": f"+{to}", "message": "Test message sent. Check WhatsApp on this phone."}
