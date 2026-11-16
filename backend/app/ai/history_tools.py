"""AI tools about the customer's own trips: their bookings, a private link to their trips page (WhatsApp only,
where writing from the number proves who they are) and their feedback after a trip.

Each tool reads only the customer of this conversation, inside this company."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from .. import workflow
from ..models import Channel, Ticket
from ..services import customer_portal as portal

HISTORY_TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "send_my_trips_link",
            "description": "A private link (30 minutes, one use) to the customer's trips page: all their bookings, "
                           "chats and trip history. WhatsApp only. Put the link in your reply as it is.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_trip_feedback",
            "description": "Save the customer's rating (1-5) and comment about a finished trip, once they gave it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "Booking reference, e.g. TRV-AB12CD"},
                    "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                    "comment": {"type": "string"},
                },
                "required": ["reference", "rating"],
            },
        },
    },
]

CHECKIN_TOOL = {
    "type": "function",
    "function": {
        "name": "record_trip_checkin",
        "description": "Save what the traveller said when we asked how their trip is going. problem=true when "
                       "anything is wrong (the team is told at once).",
        "parameters": {"type": "object", "properties": {
            "reference": {"type": "string"}, "comment": {"type": "string"}, "problem": {"type": "boolean"}},
            "required": ["reference", "comment", "problem"]},
    },
}
HISTORY_TOOL_DEFINITIONS.append(CHECKIN_TOOL)
CHECKIN_ASK = ("We asked how their trip {items} is going: when they answer, call record_trip_checkin. If something "
               "is wrong, be caring, say our team is on it, and set problem to true.")

HISTORY_PROMPT = """
THE CUSTOMER'S OWN TRIPS
When the customer asks about their requests or bookings, call my_requests. {link_rule}
"""
LINK_WHATSAPP = ("For their full history (all bookings, chats, trip progress), call send_my_trips_link and give "
                 "them the link.")
LINK_OTHER = ("Their private trips page is opened from WhatsApp: on WhatsApp you can send them a link, or on the "
              "website they can open \"My trips\" with their WhatsApp number.")
FEEDBACK_ASK = ("Their trip {items} has ended and we have no feedback yet: at a natural moment, ask once how it "
                "was (a rating from 1 to 5 and a few words), then call record_trip_feedback.")


def history_prompt(ctx) -> str | None:
    if ctx.dry_run or not ctx.customer.id:
        return None
    text = HISTORY_PROMPT.format(link_rule=LINK_WHATSAPP if ctx.conversation.channel == Channel.WHATSAPP else LINK_OTHER)
    pending = portal.finished_without_feedback(ctx.db, ctx.customer, ctx.today)[:2]
    if pending:
        items = ", ".join(f"{t.reference} ({' '.join(t.package_title.split())[:80]})" for t in pending)
        text += FEEDBACK_ASK.format(items=items) + "\n"
    ongoing = ctx.db.scalars(select(Ticket).where(Ticket.company_id == ctx.company.id, Ticket.customer_id == ctx.customer.id,
                                                  Ticket.checkin.is_not(None))).all()
    asked = [t for t in ongoing if (t.checkin or {}).get("asked_at") and not (t.checkin or {}).get("answered_at")]
    if asked:
        text += CHECKIN_ASK.format(items=", ".join(f"{t.reference} ({' '.join(t.package_title.split())[:80]})" for t in asked[:2])) + "\n"
    return text


def send_my_trips_link(ctx, **_) -> dict:
    if ctx.dry_run:
        return {"simulated": True, "note": "Test chat: no link was made."}
    if ctx.conversation.channel != Channel.WHATSAPP or not ctx.customer.whatsapp_id:
        return {"error": "Links are sent only on WhatsApp. On the website, the customer opens \"My trips\" and "
                         "signs in with their WhatsApp number."}
    link = portal.make_link(ctx.db, ctx.company, ctx.customer)
    return {"link": link, "valid_minutes": portal.LINK_MINUTES, "note": "One use only. Never share it with others."}


def record_trip_feedback(ctx, reference="", rating=None, comment="", **_) -> dict:
    if ctx.dry_run or not ctx.customer.id:
        return {"simulated": True}
    ticket = ctx.db.scalar(select(Ticket).where(Ticket.company_id == ctx.company.id,
                                                Ticket.customer_id == ctx.customer.id,
                                                Ticket.reference == str(reference).strip().upper()))
    if ticket is None:
        return {"error": "No booking with this reference for this customer. Call my_requests."}
    try:
        portal.save_feedback(ctx.db, ctx.customer, ticket, int(rating), comment, "chat", ctx.today)
        ctx.db.flush()
        workflow.refresh(ctx.db, ticket, "Client (chat)", today=ctx.today)
    except (HTTPException, ValueError, TypeError) as exc:
        return {"error": str(getattr(exc, "detail", "The rating must be from 1 to 5."))}
    return {"saved": True, "next": "Thank the customer warmly."}


def record_trip_checkin(ctx, reference="", comment="", problem=False, **_) -> dict:
    from ..models import utcnow  # noqa: PLC0415
    from ..services.notifications import notify  # noqa: PLC0415

    if ctx.dry_run or not ctx.customer.id:
        return {"simulated": True}
    ticket = ctx.db.scalar(select(Ticket).where(Ticket.company_id == ctx.company.id,
                                                Ticket.customer_id == ctx.customer.id,
                                                Ticket.reference == str(reference).strip().upper()))
    if ticket is None or not ticket.checkin:
        return {"error": "No trip check-in for this reference. Call my_requests."}
    trouble = problem is True or str(problem).lower() == "true"
    ticket.checkin = {**ticket.checkin, "answered_at": utcnow().isoformat(), "comment": " ".join(str(comment).split())[:1000],
                      "problem": trouble}
    if trouble:
        notify(ctx.db, ticket, "client_problem", text=str(comment)[:200])
    return {"saved": True, "next": "Our team was told and will help right away." if trouble else "Wish them a great trip."}


HISTORY_HANDLERS = {
    "send_my_trips_link": send_my_trips_link,
    "record_trip_feedback": record_trip_feedback,
    "record_trip_checkin": record_trip_checkin,
}
