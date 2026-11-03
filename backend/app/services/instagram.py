"""Instagram Direct messages (Meta's "Instagram API with Instagram Login").

Each company connects its own Instagram professional account through its own Meta app:
* the access token (generated for the account in the app) sends the replies,
* the app secret signs the webhooks Meta posts to the company's own address
  /api/webhooks/instagram/c/<key>.

Webhook payload (object "instagram"):
    {"object": "instagram", "entry": [{"id": "<IG account id>", "time": ..., "messaging": [
        {"sender": {"id": "<IGSID>"}, "recipient": {"id": "<IG account id>"}, "timestamp": ...,
         "message": {"mid": "...", "text": "..."}}]}]}
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import httpx

from ..models import Company
from .whatsapp import split_text, verify_signature  # same Meta signature and the same text splitting

log = logging.getLogger(__name__)

__all__ = ["verify_signature"]

# Instagram allows 1000 characters per text message: longer replies are sent in several parts.
MAX_TEXT_LENGTH = 1000
DEFAULT_API_VERSION = "v23.0"


class InstagramError(RuntimeError):
    pass


def graph_url() -> str:
    return os.environ.get("INSTAGRAM_GRAPH_URL", "https://graph.instagram.com").rstrip("/")


def api_version() -> str:
    return os.environ.get("INSTAGRAM_API_VERSION", "").strip() or DEFAULT_API_VERSION


@dataclass
class IncomingDM:
    account_id: str  # the company's Instagram professional account (entry.id / recipient.id)
    igsid: str  # the customer (Instagram-scoped user id)
    message_id: str  # mid, used to ignore Meta's repeated deliveries
    text: str


@dataclass
class ReadReceipt:
    account_id: str
    igsid: str
    message_id: str  # the last message the customer has seen


# Attachments carry no text the AI can read: it is told so and asks the customer to type
# (the same as WhatsApp). Story mentions are not a question to the business and are ignored.
IGNORED_ATTACHMENTS = {"story_mention"}


def _message_text(message: dict) -> str:
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text
    quick = message.get("quick_reply") or {}
    if isinstance(quick, dict) and isinstance(quick.get("payload"), str) and quick["payload"].strip():
        return quick["payload"]
    attachments = [a for a in message.get("attachments") or [] if isinstance(a, dict)]
    kinds = [str(a.get("type") or "file") for a in attachments]
    if kinds and all(k in IGNORED_ATTACHMENTS for k in kinds):
        return ""
    if kinds or message.get("is_unsupported"):
        kind = next((k for k in kinds if k not in IGNORED_ATTACHMENTS), "unsupported")
        return (f"[The customer sent an Instagram {kind} message that can't be read. "
                "Ask them to type their request.]")
    return ""


def _id(party) -> str:
    return str(party.get("id") or "") if isinstance(party, dict) else ""


def parse_webhook(payload: dict) -> tuple[list[IncomingDM], list[ReadReceipt]]:
    """Customer messages and read receipts. Echoes (our own replies), reactions, edits, deletions,
    messages sent by the business itself and anything malformed are left out."""
    messages: list[IncomingDM] = []
    reads: list[ReadReceipt] = []
    if not isinstance(payload, dict):
        return messages, reads
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        account_id = str(entry.get("id") or "")
        for item in entry.get("messaging") or []:
            if not isinstance(item, dict):
                continue
            sender, recipient = _id(item.get("sender")), _id(item.get("recipient"))
            # Only messages a customer sent to this account: the recipient must be the account
            # of the entry, and the business never talks to itself.
            if not account_id or not sender or recipient != account_id or sender == account_id:
                continue
            message = item.get("message")
            if isinstance(message, dict):
                if message.get("is_echo") or message.get("is_deleted") or not message.get("mid"):
                    continue
                text = _message_text(message).strip()
                if text:
                    messages.append(IncomingDM(account_id, sender, str(message["mid"]), text))
                continue
            postback = item.get("postback")  # an ice-breaker or button the customer tapped
            if isinstance(postback, dict) and postback.get("mid") and str(postback.get("title") or "").strip():
                messages.append(IncomingDM(account_id, sender, str(postback["mid"]), str(postback["title"]).strip()))
                continue
            read = item.get("read")
            if isinstance(read, dict) and read.get("mid"):
                reads.append(ReadReceipt(account_id, sender, str(read["mid"])))
            # reaction, message_edit, referral...: nothing to answer
    return messages, reads


def split_message(text: str) -> list[str]:
    """Instagram's 1000-character limit, cut at line breaks or spaces when possible."""
    return split_text(text, MAX_TEXT_LENGTH)


