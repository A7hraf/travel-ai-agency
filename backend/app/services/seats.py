"""Seats on packages with a limited number of places.

``TravelPackage.seats_available`` is the number of seats of EACH departure date. The seats left on a
date are that number minus the seats held by the bookings for the same package and date.

A booking holds its seats from the moment it is created (so the AI cannot sell the same seats
twice) until it is cancelled, or until it has waited SEAT_HOLD_HOURS without payment: one chat must
not be able to block a trip without paying. Taking seats first locks the package row, so two
bookings at the same moment can never both take the last seats.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, not_, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Ticket, TicketEvent, TicketStatus, TravelPackage, UTCDateTime

RELEASED_ACTION = "seats_released"


class NotEnoughSeats(Exception):
    def __init__(self, left: int, departure_date: str | None = None):
        on = f" on {departure_date}" if departure_date else ""
        super().__init__(f"Only {left} seats left{on} on this package")
        self.left = left
        self.departure_date = departure_date


def hold_hours() -> int:
    return get_settings().seat_hold_hours


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _held_since():
    return func.coalesce(Ticket.seats_held_at, Ticket.created_at, type_=UTCDateTime())


def _expired(now: datetime):
    """Unpaid bookings whose hold ran out (their seats no longer count, even before they are released)."""
    return and_(Ticket.status == TicketStatus.PENDING_PAYMENT, Ticket.seats_held > 0,
                _held_since() < now - timedelta(hours=hold_hours()))


def _holding(now: datetime):
    return and_(Ticket.seats_held > 0, Ticket.status != TicketStatus.CANCELLED, not_(_expired(now)))


def release_expired(db: Session, company_id: int | None = None, package_id: int | None = None) -> int:
    """Give back the seats of unpaid bookings older than SEAT_HOLD_HOURS, with a history event.

    Called before seats are counted for a booking and when employees list tickets. Seat counts already
    ignore expired holds, so this only makes the release visible (and lets staff re-hold on payment).
    """
    now = _now()
    stmt = select(Ticket).where(_expired(now))
    if company_id is not None:
        stmt = stmt.where(Ticket.company_id == company_id)
    if package_id is not None:
        stmt = stmt.where(Ticket.package_id == package_id)
    # An employee may be marking the ticket paid right now: leave it to them (Postgres; SQLite ignores it).
    tickets = db.scalars(stmt.with_for_update(skip_locked=True)).all()
    hours = hold_hours()
    for ticket in tickets:
        ticket.seats_held_at = ticket.seats_held_at or ticket.created_at  # marks "was held, now released"
        ticket.seats_held = 0
        db.add(TicketEvent(ticket_id=ticket.id, actor="System", action=RELEASED_ACTION,
                           new_value=f"Seats released: not paid within {hours} hours"))
    if tickets:
        db.flush()
    return len(tickets)


def held_by_date(db: Session, package_id: int) -> dict[str, int]:
    """Seats taken on each departure date of a package."""
    rows = db.execute(
        select(Ticket.departure_date, func.sum(Ticket.seats_held))
        .where(Ticket.package_id == package_id, _holding(_now()))
        .group_by(Ticket.departure_date)
    ).all()
    return {d: int(n or 0) for d, n in rows if d}


def left_by_date(db: Session, pkg: TravelPackage, dates: list[str], from_date: str = "") -> dict[str, int] | None:
    """Seats left on each of the given dates, plus any other date from ``from_date`` on that has bookings
    (flexible-date packages); None when unlimited.

    Also kept on the package as ``seats_left_by_date`` so the API responses can show it.
    """
    if pkg.seats_available is None:
        pkg.seats_left_by_date = None
        return None
    held = held_by_date(db, pkg.id) if pkg.id is not None else {}
    wanted = set(dates) | {d for d in held if d >= from_date}
    left = {d: max(pkg.seats_available - held.get(d, 0), 0) for d in sorted(wanted)}
    pkg.seats_left_by_date = left
    return left


def seats_left(db: Session, pkg: TravelPackage, departure_date: str) -> int | None:
    if pkg.seats_available is None:
        return None
    return max(pkg.seats_available - held_by_date(db, pkg.id).get(departure_date, 0), 0)


def _lock_package(db: Session, package_id: int) -> None:
    """Lock the package row until commit: on Postgres a row lock, on SQLite the database write lock.

    An UPDATE does both (SELECT ... FOR UPDATE is ignored by SQLite). It changes nothing.
    """
    db.execute(
        update(TravelPackage)
        .where(TravelPackage.id == package_id)
        .values(updated_at=TravelPackage.updated_at)
        .execution_options(synchronize_session=False)
    )


def hold(db: Session, ticket: Ticket) -> None:
    """Take the ticket's seats on its departure date if it does not hold them yet. Raises NotEnoughSeats."""
    if ticket.package_id is None:
        return
    _lock_package(db, ticket.package_id)
    # Counted under the lock, after expired holds (this ticket's own too) were given back.
    release_expired(db, package_id=ticket.package_id)
    if ticket.seats_held:
        return
    pkg = db.get(TravelPackage, ticket.package_id)
    if pkg is None:
        return
    db.refresh(pkg, ["seats_available"])
    travelers = ticket.adults + ticket.children
    if pkg.seats_available is None or travelers <= 0:
        return
    left = seats_left(db, pkg, ticket.departure_date or "")
    if travelers > left:
        raise NotEnoughSeats(left, ticket.departure_date)
    ticket.seats_held = travelers
    ticket.seats_held_at = _now()


def release(db: Session, ticket: Ticket) -> None:
    """Give back exactly the seats this ticket holds."""
    ticket.seats_held = 0
    ticket.seats_held_at = None


def was_released(db: Session, ticket: Ticket) -> bool:
    return bool(db.scalar(select(TicketEvent.id).where(TicketEvent.ticket_id == ticket.id,
                                                      TicketEvent.action == RELEASED_ACTION).limit(1)))


def hold_or_409(db: Session, ticket: Ticket) -> None:
    try:
        hold(db, ticket)
    except NotEnoughSeats as exc:
        if was_released(db, ticket):
            raise HTTPException(409, f"This booking's seats were released because it was not paid within "
                                     f"{hold_hours()} hours, and only {exc.left} seats are left on "
                                     f"{exc.departure_date}.") from exc
        raise HTTPException(409, str(exc)) from exc
