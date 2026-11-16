"""After the client approves: payment proof, the booking checklist, and the travel documents.

- The client sends the transfer receipt (a photo or PDF) on WhatsApp or on their private trips page. It is kept
  with the request, privately, and the request waits for the team to check the payment.
- Once paid, the team ticks each booking step of the service (flights booked, hotel confirmed…).
- When everything is done, the team uploads the documents and sends them: on WhatsApp, and on the client's
  private trips page. The request is then confirmed.

Files are never public: only the company's staff and the client of that request can open them.
"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Channel, Company, Conversation, RequestFile, Ticket, TicketStatus as T, User, utcnow,
)
from .notify import say_in_chat
from .. import workflow
from .requests import QUOTING, _require, event

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 6_000_000
MAX_FILES_PER_REQUEST = 25
MAX_COMPANY_BYTES = 300_000_000
KINDS = ("payment_proof", "client_file", "document")
SIGNATURES = {
    "image/jpeg": lambda d: d[:3] == b"\xff\xd8\xff",
    "image/png": lambda d: d[:8] == b"\x89PNG\r\n\x1a\n",
    "image/webp": lambda d: d[:4] == b"RIFF" and d[8:12] == b"WEBP",
    "application/pdf": lambda d: d[:5] == b"%PDF-",
}
EXTENSION = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
# The client can send papers while the request is open; a payment proof once they approved the quotation.
CLIENT_FILE_STATUSES = (*QUOTING, T.PENDING_PAYMENT, T.IN_PROGRESS, T.PAID, T.WORKING)
PROOF_STATUSES = (T.PENDING_PAYMENT, T.IN_PROGRESS)
DOCS_STEP = "documents"  # the step "send all travel documents" is ticked by sending them
# Sending the travel documents finishes the team's steps before it (an unpaid payment is never passed).
SENDING_PASSES = frozenset({"intake", "review", "documents", "schedule", "booking", "task"})


def clean_name(name: str | None, content_type: str) -> str:
    """A safe file name: no folders, no odd characters, with the right extension."""
    base = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", (name or "").rsplit("/", 1)[-1]).strip(" .")[:120]
    ext = EXTENSION.get(content_type, "")
    if not base:
        base = "file"
    if ext and not base.lower().endswith(ext) and not (ext == ".jpg" and base.lower().endswith(".jpeg")):
        base += ext
    return base


def check_file(data: bytes, content_type: str) -> None:
    check = SIGNATURES.get(content_type)
    if check is None:
        raise HTTPException(415, "Only photos (JPEG, PNG, WebP) and PDF files are allowed")
    if not data:
        raise HTTPException(400, "The file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "The file is too large (maximum 6 MB)")
    if not check(data):
        raise HTTPException(415, "The file is not a real photo or PDF")


def store(db: Session, ticket: Ticket, kind: str, name: str | None, content_type: str, data: bytes, by: str) -> RequestFile:
    check_file(data, content_type)
    if len(ticket.files) >= MAX_FILES_PER_REQUEST:
        raise HTTPException(409, "This request already has the most files")
    used = db.scalar(select(func.coalesce(func.sum(RequestFile.size), 0)).where(
        RequestFile.company_id == ticket.company_id)) or 0
    if used + len(data) > MAX_COMPANY_BYTES:
        raise HTTPException(409, "File storage limit reached for this company")
    f = RequestFile(company_id=ticket.company_id, ticket_id=ticket.id, kind=kind, name=clean_name(name, content_type),
                    content_type=content_type, size=len(data), data=data, uploaded_by=by[:200])
    ticket.files.append(f)
    db.flush()
    return f


def file_response(f: RequestFile) -> Response:
    """The file itself, downloaded (never shown inside the page, never cached by shared caches)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f.name)[:120] or "file"
    return Response(content=f.data, media_type=f.content_type, headers={
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{safe}"',
    })


def file_out(f: RequestFile) -> dict:
    return {"id": f.id, "key": f.key, "kind": f.kind, "name": f.name, "content_type": f.content_type, "size": f.size,
            "uploaded_by": f.uploaded_by, "sent_at": f.sent_at, "created_at": f.created_at, "requirement": f.requirement}


# --- The client's files -------------------------------------------------------------------------------

def guess_requirement(ticket: Ticket, hint: str | None) -> str | None:
    """Which document a client file is, from its caption or name ("passport", "جواز"…), when it is clear."""
    from .request_desk import documents_view  # noqa: PLC0415

    words = set(re.findall(r"\w{4,}", (hint or "").lower()))
    if not words:
        return None
    found = [i["key"] for i in documents_view(ticket)["items"]
             if words & set(re.findall(r"\w{4,}", f"{i['key']} {i['label_en']} {i['label_ar']}".lower()))]
    return found[0] if len(found) == 1 else None


