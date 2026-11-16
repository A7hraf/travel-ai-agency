"""Periodic jobs, run while the server is awake (a sleeping free server catches up when it wakes)."""

import asyncio
import logging

from .database import SessionLocal
from .timeutil import local_today

log = logging.getLogger(__name__)

EVERY_SECONDS = 5 * 60  # calendar reminders need a short step
_last_findings = None  # the AI advisor's findings run once a day


def run_once() -> None:
    from .services.calendar import send_reminders  # noqa: PLC0415
    from .services.customer_portal import send_feedback_requests  # noqa: PLC0415

    with SessionLocal() as db:
        sent = send_feedback_requests(db, local_today())
        if sent:
            log.info("Sent %s after-trip feedback requests", sent)
    with SessionLocal() as db:
        reminded = send_reminders(db)
        if reminded:
            log.info("Sent %s calendar reminders", reminded)
    from .services.broadcasts import send_checkins  # noqa: PLC0415
    from .services.notifications import clean_old, late_steps  # noqa: PLC0415

    with SessionLocal() as db:
        asked = send_checkins(db, local_today())
        if asked:
            log.info("Asked %s travellers how their trip is going", asked)

    with SessionLocal() as db:
        late = late_steps(db)
        if late:
            log.info("Told the team about %s late steps", late)
    global _last_findings
    if _last_findings != local_today():
        from .services.advisor import daily_findings  # noqa: PLC0415

        _last_findings = local_today()
        from .workflow import pass_finished_trips  # noqa: PLC0415

        with SessionLocal() as db:
            clean_old(db)
            db.commit()
        from .services.b2b_flow import payment_reminders  # noqa: PLC0415

        with SessionLocal() as db:
            due = payment_reminders(db, local_today())
            if due:
                log.info("Reminded %s business clients of a payment", due)
        with SessionLocal() as db:
            moved = pass_finished_trips(db, local_today())
            if moved:
                log.info("%s requests moved on after their trip", moved)
        with SessionLocal() as db:
            found = daily_findings(db)
            if found:
                log.info("The AI advisor raised %s findings", found)


async def loop() -> None:
    await asyncio.sleep(60)  # let the server start first
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # noqa: BLE001 (a failing job must never stop the server)
            log.exception("Periodic job failed")
        await asyncio.sleep(EVERY_SECONDS)
