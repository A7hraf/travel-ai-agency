"""Tools the AI agent can call.

Every tool runs inside a ``ToolContext`` bound to one company and one conversation,
so the model can never read or book another company's packages, whatever it asks for.
Prices are always computed here, never taken from the model.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

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
    TicketEvent,
    TicketStatus,
    TravelPackage,
)
from ..security import ticket_reference
from ..services import seats
from .llm import INVALID_ARGUMENTS
from .text import Matcher, keyword_groups

log = logging.getLogger(__name__)

MAX_TRAVELERS = 50
MAX_BOOKING_HORIZON_DAYS = 730

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
            "name": "quote_booking",
            "description": "Check a booking and get the exact total price from the system, without booking. "
            "Call it before showing the summary to the customer, and use only the total it returns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_id": {"type": "integer"},
                    "departure_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "adults": {"type": "integer", "minimum": 1},
                    "children": {"type": "integer", "minimum": 0},
                },
                "required": ["package_id", "departure_date", "adults"],
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


def _text(value, limit: int = 500) -> str:
    """Any value the model sent, as clean text (models sometimes send numbers or lists)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value)
    return str(value).strip()[:limit]


def _number(value) -> Decimal | None:
    """A positive amount from "300", 300, "300 OMR", "1,000" or "٣٠٠"; None when there is none."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value)) if math.isfinite(value) and value >= 0 else None
    text = str(value).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    try:
        return Decimal(match.group()) if match else None
    except InvalidOperation:
        return None


def _count(value, default: int | None = None) -> int | None:
    """A whole number of people; None when the value is not one (True, 2.5, "two", 10**9...)."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, int):
        return value
    text = str(value).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return int(text) if text.isdigit() else None


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
    pid = _count(package_id)
    if pid is None or not 0 < pid < 2**31:
        return None
    pkg = ctx.db.get(TravelPackage, pid)
    if pkg is None or pkg.company_id != ctx.company.id:
        return None
    return pkg