def client_upload(db: Session, ticket: Ticket, name: str | None, content_type: str, data: bytes,
                  actor: str = "Client", purpose: str = "auto", requirement: str | None = None,
                  hint: str | None = None) -> RequestFile:
    """A file from the client: one of the documents the service needs (passport copy…), or a payment receipt.
    `purpose` "auto" decides from the stage: after the quotation is approved a file is a receipt, unless its
    caption or name says which document it is. A receipt waits for the team to check it (a pending payment)."""
    from .request_desk import add_client_proof, documents_view  # noqa: PLC0415

    if ticket.status not in CLIENT_FILE_STATUSES:
        raise HTTPException(409, "This request is closed: files can't be added any more")
    if requirement and requirement not in {i["key"] for i in documents_view(ticket)["items"]}:
        raise HTTPException(422, "This service has no such document")
    if purpose == "auto" and not requirement:
        requirement = guess_requirement(ticket, hint) or guess_requirement(ticket, name)
    if purpose == "proof" or (purpose == "auto" and not requirement and ticket.status in PROOF_STATUSES):
        if ticket.status not in PROOF_STATUSES:
            raise HTTPException(409, "Send the payment receipt after approving the quotation")
        kind = "payment_proof"
    else:
        kind = "client_file"
    f = store(db, ticket, kind, name, content_type, data, "client")
    f.requirement = requirement if kind == "client_file" else None
    event(db, ticket, actor, kind, None, f.name + (f" ({requirement})" if f.requirement else ""))
    ticket.last_client_at = utcnow()
    if kind == "payment_proof":
        add_client_proof(db, ticket, f)
    workflow.refresh(db, ticket, actor)
    return f


def open_request_for(db: Session, company_id: int, customer_id: int) -> Ticket | None:
    """The request a file from this client belongs to: the newest waiting for payment, else the newest open one."""
    rows = db.scalars(select(Ticket).where(Ticket.company_id == company_id, Ticket.customer_id == customer_id,
                                           Ticket.status.in_(CLIENT_FILE_STATUSES))
                      .order_by(Ticket.created_at.desc())).all()
    for t in rows:
        if t.status in PROOF_STATUSES:
            return t
    return rows[0] if rows else None


def receive_whatsapp_file(db: Session, company: Company, conversation: Conversation, media: dict, caption: str) -> str:
    """Keeps a photo or PDF the client sent on WhatsApp with their open request. Returns what the AI reads
    in place of the message."""
    from .whatsapp import WhatsAppError, get_whatsapp_sender  # noqa: PLC0415

    what = "photo" if media.get("kind") == "image" else "file"
    tail = f" Their caption: {caption}" if caption else ""
    ticket = open_request_for(db, company.id, conversation.customer_id)
    if ticket is None:
        return (f"[The customer sent a {what}. It was not kept: they have no open request. Ask what it is for; "
                f"for a new trip, start a request first.]{tail}")
    try:
        data, mime = get_whatsapp_sender().download_media(company, media["id"], MAX_FILE_BYTES)
    except WhatsAppError as exc:
        log.info("Could not download a WhatsApp file for request %s: %s", ticket.reference, exc)
        return f"[The customer sent a {what} that could not be received (maybe too large). Ask them to send it again as a photo or PDF under 6 MB.]{tail}"
    content_type = mime or media.get("mime_type") or ""
    try:
        f = client_upload(db, ticket, media.get("filename") or f"{ticket.reference}-file", content_type, data, hint=caption)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return f"[The customer sent a {what}, but it could not be kept ({exc.detail}). Tell them kindly.]{tail}"
    from .requests import announce  # noqa: PLC0415

    if announce(db, company, ticket):
        tail = " The next step of the request was just sent to them in its own message: don't repeat it." + tail
    if f.kind == "payment_proof":
        return (f"[The customer sent a {what}: it was kept as the payment proof of request {ticket.reference}. "
                f"Thank them and say the team will check the payment and confirm.]{tail}")
    from .request_desk import documents_view  # noqa: PLC0415

    docs = documents_view(ticket)
    label = next((i["label_en"] for i in docs["items"] if i["key"] == f.requirement), None)
    missing = [i["label_en"] for i in docs["items"] if i["required"] and not i["done"]]
    return (f"[The customer sent a {what}: it was kept with request {ticket.reference}"
            + (f" as: {label}" if label else " for the team to sort") + "."
            + (f" Still missing: {', '.join(missing)}." if missing else " All the documents needed are in.") + f"]{tail}")


# --- The team's side ----------------------------------------------------------------------------------

def staff_upload(db: Session, ticket: Ticket, kind: str, name: str | None, content_type: str, data: bytes,
                 user: User) -> RequestFile:
    if kind not in KINDS:
        raise HTTPException(422, "Unknown kind of file")
    if ticket.status in (T.CANCELLED, T.REJECTED):
        raise HTTPException(409, "This request is closed: files can't be added any more")
    f = store(db, ticket, kind, name, content_type, data, user.full_name)
    event(db, ticket, user.full_name, "file_added", None, f.name, user)
    return f


