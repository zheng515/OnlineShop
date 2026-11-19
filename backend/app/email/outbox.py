"""Writing emails to the outbox (FR95). Emails are inserted in the caller's transaction, so an
email exists exactly when the event that causes it was committed; app/email/delivery.py sends them."""

from ..database import Database
from ..security import utcnow

# Links in email bodies are written relative to this marker and completed with the shop's public
# address (SHOP_PUBLIC_URL) when the email is sent, so code that queues emails needs no settings.
SHOP_URL = "{{SHOP_URL}}"


def queue_email(conn: Database, to_address: str, subject: str, body: str, kind: str) -> int:
    now = utcnow().isoformat()
    return conn.insert(
        """INSERT INTO email_outbox (to_address, subject, body, kind, status, attempts, next_attempt_at, created_at)
           VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
        (to_address, subject, body, kind, now, now),
    )
