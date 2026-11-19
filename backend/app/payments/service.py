"""Payments for orders: starting and resuming payments, provider notifications, refunds and the
payment deadline (FR78-FR83). Provider-specific work goes through app/payments/provider.py."""

import logging
from datetime import datetime

from fastapi import HTTPException, status

from ..config import Settings
from ..database import Database, write_transaction
from ..errors import ValidationProblem
from ..notifications import refund_completed
from ..order_service import OrderChanged, apply_transition, change_status, create_refunds, order_number, system_actor
from ..security import security_log, utcnow
from .provider import InvalidNotification, PaymentProvider, RefundFailed, get_provider

log = logging.getLogger("onlineshop.payments")

PAYMENT_CONFIRMED = system_actor("payment provider")
DEADLINE_PASSED = system_actor("payment deadline")


def _deadline_passed(expires_at: str | None) -> bool:
    return bool(expires_at) and datetime.fromisoformat(expires_at) <= utcnow()


def return_url(order_id: int) -> str:
    return f"/order.html?id={order_id}&payment=returned"


def expire_if_overdue(conn: Database, order_id: int) -> bool:
    """Cancel one order whose payment deadline has passed (FR79). Returns True if it was cancelled."""
    row = conn.execute("SELECT status, expires_at FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row or row["status"] != "awaiting_payment" or not _deadline_passed(row["expires_at"]):
        return False
    try:
        change_status(conn, order_id, "cancelled", DEADLINE_PASSED)
    except ValidationProblem:
        return False  # paid or cancelled meanwhile
    log.info("order_expired order=%s", order_id)
    return True


def expire_overdue_orders(conn: Database) -> int:
    """Cancel every order whose payment deadline has passed; run regularly by the server (FR79)."""
    rows = conn.execute(
        "SELECT id FROM orders WHERE status = 'awaiting_payment' AND expires_at <= ?", (utcnow().isoformat(),)
    ).fetchall()
    conn.commit()
    return sum(expire_if_overdue(conn, row["id"]) for row in rows)


def start_or_resume_payment(conn: Database, settings: Settings, order_id: int, user_id: int) -> str:
    """The provider page where the customer pays for their order (FR78, FR80)."""
    provider = get_provider(settings)
    order = conn.execute(
        "SELECT id, status, total_cents, expires_at FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)
    ).fetchone()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if order["status"] == "awaiting_payment" and expire_if_overdue(conn, order_id):
        raise ValidationProblem(
            ["The time to pay for this order has run out. The order was cancelled and its items were released."],
            status.HTTP_409_CONFLICT,
        )
    if order["status"] != "awaiting_payment":
        message = {
            "paid": "This order has already been paid.",
            "cancelled": "This order was cancelled and can no longer be paid.",
        }.get(order["status"], "This order does not need to be paid.")
        raise ValidationProblem([message], status.HTTP_409_CONFLICT)

    with write_transaction(conn):
        pending = conn.execute(
            "SELECT id, reference FROM payments WHERE order_id = ? AND status = 'pending' ORDER BY id DESC",
            (order_id,),
        ).fetchall()
        for payment in pending:
            if provider.is_usable(conn, payment["reference"]):
                return provider.page_url(payment["reference"])  # an unfinished page is reused (FR80)
            conn.execute(
                """UPDATE payments SET status = 'failed', failure_reason = 'The payment page was left without paying.',
                   updated_at = ? WHERE id = ? AND status = 'pending'""",
                (utcnow().isoformat(), payment["id"]),
            )
        session = provider.start(
            conn,
            order_number=order_number(order_id),
            amount_cents=order["total_cents"],
            currency=settings.currency,
            expires_at=datetime.fromisoformat(order["expires_at"]),
            return_url=return_url(order_id),
        )
        now = utcnow().isoformat()
        conn.insert(
            """INSERT INTO payments (order_id, provider, reference, amount_cents, currency, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (order_id, provider.name, session.reference, order["total_cents"], settings.currency, now, now),
        )
    log.info("payment_started order=%s reference=%s", order_id, session.reference)
    return session.url


def handle_notification(conn: Database, settings: Settings, provider_name: str, headers: dict[str, str], body: bytes) -> str:
    """Process one payment notification from the provider (FR81). Returns what was done."""
    provider = get_provider(settings)
    if provider_name != provider.name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown payment provider.")
    try:
        note = provider.parse_notification({k.lower(): v for k, v in headers.items()}, body)
    except InvalidNotification as exc:
        security_log.warning("payment_notification_rejected provider=%s reason=%s", provider_name, exc)
        raise ValidationProblem(["The payment notification could not be verified."], status.HTTP_400_BAD_REQUEST) from exc

    refund_ids: list[int] = []
    with write_transaction(conn):
        now = utcnow().isoformat()
        # Claiming the event id first makes repeats and simultaneous copies no-ops.
        claimed = conn.execute(
            "INSERT INTO payment_events (provider, event_id, received_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (provider.name, note.event_id, now),
        ).rowcount
        if claimed != 1:
            return "duplicate"
        payment = conn.execute(
            "SELECT * FROM payments WHERE provider = ? AND reference = ?", (provider.name, note.reference)
        ).fetchone()
        if payment is None:
            log.warning("payment_notification_unknown reference=%s", note.reference)
            return "unknown payment"

        if note.type == "payment.failed":
            conn.execute(
                "UPDATE payments SET status = 'failed', failure_reason = ?, updated_at = ? WHERE id = ? AND status = 'pending'",
                (note.reason or "The payment was declined.", now, payment["id"]),
            )
            return "payment failed"

        if payment["status"] == "succeeded":
            return "already paid"
        if note.amount_cents != payment["amount_cents"] or note.currency != payment["currency"]:
            security_log.warning(
                "payment_amount_mismatch reference=%s expected=%s %s got=%s %s", note.reference,
                payment["amount_cents"], payment["currency"], note.amount_cents, note.currency,
            )
            conn.execute(
                "UPDATE payments SET status = 'failed', failure_reason = ?, updated_at = ? WHERE id = ?",
                ("The confirmed amount did not match the order.", now, payment["id"]),
            )
            return "amount mismatch"

        # Money was taken: record it even if the attempt had been given up on.
        conn.execute(
            "UPDATE payments SET status = 'succeeded', failure_reason = NULL, paid_at = ?, updated_at = ? WHERE id = ?",
            (now, now, payment["id"]),
        )
        try:
            apply_transition(conn, payment["order_id"], "awaiting_payment", "paid", PAYMENT_CONFIRMED, now)
            result = "order paid"
        except OrderChanged:
            # Cancelled (for example by the deadline) or already paid by another attempt:
            # this payment goes back to the customer (FR79, FR80).
            state = conn.execute("SELECT status FROM orders WHERE id = ?", (payment["order_id"],)).fetchone()["status"]
            reason = "Duplicate payment" if state != "cancelled" else "Paid after the order was cancelled"
            refund_ids = create_refunds(conn, payment["order_id"], reason, now, payment_id=payment["id"])
            result = "refunding"
    log.info("payment_notification reference=%s result=%s", note.reference, result)
    process_refunds(conn, settings, refund_ids)
    return result


def process_refunds(conn: Database, settings: Settings, refund_ids: list[int], provider: PaymentProvider | None = None) -> None:
    """Send pending refunds to the provider and record the answer (FR82)."""
    provider = provider or get_provider(settings)
    for refund_id in refund_ids:
        refund = conn.execute(
            """SELECT r.id, r.amount_cents, p.reference FROM refunds r JOIN payments p ON p.id = r.payment_id
               WHERE r.id = ? AND r.status IN ('pending', 'failed')""",
            (refund_id,),
        ).fetchone()
        conn.commit()
        if refund is None:
            continue
        try:
            reference = provider.refund(conn, refund["reference"], refund["amount_cents"])
        except RefundFailed as exc:
            # Never overwrite a success recorded by a simultaneous attempt for the same refund.
            conn.execute(
                "UPDATE refunds SET status = 'failed', failure_reason = ?, updated_at = ? WHERE id = ? AND status <> 'refunded'",
                (str(exc), utcnow().isoformat(), refund_id),
            )
            conn.commit()
            log.error("refund_failed refund=%s payment=%s reason=%s", refund_id, refund["reference"], exc)
            continue
        conn.execute(
            "UPDATE refunds SET status = 'refunded', reference = ?, failure_reason = NULL, updated_at = ? WHERE id = ?",
            (reference, utcnow().isoformat(), refund_id),
        )
        refund_completed(conn, refund_id)
        conn.commit()
        log.info("refunded refund=%s payment=%s", refund_id, refund["reference"])


def retry_failed_refunds(conn: Database, settings: Settings, order_id: int) -> int:
    """Administrator action: send the order's failed refunds again (FR82)."""
    refund_ids = [
        row["id"]
        for row in conn.execute(
            """SELECT r.id FROM refunds r JOIN payments p ON p.id = r.payment_id
               WHERE p.order_id = ? AND r.status = 'failed'""",
            (order_id,),
        )
    ]
    if not refund_ids:
        raise ValidationProblem(["This order has no failed refund to retry."], status.HTTP_409_CONFLICT)
    process_refunds(conn, settings, refund_ids)
    return len(refund_ids)
