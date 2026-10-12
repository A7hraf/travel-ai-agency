"""Tools the AI agent can call.

Every tool runs inside a ``ToolContext`` bound to one company and one conversation,
so the model can never read or book another company's packages, whatever it asks for.
Prices are always computed here, never taken from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Company,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageKind,
    Sender,
    Ticket,
    TicketStatus,
    TravelPackage,
)
from ..security import ticket_reference
from .text import keywords, normalize

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_packages",
            "description": (
                "Search the agency's travel packages. Use it before recommending any trip. "
                "All filters are optional; call with no arguments to see everything on offer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords: destination, country or trip type, e.g. 'Maldives honeymoon', "
                        "'Turkey family', 'Umrah'. Prefer English place names.",
                    },
                    "max_price_per_person": {"type": "number", "description": "Budget per person."},
                    "min_days": {"type": "integer", "description": "Minimum trip length in days."},
                    "max_days": {"type": "integer", "description": "Maximum trip length in days."},
                    "departure_month": {
                        "type": "string",
                        "description": "Month the customer wants to leave, as YYYY-MM.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_package_details",
            "description": "Get full details of one package: itinerary description, inclusions, "
            "exclusions, hotel and departure dates.",
            "parameters": {
                "type": "object",
                "properties": {"package_id": {"type": "integer"}},
                "required": ["package_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking_ticket",
            "description": (
                "Create the booking ticket once the customer has confirmed the summary. This hands the "
                "booking to a human employee who will contact the customer for payment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "integer"},
                    "departure_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "adults": {"type": "integer", "minimum": 1},
                    "children": {"type": "integer", "minimum": 0},
                    "lead_traveler_name": {"type": "string"},
                    "contact_phone": {"type": "string"},
                    "contact_email": {"type": "string"},
                    "special_requests": {"type": "string"},
                },
                "required": ["package_id", "departure_date", "adults", "lead_traveler_name", "contact_phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_agent",
            "description": "Hand the conversation to a human employee (customer asks for a person, "
            "complaint, changes to an existing booking, or anything you cannot handle).",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string", "description": "Short reason for the employee."}},
                "required": ["reason"],
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOL_DEFINITIONS}

MAX_RESULTS = 5


@dataclass
class ToolContext:
    db: Session
    company: Company
    conversation: Conversation
    customer: Customer
    today: date

    # set when a tool handed the conversation over to a human
    handed_over: bool = False
    ticket_reference: str | None = None


def _money(value: Decimal | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if value == int(value) else float(value)


def _upcoming_dates(pkg: TravelPackage, today: date) -> list[str]:
    return sorted(d for d in (pkg.departure_dates or []) if d >= today.isoformat())


def is_bookable(pkg: TravelPackage, today: date) -> bool:
    if not pkg.is_active:
        return False
    if pkg.seats_available is not None and pkg.seats_available <= 0:
        return False
    # Packages with fixed dates that have all passed are no longer bookable.
    if pkg.departure_dates and not _upcoming_dates(pkg, today):
        return False
    return True


def _summary(pkg: TravelPackage, today: date) -> dict:
    return {
        "id": pkg.id,
        "title": pkg.title,
        "destination": pkg.destination,
        "country": pkg.country,
        "duration_days": pkg.duration_days,
        "price_per_person": _money(pkg.price_per_person),
        "child_price": _money(pkg.child_price),
        "currency": pkg.currency,
        "next_departures": _upcoming_dates(pkg, today)[:6] or "flexible, on request",
        "hotel": f"{pkg.hotel_name} ({pkg.hotel_stars}*)" if pkg.hotel_name and pkg.hotel_stars else pkg.hotel_name,
        "tags": pkg.tags or [],
        "seats_left": pkg.seats_available,
    }


def _company_packages(ctx: ToolContext) -> list[TravelPackage]:
    rows = ctx.db.scalars(select(TravelPackage).where(TravelPackage.company_id == ctx.company.id))
    return [p for p in rows if is_bookable(p, ctx.today)]


def _get_package(ctx: ToolContext, package_id) -> TravelPackage | None:
    try:
        pid = int(package_id)
    except (TypeError, ValueError):
        return None
    pkg = ctx.db.get(TravelPackage, pid)
    if pkg is None or pkg.company_id != ctx.company.id:
        return None
    return pkg


def search_packages(ctx: ToolContext, query: str = "", max_price_per_person=None, min_days=None,
                    max_days=None, departure_month: str | None = None, **_) -> dict:
    packages = _company_packages(ctx)
    # Only a well-formed YYYY-MM month filters; anything else ("November") is ignored.
    month = departure_month if departure_month and re.fullmatch(r"\d{4}-\d{2}", departure_month) else None

    def passes_filters(p: TravelPackage) -> bool:
        try:
            if max_price_per_person not in (None, "") and p.price_per_person > Decimal(str(max_price_per_person)):
                return False
            if min_days not in (None, "") and p.duration_days < int(min_days):
                return False
            if max_days not in (None, "") and p.duration_days > int(max_days):
                return False
        except (ValueError, ArithmeticError):
            pass
        if month and p.departure_dates:
            if not any(d.startswith(month) for d in _upcoming_dates(p, ctx.today)):
                return False
        return True

    filtered = [p for p in packages if passes_filters(p)]
    tokens = keywords(query or "")
    if tokens:
        scored = []
        for p in filtered:
            haystack = normalize(" ".join(
                [p.title, p.destination, p.country, p.description or "", p.hotel_name or "", " ".join(p.tags or [])]
            ))
            place = normalize(f"{p.destination} {p.country} {' '.join(p.tags or [])}")
            score = sum(1 for t in tokens if t in haystack) + sum(2 for t in tokens if t in place)
            if score:
                scored.append((score, p))
        scored.sort(key=lambda sp: (-sp[0], not sp[1].is_featured, sp[1].price_per_person))
        matches = [p for _, p in scored]
    else:
        matches = sorted(filtered, key=lambda p: (not p.is_featured, p.price_per_person))

    if matches:
        return {"results": [_summary(p, ctx.today) for p in matches[:MAX_RESULTS]], "total_matches": len(matches)}

    alternatives = sorted(packages, key=lambda p: (not p.is_featured, p.price_per_person))[:3]
    return {
        "results": [],
        "note": "No package matches these criteria. Tell the customer honestly and suggest the "
        "alternatives below, or offer a human consultant for a custom trip.",
        "alternatives": [_summary(p, ctx.today) for p in alternatives],
    }


def get_package_details(ctx: ToolContext, package_id=None, **_) -> dict:
    pkg = _get_package(ctx, package_id)
    if pkg is None or not is_bookable(pkg, ctx.today):
        return {"error": f"Package {package_id} not found or not available. Use search_packages."}
    details = _summary(pkg, ctx.today)
    details.update(
        {
            "description": (pkg.description or "")[:2000],
            "includes": pkg.includes or [],
            "excludes": pkg.excludes or [],
            "all_upcoming_departures": _upcoming_dates(pkg, ctx.today) or "flexible, on request",
        }
    )
    return details


def _to_int(value, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def create_booking_ticket(ctx: ToolContext, package_id=None, departure_date: str = "", adults=None, children=0,
                          lead_traveler_name: str = "", contact_phone: str = "", contact_email: str = "",
                          special_requests: str = "", **_) -> dict:
    pkg = _get_package(ctx, package_id)
    if pkg is None or not is_bookable(pkg, ctx.today):
        return {"error": f"Package {package_id} not found or not available."}

    n_adults = _to_int(adults)
    n_children = _to_int(children, 0) or 0
    if not n_adults or n_adults < 1 or n_children < 0:
        return {"error": "At least one adult is required. Ask the customer how many adults and children."}

    departure_date = (departure_date or "").strip()
    try:
        dep = date.fromisoformat(departure_date)
    except ValueError:
        return {"error": "departure_date must be YYYY-MM-DD. Ask the customer to pick a date."}
    upcoming = _upcoming_dates(pkg, ctx.today)
    if pkg.departure_dates:
        if departure_date not in upcoming:
            return {"error": "This date is not available.", "available_dates": upcoming}
    elif dep < ctx.today:
        return {"error": "The departure date is in the past."}

    if pkg.seats_available is not None and n_adults + n_children > pkg.seats_available:
        return {"error": f"Only {pkg.seats_available} seats are left on this package."}

    name = (lead_traveler_name or "").strip()
    phone = (contact_phone or "").strip() or ctx.customer.phone
    if not name or not phone:
        return {"error": "The lead traveler's full name and a phone number are required."}

    # The same conversation already has an open ticket: don't create a duplicate.
    existing = ctx.db.scalar(
        select(Ticket).where(
            Ticket.conversation_id == ctx.conversation.id,
            Ticket.package_id == pkg.id,
            Ticket.status.in_([TicketStatus.PENDING_PAYMENT, TicketStatus.IN_PROGRESS]),
        )
    )
    if existing:
        ctx.ticket_reference = existing.reference
        _hand_over(ctx, f"Payment for ticket {existing.reference}")
        return {
            "ticket_reference": existing.reference,
            "note": "This booking was already created. Remind the customer of the reference.",
        }

    child_unit = pkg.child_price if pkg.child_price is not None else pkg.price_per_person
    total = pkg.price_per_person * n_adults + child_unit * n_children

    customer = ctx.customer
    customer.name = customer.name or name
    customer.phone = customer.phone or phone
    if contact_email and not customer.email:
        customer.email = contact_email.strip()

    ref = ticket_reference()
    while ctx.db.scalar(select(Ticket.id).where(Ticket.reference == ref)):
        ref = ticket_reference()

    ticket = Ticket(
        company_id=ctx.company.id,
        reference=ref,
        conversation_id=ctx.conversation.id,
        customer_id=customer.id,
        package_id=pkg.id,
        package_title=pkg.title,
        departure_date=departure_date,
        adults=n_adults,
        children=n_children,
        lead_traveler_name=name,
        contact_phone=phone,
        contact_email=(contact_email or "").strip() or None,
        special_requests=(special_requests or "").strip(),
        total_price=total,
        currency=pkg.currency,
        status=TicketStatus.PENDING_PAYMENT,
        created_by="ai",
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    ctx.ticket_reference = ref
    _hand_over(ctx, f"Payment for ticket {ref}")
    return {
        "ticket_reference": ref,
        "package": pkg.title,
        "departure_date": departure_date,
        "travelers": {"adults": n_adults, "children": n_children},
        "total_price": _money(total),
        "currency": pkg.currency,
        "next_step": f"A {ctx.company.name} consultant will contact the customer to complete the payment. "
        "Give the customer the ticket reference. Do not ask for payment details.",
    }


def request_human_agent(ctx: ToolContext, reason: str = "", **_) -> dict:
    _hand_over(ctx, (reason or "Customer needs a human agent").strip()[:300])
    return {
        "handed_over": True,
        "next_step": "Tell the customer a consultant will reply in this chat shortly.",
    }


def _hand_over(ctx: ToolContext, reason: str) -> None:
    conv = ctx.conversation
    conv.status = ConversationStatus.HUMAN
    conv.handover_reason = reason
    ctx.handed_over = True
    ctx.db.add(
        Message(
            conversation_id=conv.id,
            sender=Sender.SYSTEM,
            kind=MessageKind.TEXT,
            content=f"Handed over to the team: {reason}",
        )
    )


_HANDLERS = {
    "search_packages": search_packages,
    "get_package_details": get_package_details,
    "create_booking_ticket": create_booking_ticket,
    "request_human_agent": request_human_agent,
}


def run_tool(ctx: ToolContext, name: str, arguments: dict) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool {name}"}
    try:
        return handler(ctx, **(arguments or {}))
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