def search_packages(ctx: ToolContext, query="", max_price_per_person=None, min_days=None,
                    max_days=None, departure_month=None, **_) -> dict:
    packages = _company_packages(ctx)
    ignored: list[str] = []

    budget = _number(max_price_per_person)
    if max_price_per_person not in (None, "") and budget is None:
        ignored.append("max_price_per_person (not a number)")
    min_d = _count(min_days)
    if min_days not in (None, "") and min_d is None:
        ignored.append("min_days (not a whole number)")
    max_d = _count(max_days)
    if max_days not in (None, "") and max_d is None:
        ignored.append("max_days (not a whole number)")
    month_text = _text(departure_month, 20)
    month = month_text if re.fullmatch(r"\d{4}-\d{2}", month_text) else None
    if month_text and not month:
        ignored.append("departure_month (use YYYY-MM)")

    def passes_filters(p: TravelPackage) -> bool:
        if budget is not None and p.price_per_person > budget:
            return False
        if min_d is not None and p.duration_days < min_d:
            return False
        if max_d is not None and p.duration_days > max_d:
            return False
        if month and p.departure_dates:
            if not any(d.startswith(month) for d in _upcoming_dates(p, ctx.today)):
                return False
        return True

    filtered = [p for p in packages if passes_filters(p)]
    groups = keyword_groups(_text(query, 300))
    if groups:
        scored = []
        for p in filtered:
            everything = Matcher(" ".join(
                [p.title, p.destination, p.country, p.description or "", p.hotel_name or "", " ".join(p.tags or [])]
            ))
            place = Matcher(f"{p.title} {p.destination} {p.country} {' '.join(p.tags or [])}")
            score = sum(1 for g in groups if everything.matches(g)) + sum(2 for g in groups if place.matches(g))
            if score:
                scored.append((score, p))
        scored.sort(key=lambda sp: (-sp[0], not sp[1].is_featured, sp[1].price_per_person))
        matches = [p for _, p in scored]
    else:
        matches = sorted(filtered, key=lambda p: (not p.is_featured, p.price_per_person))

    extra = {"ignored_filters": ignored} if ignored else {}
    if matches:
        return {"results": [_summary(p, ctx.today) for p in matches[:MAX_RESULTS]], "total_matches": len(matches),
                **extra}

    alternatives = sorted(packages, key=lambda p: (not p.is_featured, p.price_per_person))[:3]
    return {
        "results": [],
        "note": "No package matches these criteria. Tell the customer honestly and suggest the "
        "alternatives below, or offer a human consultant for a custom trip.",
        "alternatives": [_summary(p, ctx.today) for p in alternatives],
        **extra,
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


def _check_booking(ctx: ToolContext, package_id, departure_date, adults, children):
    """Validate a booking request. Returns (error, values)."""
    pkg = _get_package(ctx, package_id)
    if pkg is None or not is_bookable(pkg, ctx.today):
        return {"error": f"Package {package_id} not found or not available. Use search_packages."}, None

    n_adults = _count(adults)
    n_children = _count(children, 0)
    if n_adults is None or n_children is None or n_adults < 1 or n_children < 0:
        return {"error": "Give the number of adults (at least 1) and of children as whole numbers. "
                         "Ask the customer if unsure."}, None
    if n_adults + n_children > MAX_TRAVELERS:
        return {"error": f"Groups of more than {MAX_TRAVELERS} travelers are handled by a consultant: "
                         "call request_human_agent."}, None

    try:
        dep = date.fromisoformat(_text(departure_date, 20))
    except ValueError:
        return {"error": "departure_date must be YYYY-MM-DD. Ask the customer to pick a date."}, None
    upcoming = _upcoming_dates(pkg, ctx.today)
    if pkg.departure_dates:
        if dep.isoformat() not in upcoming:
            return {"error": "This date is not available.", "available_dates": upcoming}, None
    elif dep <= ctx.today:
        return {"error": "The departure date must be after today."}, None
    elif dep > ctx.today + timedelta(days=MAX_BOOKING_HORIZON_DAYS):
        return {"error": "This date is too far ahead. Ask the customer for a date within two years."}, None

    if pkg.seats_available is not None and n_adults + n_children > pkg.seats_available:
        return {"error": f"Only {pkg.seats_available} seats are left on this package."}, None

    child_unit = pkg.child_price if pkg.child_price is not None else pkg.price_per_person
    total = pkg.price_per_person * n_adults + child_unit * n_children
    return None, (pkg, dep.isoformat(), n_adults, n_children, total)


def quote_booking(ctx: ToolContext, package_id=None, departure_date="", adults=None, children=0, **_) -> dict:
    error, values = _check_booking(ctx, package_id, departure_date, adults, children)
    if error:
        return error
    pkg, dep, n_adults, n_children, total = values
    return {
        "package": pkg.title,
        "departure_date": dep,
        "travelers": {"adults": n_adults, "children": n_children},
        "price_per_adult": _money(pkg.price_per_person),
        "price_per_child": _money(pkg.child_price if pkg.child_price is not None else pkg.price_per_person),
        "total_price": _money(total),
        "currency": pkg.currency,
        "next_step": "Show this summary and total to the customer and ask them to confirm.",
    }


def _ticket_summary(ticket: Ticket) -> dict:
    return {
        "ticket_reference": ticket.reference,
        "package": ticket.package_title,
        "departure_date": ticket.departure_date,
        "travelers": {"adults": ticket.adults, "children": ticket.children},
        "total_price": _money(ticket.total_price),
        "currency": ticket.currency,
    }


def create_booking_ticket(ctx: ToolContext, package_id=None, departure_date="", adults=None, children=0,
                          lead_traveler_name="", contact_phone="", contact_email="",
                          special_requests="", **_) -> dict:
    if ctx.ticket_reference:
        return {"error": f"A booking ({ctx.ticket_reference}) was already created in this reply. "
                         "Give the customer that reference."}
    if ctx.handed_over:
        return {"error": "The conversation was handed to a consultant; do not book now."}

    error, values = _check_booking(ctx, package_id, departure_date, adults, children)
    if error:
        return error
    pkg, departure_date, n_adults, n_children, total = values

    name = _text(lead_traveler_name, 200)
    phone = _text(contact_phone, 50) or ctx.customer.phone
    email = _text(contact_email, 200)
    if not name or not phone:
        return {"error": "The lead traveler's full name and a phone number are required."}

    # The conversation already has an open booking: never create a second one. Changes go to a consultant.
    existing = ctx.db.scalar(
        select(Ticket).where(
            Ticket.conversation_id == ctx.conversation.id,
            Ticket.status.in_([TicketStatus.PENDING_PAYMENT, TicketStatus.IN_PROGRESS]),
        ).order_by(Ticket.id.desc()).limit(1)
    )
    if existing:
        same = (existing.package_id == pkg.id and existing.departure_date == departure_date
                and existing.adults == n_adults and existing.children == n_children)
        ctx.ticket_reference = existing.reference
        if same:
            _hand_over(ctx, f"Payment for ticket {existing.reference}")
            note = "This booking was already created. Remind the customer of the reference and total."
        else:
            _hand_over(ctx, f"Customer wants to change ticket {existing.reference}: {pkg.title}, {departure_date}, "
                            f"{n_adults} adults, {n_children} children")
            note = ("The customer already has this booking. A consultant will update it with the new details; "
                    "tell the customer so, with the reference.")
        return {**_ticket_summary(existing), "note": note}

    child_unit = pkg.child_price if pkg.child_price is not None else pkg.price_per_person
    total = pkg.price_per_person * n_adults + child_unit * n_children

    customer = ctx.customer
    customer.name = customer.name or name
    customer.phone = customer.phone or phone
    if email and not customer.email:
        customer.email = email

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
        contact_email=email or None,
        special_requests=_text(special_requests, 2000),
        total_price=total,
        currency=pkg.currency,
        status=TicketStatus.PENDING_PAYMENT,
        created_by="ai",
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    try:
        seats.hold(ctx.db, ticket)
    except seats.NotEnoughSeats as exc:
        ctx.db.delete(ticket)
        ctx.db.flush()
        return {"error": f"Only {exc.left} seats are left on this package."}
    ctx.db.add(TicketEvent(ticket_id=ticket.id, actor="AI", action="created",
                           new_value=f"{n_adults} adults, {n_children} children, {_money(total)} {pkg.currency}"))
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


def request_human_agent(ctx: ToolContext, reason="", **_) -> dict:
    _hand_over(ctx, _text(reason, 300) or "Customer needs a human agent")
    return {
        "handed_over": True,
        "next_step": "Tell the customer a consultant will reply in this chat shortly.",
    }


def _hand_over(ctx: ToolContext, reason: str) -> None:
    conv = ctx.conversation
    conv.status = ConversationStatus.HUMAN
    conv.handover_reason = reason[:300]
    conv.was_handed_over = True
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
    "quote_booking": quote_booking,
    "create_booking_ticket": create_booking_ticket,
    "request_human_agent": request_human_agent,
}


def run_tool(ctx: ToolContext, name: str, arguments: dict) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool {name}. Available: {', '.join(_HANDLERS)}"}
    arguments = arguments if isinstance(arguments, dict) else {}
    if INVALID_ARGUMENTS in arguments:
        return {"error": f"Your arguments for {name} were not a valid JSON object. Send them again."}
    try:
        return handler(ctx, **arguments)
    except Exception as exc:  # a bad value from the model must never break the conversation
        log.warning("Tool %s failed with %r: %s", name, arguments, exc)
        return {"error": f"Bad arguments for {name}. Check the values and try again."}
