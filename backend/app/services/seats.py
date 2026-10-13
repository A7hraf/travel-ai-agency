"""Seats on packages with a limited number of places.

A booking holds its seats from the moment it is created (so the AI cannot sell the same seats
twice) until it is cancelled. Every change is one conditional UPDATE in the database, so two
bookings at the same moment can never both take the last seats.
"""

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Ticket, TravelPackage


class NotEnoughSeats(Exception):
    def __init__(self, left: int):
        super().__init__(f"Only {left} seats left on this package")
        self.left = left


def hold(db: Session, ticket: Ticket) -> None:
    """Take the ticket's seats if it does not hold them yet. Raises NotEnoughSeats."""
    if ticket.seats_held or ticket.package_id is None:
        return
    pkg = db.get(TravelPackage, ticket.package_id)
    travelers = ticket.adults + ticket.children
    if pkg is None or pkg.seats_available is None or travelers <= 0:
        return
    result = db.execute(
        update(TravelPackage)
        .where(TravelPackage.id == pkg.id, TravelPackage.seats_available >= travelers)
        .values(seats_available=TravelPackage.seats_available - travelers)
        .execution_options(synchronize_session=False)
    )
    db.refresh(pkg, ["seats_available"])
    if result.rowcount != 1:
        raise NotEnoughSeats(pkg.seats_available or 0)
    ticket.seats_held = travelers


def release(db: Session, ticket: Ticket) -> None:
    """Give back exactly the seats this ticket holds."""
    if not ticket.seats_held:
        return
    if ticket.package_id is not None:
        db.execute(
            update(TravelPackage)
            .where(TravelPackage.id == ticket.package_id, TravelPackage.seats_available.is_not(None))
            .values(seats_available=TravelPackage.seats_available + ticket.seats_held)
            .execution_options(synchronize_session=False)
        )
        pkg = db.get(TravelPackage, ticket.package_id)
        if pkg is not None:
            db.refresh(pkg, ["seats_available"])
    ticket.seats_held = 0


def hold_or_409(db: Session, ticket: Ticket) -> None:
    try:
        hold(db, ticket)
    except NotEnoughSeats as exc:
        raise HTTPException(409, str(exc)) from exc
