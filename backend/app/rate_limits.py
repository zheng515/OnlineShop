"""Counting requests for the abuse limits (FR94)."""

from datetime import timedelta

from .database import Database
from .security import utcnow

RETENTION = timedelta(days=1)


def allow(conn: Database, kind: str, key: str, limit: int, window: timedelta) -> bool:
    """Record a request of `kind` for `key` and say whether it is within `limit` per `window`.
    Requests over the limit are not recorded, so they do not extend the wait."""
    now = utcnow()
    conn.execute("DELETE FROM rate_events WHERE created_at < ?", ((now - RETENTION).isoformat(),))
    count = conn.execute(
        "SELECT COUNT(*) FROM rate_events WHERE kind = ? AND key = ? AND created_at > ?",
        (kind, key, (now - window).isoformat()),
    ).fetchone()[0]
    if count >= limit:
        conn.commit()
        return False
    conn.execute("INSERT INTO rate_events (kind, key, created_at) VALUES (?, ?, ?)", (kind, key, now.isoformat()))
    conn.commit()
    return True