def delete_file(db: Session, ticket: Ticket, file_id: int, user: User) -> None:
    f = next((x for x in ticket.files if x.id == file_id), None)
    if f is None:
        raise HTTPException(404, "File not found")
    if f.sent_at is not None:
        raise HTTPException(409, "This document was already sent to the client")
    event(db, ticket, user.full_name, "file_removed", None, f.name, user)
    ticket.files.remove(f)


def steps_of(ticket: Ticket) -> list[dict]:
    return [s for s in ((ticket.service.steps if ticket.service else None) or []) if isinstance(s, dict) and s.get("key")]


def checklist_view(ticket: Ticket) -> list[dict]:
    done = ticket.checklist if isinstance(ticket.checklist, dict) else {}
    return [{"key": s["key"], "label_en": s.get("label_en", ""), "label_ar": s.get("label_ar", ""),
             "done": s["key"] in done, "at": (done.get(s["key"]) or {}).get("at"), "by": (done.get(s["key"]) or {}).get("by")}
            for s in steps_of(ticket)]


def tick(db: Session, ticket: Ticket, step_key: str, done: bool, user: User) -> None:
    """A booking step done (or undone), before the documents go out."""
    _require(ticket, T.PAID, T.WORKING)
    step = next((s for s in steps_of(ticket) if s["key"] == step_key), None)
    if step is None or step_key == DOCS_STEP:
        raise HTTPException(404, "Step not found")
    current = dict(ticket.checklist) if isinstance(ticket.checklist, dict) else {}
    if done == (step_key in current):
        return
    if done:
        current[step_key] = {"at": utcnow().isoformat(), "by": user.full_name}
    else:
        current.pop(step_key, None)
    ticket.checklist = current  # a new dict, so the change is saved
    event(db, ticket, user.full_name, "step_done" if done else "step_undone", None, step.get("label_en") or step_key, user)
    workflow.refresh(db, ticket, user.full_name, user)


def send_documents(db: Session, company: Company, ticket: Ticket, note: str | None, user: User) -> int:
    """Sends the new documents to the client and confirms the request. Returns how many WhatsApp could not take
    (they stay on the client's private trips page)."""
    from .whatsapp import WhatsAppError, get_whatsapp_sender  # noqa: PLC0415

    _require(ticket, T.PAID, T.WORKING, T.CONFIRMED, T.COMPLETED)
    first_time = ticket.documents_sent_at is None
    if first_time and any(not s["done"] for s in checklist_view(ticket) if s["key"] != DOCS_STEP):
        raise HTTPException(409, "Tick every booking step first")
    if first_time:
        workflow.reach(db, ticket, "delivery", user.full_name, user, passing=SENDING_PASSES)
    docs = [f for f in ticket.files if f.kind == "document" and f.sent_at is None]
    if not first_time and not docs:
        raise HTTPException(409, "There are no new documents to send")
    now = utcnow()
    for f in docs:
        f.sent_at = now
    ticket.documents_sent_at = now
    if any(s["key"] == DOCS_STEP for s in steps_of(ticket)):
        ticket.checklist = {**(ticket.checklist or {}), DOCS_STEP: {"at": now.isoformat(), "by": user.full_name}}
    event(db, ticket, user.full_name, "documents_sent", None, ", ".join(f.name for f in docs) or "—", user)
    workflow.refresh(db, ticket, user.full_name, user)
    db.commit()

    lines = [f"*{ticket.reference}* is fully booked ✅ · تم حجز *{ticket.reference}* بالكامل ✅"]
    if docs:
        lines.append("Your travel documents · وثائق سفرك:")
        lines += [f"• {f.name}" for f in docs]
    if note and note.strip():
        lines.append(note.strip()[:800])
    lines.append("You can also open them any time on your private trips page (ask us for \"my trips\").\n"
                 "يمكنك فتحها في أي وقت من صفحة رحلاتك الخاصة (اكتب لنا «رحلاتي»).")
    say_in_chat(db, ticket.company_id, ticket.conversation_id, "\n".join(lines))

    failed = 0
    conv = db.get(Conversation, ticket.conversation_id) if ticket.conversation_id else None
    if docs and conv is not None and conv.channel == Channel.WHATSAPP and conv.customer.whatsapp_id:
        sender = get_whatsapp_sender()
        for f in docs:
            try:
                sender.send_file(company, conv.customer.whatsapp_id, f.data, f.content_type, f.name, f"{ticket.reference} · {f.name}")
            except (WhatsAppError, AttributeError) as exc:
                failed += 1
                log.info("Document %s of %s not sent on WhatsApp: %s", f.id, ticket.reference, exc)
    return failed
