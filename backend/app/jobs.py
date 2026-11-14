"""Periodic jobs, run while the server is awake (a sleeping free server catches up when it wakes)."""

import asyncio
import logging

from .database import SessionLocal
from .timeutil import local_today

log = logging.getLogger(__name__)

EVERY_SECONDS = 5 * 60  # calendar reminders need a short step


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


async def loop() -> None:
    await asyncio.sleep(60)  # let the server start first
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:  # noqa: BLE001 (a failing job must never stop the server)
            log.exception("Periodic job failed")
        await asyncio.sleep(EVERY_SECONDS)
