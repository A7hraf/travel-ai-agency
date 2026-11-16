"""The supplier library: hotels, airlines, transport, activities… the company saved.

- Saved once (by hand, or from a choice sent to a client), then suggested again for requests to the same place.
- Spending figures: what the company paid each supplier and what clients paid, from requests that were paid.
- Margin learning: the company's usual margin per part, used to suggest a client price from a cost.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Supplier, Ticket, TicketStatus, TripOption, User, utcnow

PAID = (TicketStatus.PAID, TicketStatus.CONFIRMED, TicketStatus.COMPLETED)
MAX_SUPPLIERS = 2000


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def matches(db: Session, company_id: int, category: str, place: str | None, limit: int = 3) -> list[Supplier]:
    """The saved suppliers of this part for this place (or for anywhere), preferred and most used first."""
    used = (select(TripOption.supplier_id, func.count(TripOption.id).label("n"))
            .where(TripOption.company_id == company_id, TripOption.chosen.is_(True), TripOption.supplier_id.is_not(None))
            .group_by(TripOption.supplier_id).subquery())
    stmt = (select(Supplier).outerjoin(used, used.c.supplier_id == Supplier.id)
            .where(Supplier.company_id == company_id, Supplier.category == category, Supplier.is_active.is_(True)))
    words = [w for w in _norm(place).replace(",", " ").split() if len(w) > 2]
    if words:
        stmt = stmt.where(or_(Supplier.place == "", *[func.lower(Supplier.place).contains(w) for w in words]))
    else:
        stmt = stmt.where(Supplier.place == "")
    stmt = stmt.order_by(Supplier.preferred.desc(), func.coalesce(used.c.n, 0).desc(), Supplier.id)
    return list(db.scalars(stmt.limit(limit)).all())


def option_from(supplier: Supplier) -> dict:
    """The fields of a choice filled from a saved supplier."""
    return {"category": supplier.category, "title": supplier.name, "provider": supplier.name, "link": supplier.link,
            "image_url": supplier.image_url, "details": supplier.description or None, "cost_price": supplier.usual_cost,
            "price": supplier.usual_price, "supplier_id": supplier.id}


def save_option(db: Session, ticket: Ticket, option: TripOption, user: User) -> Supplier:
    """Keeps a choice in the library (or links it to the same supplier already there)."""
    name = option.provider if option.category == "flight" and option.provider else option.title
    existing = db.scalar(select(Supplier).where(Supplier.company_id == ticket.company_id, Supplier.category == option.category,
                                                func.lower(Supplier.name) == _norm(name)))
    if existing is None:
        count = db.scalar(select(func.count(Supplier.id)).where(Supplier.company_id == ticket.company_id)) or 0
        if count >= MAX_SUPPLIERS:
            raise HTTPException(409, "The library is full")
        existing = Supplier(company_id=ticket.company_id, category=option.category, name=name[:200],
                            place="" if option.category in ("flight", "insurance") else (ticket.destination or "")[:120],
                            link=option.link, image_url=option.image_url, description=(option.details or "")[:2000],
                            usual_cost=option.cost_price, usual_price=option.price)
        db.add(existing)
        db.flush()
    option.supplier_id = existing.id
    return existing


# --- Spending figures and margins -----------------------------------------------------------------------

def _paid_choices(db: Session, company_id: int, days: int) -> list[TripOption]:
    since = utcnow() - timedelta(days=days)
    return list(db.scalars(select(TripOption).join(Ticket, Ticket.id == TripOption.ticket_id).where(
        TripOption.company_id == company_id, TripOption.chosen.is_(True), Ticket.status.in_(PAID),
        Ticket.created_at >= since)).all())


def margins(db: Session, company_id: int, days: int = 365) -> dict[str, dict]:
    """Per part: the usual margin on cost (median of paid choices with both prices) and how many it is based on."""
    by_part: dict[str, list[float]] = defaultdict(list)
    for o in _paid_choices(db, company_id, days):
        if o.cost_price and o.price is not None and o.cost_price > 0:
            by_part[o.category].append(float((o.price - o.cost_price) / o.cost_price))
    out = {}
    for part, values in by_part.items():
        values.sort()
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        out[part] = {"margin_pct": round(median * 100, 1), "samples": len(values)}
    return out


def stats(db: Session, company_id: int, days: int = 365) -> dict:
    """What was spent with each supplier and what clients chose most, from requests that were paid."""
    choices = _paid_choices(db, company_id, days)
    suppliers = {s.id: s for s in db.scalars(select(Supplier).where(Supplier.company_id == company_id)).all()}
    rows: dict[tuple, dict] = {}
    stars: dict[int, int] = defaultdict(int)
    for o in choices:
        s = suppliers.get(o.supplier_id) if o.supplier_id else None
        key = ("s", s.id) if s else ("n", o.category, _norm(o.provider or o.title))
        row = rows.setdefault(key, {"supplier_id": s.id if s else None, "name": s.name if s else (o.provider or o.title),
                                    "category": o.category, "place": s.place if s else "", "stars": s.stars if s else None,
                                    "bookings": 0, "cost": Decimal(0), "revenue": Decimal(0), "in_library": bool(s)})
        row["bookings"] += 1
        row["cost"] += o.cost_price or 0
        row["revenue"] += o.price or 0
        if s and s.category == "hotel" and s.stars:
            stars[s.stars] += 1
    top = sorted(rows.values(), key=lambda r: (r["cost"], r["bookings"]), reverse=True)
    by_part: dict[str, dict] = defaultdict(lambda: {"bookings": 0, "cost": Decimal(0), "revenue": Decimal(0)})
    for r in top:
        p = by_part[r["category"]]
        p["bookings"] += r["bookings"]
        p["cost"] += r["cost"]
        p["revenue"] += r["revenue"]
    money = lambda v: float(round(v, 3))  # noqa: E731
    return {
        "days": days,
        "suppliers": [{**r, "cost": money(r["cost"]), "revenue": money(r["revenue"]),
                       "margin": money(r["revenue"] - r["cost"])} for r in top[:50]],
        "by_part": {k: {"bookings": v["bookings"], "cost": money(v["cost"]), "revenue": money(v["revenue"]),
                        "margin": money(v["revenue"] - v["cost"])} for k, v in by_part.items()},
        "hotel_stars": {str(k): v for k, v in sorted(stars.items())},
        "not_saved": sum(1 for r in top if not r["in_library"]),
    }
