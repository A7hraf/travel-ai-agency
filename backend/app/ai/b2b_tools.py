"""AI tools for business clients writing from a WhatsApp number linked to their account.

They are offered only when the customer's number belongs to an active business client of this travel
company whose "Request trips by WhatsApp" feature is on; each handler checks that again, so a model
calling them in any other chat gets an error and nothing happens.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from ..b2b import effective_features
from ..models import Channel, Partner, PartnerKind, TripRequest, TripRequestStatus
from ..services import trip_requests as svc
from ..trip_schemas import CATEGORIES, TripRequestIn

B2B_TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_business_trip_request",
            "description": (
                "Send a business trip request of this business client to the travel team, after you summarised "
                "the details and the customer confirmed. The team finds options and sends them back here."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "origin": {"type": "string", "description": "Departure city (Muscat if not said)"},
                    "depart_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "travellers": {"type": "integer", "minimum": 1},
                    "traveller_names": {"type": "string", "description": "Full names, one per line"},
                    "needs": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)},
                              "description": "Parts to arrange"},
                    "purpose": {"type": "string", "description": "Reason of the trip (meeting, conference…)"},
                    "budget": {"type": "string"},
                    "notes": {"type": "string", "description": "Preferences: cabin class, hotel area, times…"},
                },
                "required": ["destination", "travellers", "needs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_business_trip_requests",
            "description": "The business client's recent trip requests with their status, and the numbered "
                           "options waiting for their choice.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "choose_business_trip_options",
            "description": "Record the customer's choice for a request waiting for their choice: one option "
                           "number per part, as listed by list_business_trip_requests. Confirm with the customer first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "Request reference, e.g. BR-AB12CD"},
                    "option_numbers": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["reference", "option_numbers"],
            },
        },
    },
]

B2B_PROMPT = """
BUSINESS CLIENT
This customer writes for {partner}, a business client of {company_name} (their WhatsApp number is linked to \
that account). For their business travel, do not search packages or create booking tickets. Instead:
1. Collect the destination, departure city, dates, number of travellers and their full names, the parts they \
need (flight, hotel, transport, activity, food), purpose, budget and preferences.
2. Summarise and ask them to confirm, then call create_business_trip_request and give them the reference.
3. Our team prepares up to 3 options for each part and sends them in this chat. When they ask about their \
requests or reply with option numbers, call list_business_trip_requests, confirm the choice, then call \
choose_business_trip_options. Our team then approves and books, and the booking reference is sent here.
"""


def business_client(ctx) -> Partner | None:
    """The active business client this WhatsApp chat writes for, when it may request trips here."""
    if ctx.dry_run or ctx.conversation.channel != Channel.WHATSAPP or not ctx.customer.partner_id:
        return None
    partner = ctx.db.get(Partner, ctx.customer.partner_id)
    if partner is None or partner.company_id != ctx.company.id or partner.kind != PartnerKind.CLIENT:
        return None
    return partner if "client.whatsapp" in effective_features(partner, ctx.company) else None


def b2b_prompt(ctx) -> str | None:
    partner = business_client(ctx)
    if partner is None:
        return None
    return B2B_PROMPT.format(partner=" ".join(partner.name.split())[:120], company_name=ctx.company.name)


def _no_access() -> dict:
    return {"error": "This chat is not linked to a business client account. Help the customer as usual."}


def _actor(ctx) -> svc.Actor:
    name = (ctx.customer.name or "").strip() or f"+{ctx.customer.whatsapp_id}"
    return svc.Actor("client", f"{name} (WhatsApp)")


def create_business_trip_request(ctx, **arguments) -> dict:
    partner = business_client(ctx)
    if partner is None:
        return _no_access()
    known = set(TripRequestIn.model_fields)
    try:
        data = TripRequestIn.model_validate({k: v for k, v in arguments.items() if k in known and v not in ("", None)})
    except ValidationError as exc:
        err = exc.errors()[0]
        return {"error": f"Check '{'.'.join(str(p) for p in err.get('loc', []))}': {err.get('msg')}"}
    try:
        req = svc.create_request(ctx.db, ctx.company, partner, data, _actor(ctx), "whatsapp",
                                 conversation_id=ctx.conversation.id)
    except HTTPException as exc:
        return {"error": str(exc.detail)}
    return {"created": True, "reference": req.reference,
            "next": "Our team prepares the options and sends them in this chat."}


def list_business_trip_requests(ctx, **_) -> dict:
    partner = business_client(ctx)
    if partner is None:
        return _no_access()
    reqs = ctx.db.scalars(select(TripRequest).where(TripRequest.company_id == ctx.company.id,
                                                    TripRequest.client_id == partner.id)
                          .order_by(TripRequest.created_at.desc()).limit(8)).all()
    out = []
    for r in reqs:
        item = {"reference": r.reference, "status": r.status, "destination": r.destination,
                "depart_date": r.depart_date.isoformat() if r.depart_date else None, "travellers": r.travellers}
        if r.status == TripRequestStatus.WITH_CLIENT:
            item["options_waiting_for_choice"] = [
                {"number": n, "part": o.category, "title": o.title, "provider": o.provider,
                 "price": float(o.price) if o.price is not None else None}
                for n, o in svc.numbered_options(r)]
        if r.status in (TripRequestStatus.BOOKED, TripRequestStatus.COMPLETED):
            item["booking_reference"] = r.booking_reference
        out.append(item)
    return {"requests": out, "currency": ctx.company.currency or "OMR"}


def choose_business_trip_options(ctx, reference="", option_numbers=None, **_) -> dict:
    partner = business_client(ctx)
    if partner is None:
        return _no_access()
    req = ctx.db.scalar(select(TripRequest).where(TripRequest.company_id == ctx.company.id,
                                                  TripRequest.client_id == partner.id,
                                                  TripRequest.reference == str(reference).strip().upper())
                        .with_for_update())
    if req is None:
        return {"error": "No request with this reference for this business. Call list_business_trip_requests."}
    numbered = dict(svc.numbered_options(req))
    try:
        ids = [numbered[int(n)].id for n in (option_numbers or [])]
    except (KeyError, ValueError, TypeError):
        return {"error": f"Option numbers must be between 1 and {len(numbered)}."}
    try:
        svc.choose(ctx.db, req, ids, _actor(ctx))
    except HTTPException as exc:
        return {"error": str(exc.detail)}
    return {"chosen": True, "reference": req.reference,
            "next": "Our team approves the choice and books it; the booking reference is sent here."}


B2B_HANDLERS = {
    "create_business_trip_request": create_business_trip_request,
    "list_business_trip_requests": list_business_trip_requests,
    "choose_business_trip_options": choose_business_trip_options,
}
