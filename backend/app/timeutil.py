"""Local business time. Agencies work in their own time zone (Oman by default), so "today",
departure dates and dashboard days follow it instead of the server's UTC clock."""

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from .config import get_settings


@lru_cache
def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().business_timezone)


def local_now() -> datetime:
    return datetime.now(business_tz())


def local_today() -> date:
    return local_now().date()


def local_date(moment: datetime) -> date:
    """The local calendar day of a stored (UTC) time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(business_tz()).date()


def start_of_local_day(day: date) -> datetime:
    """The UTC moment the given local day starts."""
    return datetime.combine(day, datetime.min.time(), business_tz()).astimezone(timezone.utc)


def days_back(days: int) -> tuple[date, datetime]:
    """First local day of a period of ``days`` days ending today, and the UTC moment it starts."""
    first = local_today() - timedelta(days=days - 1)
    return first, start_of_local_day(first)
