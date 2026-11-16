"""Periodic jobs, run while the server is awake (a sleeping free server catches up when it wakes)."""

import asyncio
import logging
from collections.abc import Callable

from .database import SessionLocal
from .timeutil import local_today

log = logging.getLogger(__name__)

EVERY_SECONDS = 5 * 60  # calendar reminders need a short step
_last_daily = None


def _often() -> list[tuple[str, Callable]]:
    from .services.broadcasts import send_checkins  # noqa: PLC0415
    from .services.calendar import send_reminders  # noqa: PLC0415
    from .services.customer_portal import send_feedback_requests  # noqa: PLC0415
    from .services.notifications import late_steps  # noqa: PLC0415

    return [
        ("after-trip feedback requests sent", lambda db: send_feedback_requests(db, local_today())),
        ("calendar reminders sent", send_reminders),
        ("travellers asked how their trip is going", lambda db: send_checkins(db, local_today())),
        ("late steps told to the team", late_steps),
    ]


def _daily() -> list[tuple[str, Callable]]:
    from .services.advisor import daily_findings  # noqa: PLC0415
    from .services.b2b_flow import payment_reminders  # noqa: PLC0415
    from .services.notifications import clean_old  # noqa: PLC0415
    from .workflow import pass_finished_trips  # noqa: PLC0415

    def clean(db):
        clean_old(db)
        db.commit()

    return [
        ("old notifications cleared", clean),
        ("business payment reminders sent", lambda db: payment_reminders(db, local_today())),
        ("requests moved on after their trip", lambda db: pass_finished_trips(db, local_today())),
        ("advisor findings raised", daily_findings),
    ]


def _run(jobs: list[tuple[str, Callable]]) -> None:
    for name, job in jobs:
        try:
            with SessionLocal() as db:
                done = job(db)
            if done:
                log.info("%s: %s", name, done)
        except Exception:  # noqa: BLE001 (one failing job must not stop the others)
            log.exception("Periodic job failed: %s", name)


def run_once() -> None:
    global _last_daily
    _run(_often())
    if _last_daily != local_today():
        _last_daily = local_today()
        _run(_daily())


async def loop() -> None:
    await asyncio.sleep(60)  # let the server start first
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # noqa: BLE001 (a failing job must never stop the server)
            log.exception("Periodic jobs failed")
        await asyncio.sleep(EVERY_SECONDS)
