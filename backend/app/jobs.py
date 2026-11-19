"""Regular background work (FR79).

The server runs it every SHOP_JOB_INTERVAL_SECONDS; it can also be run from cron:
    python -m app.jobs
"""

import asyncio
import logging
import sys

from .config import Settings, load_settings
from .database import close_pools, connect
from .payments.service import expire_overdue_orders

log = logging.getLogger("onlineshop.jobs")


def run_once(settings: Settings) -> int:
    conn = connect(settings.database_url)
    try:
        return expire_overdue_orders(conn)
    finally:
        conn.close()


async def run_forever(settings: Settings) -> None:
    """Started by the server. Each worker runs it; the status checks make that safe."""
    while True:
        await asyncio.sleep(settings.job_interval_seconds)
        try:
            expired = await asyncio.to_thread(run_once, settings)
            if expired:
                log.info("Cancelled %s order(s) whose payment deadline passed", expired)
        except Exception:  # noqa: BLE001 - keep the loop alive; the next round retries
            log.exception("Background job failed")


if __name__ == "__main__":
    count = run_once(load_settings())
    close_pools()
    print(f"Cancelled {count} order(s) whose payment deadline passed.")
    sys.exit(0)
