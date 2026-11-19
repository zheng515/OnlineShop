"""Order emails to customers (FR96). Called inside the transaction of the order change, so the
email is queued exactly when the change is committed (FR95)."""

from datetime import datetime

from .database import Database
from .email import templates
from .email.outbox import queue_email
from .products import format_cents
from .security import utcnow

CANCEL_REASONS = {
    "customer": "at your request",
    "admin": "by the shop",
    "payment deadline": "because the payment was not completed in time",
}


def _recipient(conn: Database, order_id: int):
    return conn.execute(
        """SELECT o.id, o.total_cents, o.expires_at, u.email, u.display_name
           FROM orders o JOIN users u ON u.id = o.user_id WHERE o.id = ?""",
        (order_id,),
    ).fetchone()


def _money(cents: int) -> str:
    return f"${format_cents(cents):.2f}"


def order_event(conn: Database, order_id: int, new_status: str, actor: dict, refunding: bool = False) -> None:
    row = _recipient(conn, order_id)
    if row is None or not row["email"]:
        return  # accounts without an email address get no emails
    number = f"#{order_id:06d}"
    name = row["display_name"]
    if new_status == "awaiting_payment":
        minutes = max(1, round((datetime.fromisoformat(row["expires_at"]) - utcnow()).total_seconds() / 60))
        subject, body = templates.order_placed(name, number, order_id, _money(row["total_cents"]), minutes)
    elif new_status == "paid":
        subject, body = templates.payment_received(name, number, order_id, _money(row["total_cents"]))
    elif new_status == "shipped":
        subject, body = templates.order_shipped(name, number, order_id)
    elif new_status == "cancelled":
        reason = CANCEL_REASONS.get(actor["username"] if actor["role"] == "system" else actor["role"], "")
        subject, body = templates.order_cancelled(name, number, order_id, reason, refunding)
    else:
        return
    queue_email(conn, row["email"], subject, body, f"order_{new_status}")


def refund_completed(conn: Database, refund_id: int) -> None:
    row = conn.execute(
        """SELECT r.amount_cents, o.id AS order_id, u.email, u.display_name
           FROM refunds r JOIN payments p ON p.id = r.payment_id JOIN orders o ON o.id = p.order_id
           JOIN users u ON u.id = o.user_id WHERE r.id = ?""",
        (refund_id,),
    ).fetchone()
    if row is None or not row["email"]:
        return
    number = f"#{row['order_id']:06d}"
    subject, body = templates.refund_completed(row["display_name"], number, row["order_id"], _money(row["amount_cents"]))
    queue_email(conn, row["email"], subject, body, "refund_completed")
