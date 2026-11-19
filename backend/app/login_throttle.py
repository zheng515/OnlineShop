"""Login throttling per username and per client address (FR53)."""

import math
import sqlite3
from datetime import datetime, timedelta

from .security import utcnow

WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_USERNAME = 5
MAX_FAILURES_PER_IP = 30
RETENTION = timedelta(days=1)


def _wait_until(failures: list[str], limit: int) -> datetime | None:
    """failures: timestamps newest first. Locked until the oldest of the last `limit` ages out of the window."""
    if len(failures) < limit:
        return None
    return datetime.fromisoformat(failures[limit - 1]) + WINDOW


def retry_after_seconds(conn: sqlite3.Connection, username: str, ip: str) -> int | None:
    """Seconds until a login attempt is allowed again, or None if allowed now."""
    now = utcnow()
    window_start = (now - WINDOW).isoformat()

    last_success = conn.execute(
        "SELECT MAX(created_at) AS at FROM login_attempts WHERE username = ? AND success = 1", (username,)
    ).fetchone()["at"]
    since = max(window_start, last_success) if last_success else window_start
    by_username = [
        row["created_at"]
        for row in conn.execute(
            """SELECT created_at FROM login_attempts
               WHERE username = ? AND success = 0 AND created_at > ? ORDER BY created_at DESC LIMIT ?""",
            (username, since, MAX_FAILURES_PER_USERNAME),
        )
    ]
    by_ip = [
        row["created_at"]
        for row in conn.execute(
            """SELECT created_at FROM login_attempts
               WHERE ip = ? AND success = 0 AND created_at > ? ORDER BY created_at DESC LIMIT ?""",
            (ip, window_start, MAX_FAILURES_PER_IP),
        )
    ]
    locks = [
        until
        for until in (_wait_until(by_username, MAX_FAILURES_PER_USERNAME), _wait_until(by_ip, MAX_FAILURES_PER_IP))
        if until and until > now
    ]
    if not locks:
        return None
    return max(1, math.ceil((max(locks) - now).total_seconds()))


def record_attempt(conn: sqlite3.Connection, username: str, ip: str, success: bool) -> None:
    now = utcnow()
    conn.execute("DELETE FROM login_attempts WHERE created_at < ?", ((now - RETENTION).isoformat(),))
    conn.execute(
        "INSERT INTO login_attempts (username, ip, success, created_at) VALUES (?, ?, ?, ?)",
        (username, ip, int(success), now.isoformat()),
    )
    conn.commit()


def refusal_message(seconds: int) -> str:
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed login attempts. Please try again in {minutes} {unit}."
