"""Regular background work: cancelling unpaid orders after their deadline (FR79) and sending
outbox emails (FR95).

The server runs both in every worker (their status checks make that safe); they can also be
run once from cron:
    python -m app.jobs
"""

import asyncio
import logging
import sys
from collections.abc import Callable

from .config import Settings, load_settings
from .database import close_pools, connect
from .email.delivery import send_due
from .payments.service import expire_overdue_orders

log = logging.getLogger("onlineshop.jobs")


def _with_connection(settings: Settings, work: Callable) -> int:
    conn = connect(settings.database_url)
    try:
        return work(conn)
    finally:
        conn.close()


def expire_orders_once(settings: Settings) -> int:
    return _with_connection(settings, expire_overdue_orders)


def send_emails_once(settings: Settings) -> int:
    return _with_connection(settings, lambda conn: send_due(conn, settings))


async def run_forever(settings: Settings, job: Callable[[Settings], int], interval: int, description: str) -> None:
    """Started by the server for each job."""
    while True:
        await asyncio.sleep(interval)
        try:
            done = await asyncio.to_thread(job, settings)
            if done:
                log.info("%s: %s", description, done)
        except Exception:  # noqa: BLE001 - keep the loop alive; the next round retries
            log.exception("Background job failed: %s", description)


def start_background_jobs(settings: Settings) -> list[asyncio.Task]:
    jobs = [
        (expire_orders_once, settings.job_interval_seconds, "orders cancelled after their payment deadline"),
        (send_emails_once, settings.email_interval_seconds, "emails sent"),
    ]
    return [asyncio.create_task(run_forever(settings, job, interval, text)) for job, interval, text in jobs if interval > 0]


if __name__ == "__main__":
    current = load_settings()
    expired, sent = expire_orders_once(current), send_emails_once(current)
    close_pools()
    print(f"Cancelled {expired} order(s) whose payment deadline passed; sent {sent} email(s).")
    sys.exit(0)