# --- Connection check -------------------------------------------------------------------------

CHECK_MESSAGES = {
    "connected": "Connected: Instagram confirmed that this access token belongs to this account.",
    "token_invalid": "The access token is not valid or has expired. Generate a new token for your Instagram "
                     "account in your Meta app (Instagram → API setup with Instagram login) and save it again.",
    "account_mismatch": "This access token belongs to another Instagram account. Generate the token while "
                        "logged in to the account you want to connect, or correct the account ID.",
    "account_missing": "The access token works. Save the Instagram account ID it belongs to (shown below) to "
                       "finish connecting.",
    "no_access": "This access token is missing the Instagram messaging permission. Generate it again with "
                 "instagram_business_basic and instagram_business_manage_messages.",
    "network": "Could not reach Instagram. Check the internet connection of the server and try again.",
    "not_configured": "Add the Instagram access token first.",
}


def check_account(account_id: str | None, token: str | None) -> dict:
    """Asks Instagram which account this token belongs to (GET /me?fields=user_id,username).

    Returns {"result", "message", "user_id", "username"}; result is one of CHECK_MESSAGES' keys.
    "connected" only when the token's user_id is the account ID: a company can't connect an
    account its token does not prove it owns.
    """
    if not token:
        return {"result": "not_configured", "message": CHECK_MESSAGES["not_configured"]}
    try:
        resp = httpx.get(
            f"{graph_url()}/{api_version()}/me",
            params={"fields": "user_id,username"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        log.info("Could not reach Instagram to check an account: %s", exc)
        return {"result": "network", "message": CHECK_MESSAGES["network"]}
    try:
        data = resp.json()
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    if resp.status_code == 200 and data.get("user_id"):
        user_id, username = str(data["user_id"]), data.get("username")
        if not account_id:
            result = "account_missing"
        elif user_id == str(account_id):
            result = "connected"
        else:
            result = "account_mismatch"
        return {"result": result, "message": CHECK_MESSAGES[result], "user_id": user_id, "username": username}
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    code = error.get("code")
    if code in (10, 200) or resp.status_code == 403:
        result = "no_access"
    elif resp.status_code >= 500 or code in (1, 2, 4):
        result = "network"
    else:
        result = "token_invalid"
    log.info("Instagram account check: HTTP %s %s", resp.status_code, error.get("message"))
    return {"result": result, "message": CHECK_MESSAGES[result]}


def verify_account(account_id: str, token: str) -> dict | None:
    """The check result when Instagram confirms that the token belongs to this account, else None."""
    result = check_account(account_id, token)
    return result if result["result"] == "connected" else None


def connection_status(company: Company) -> dict:
    """status: connected | not_connected | needs_token | needs_app_secret."""
    if not company.instagram_account_id:
        status = "not_connected"
    elif not company.instagram_access_token:
        status = "needs_token"
    elif not company.instagram_app_secret:
        status = "needs_app_secret"
    else:
        status = "connected"
    key = company.instagram_webhook_key
    return {
        "status": status,
        "account_id": company.instagram_account_id,
        "username": company.instagram_username,
        "token_set": bool(company.instagram_access_token),
        "app_secret_set": bool(company.instagram_app_secret),
        "webhook_path": f"/api/webhooks/instagram/c/{key}" if key else None,
        "verify_token": company.instagram_verify_token,
    }


# --- Sending ------------------------------------------------------------------------------------


class InstagramSender(Protocol):
    def send_text(self, company: Company, igsid: str, text: str) -> str | None: ...

    def profile(self, company: Company, igsid: str) -> dict | None: ...


class GraphSender:
    def send_text(self, company: Company, igsid: str, text: str) -> str | None:
        token = company.instagram_access_token
        if not company.instagram_account_id or not token:
            raise InstagramError("Instagram is not connected for this company")
        url = f"{graph_url()}/{api_version()}/{company.instagram_account_id}/messages"
        last_id = None
        for part in split_message(text):
            try:
                resp = httpx.post(url, json={"recipient": {"id": igsid}, "message": {"text": part}},
                                  headers={"Authorization": f"Bearer {token}"}, timeout=20)
                resp.raise_for_status()
                last_id = resp.json().get("message_id") or last_id
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                detail = getattr(getattr(exc, "response", None), "text", "")
                raise InstagramError(f"Instagram send failed: {exc} {detail}".strip()) from exc
        return last_id

    def profile(self, company: Company, igsid: str) -> dict | None:
        if not company.instagram_access_token:
            return None
        try:
            resp = httpx.get(f"{graph_url()}/{api_version()}/{igsid}", params={"fields": "name,username"},
                             headers={"Authorization": f"Bearer {company.instagram_access_token}"}, timeout=5)
            data = resp.json() if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError) as exc:
            log.info("Could not read an Instagram profile: %s", exc)
            return None
        return data if isinstance(data, dict) else None


_sender_override: InstagramSender | None = None


def set_instagram_sender(sender: InstagramSender | None) -> None:
    """Used by tests to capture outgoing messages."""
    global _sender_override
    _sender_override = sender


def get_instagram_sender() -> InstagramSender:
    return _sender_override or GraphSender()


def profile_name(profile: dict | None) -> str | None:
    """"Omar Al Balushi", or "@omar.travels" when the customer has no name on Instagram."""
    if not profile:
        return None
    name = str(profile.get("name") or "").strip()
    username = str(profile.get("username") or "").strip()
    return (name or (f"@{username}" if username else ""))[:200] or None


# --- Keeping the token alive -----------------------------------------------------------------------

# Instagram's long-lived tokens stop working 60 days after they were made or last renewed.
REFRESH_AFTER = timedelta(days=20)


def refresh_token_if_due(company: Company) -> bool:
    """Renews the company's token (GET /refresh_access_token) once it is 20+ days old. Best effort:
    called after incoming messages, at most once an hour per company; the caller commits."""
    from ..models import utcnow
    from ..ratelimit import limiter

    token = company.instagram_access_token
    last = company.instagram_token_refreshed_at
    if not token or (last is not None and utcnow() - last < REFRESH_AFTER):
        return False
    if not limiter.allow(f"ig-refresh:{company.id}", 1, window=3600):
        return False
    try:
        resp = httpx.get(f"{graph_url()}/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=15)
        data = resp.json() if resp.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Could not renew the Instagram token of company %s: %s", company.id, exc)
        return False
    new_token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(new_token, str) or not new_token:
        log.info("Instagram did not renew the token of company %s (HTTP %s)", company.id, resp.status_code)
        return False
    company.instagram_access_token = new_token
    company.instagram_token_refreshed_at = utcnow()
    return True


# --- "Test connection" (settings page and platform console) ---------------------------------------

TEST_LIMIT_PER_MINUTE = 10


def run_connection_test(company: Company, user_id: int) -> dict:
    from ..ratelimit import limiter

    limiter.check(f"ig-test:{user_id}", TEST_LIMIT_PER_MINUTE, "Please wait a minute before testing again")
    result = check_account(company.instagram_account_id, company.instagram_access_token)
    if result["result"] == "connected" and result.get("username"):
        company.instagram_username = str(result["username"])[:100]  # caller commits
    return {**result, "status": connection_status(company)}
