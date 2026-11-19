"""Order placement, cancellation and status changes (FR41-FR50, FR79, FR82, FR87)."""

from datetime import datetime

from fastapi import HTTPException, status

from .database import Database, Row, write_transaction
from .errors import ValidationProblem
from .images import image_url
from .orders import Line, cart_lines, evaluate_lines
from .products import format_cents, get_product
from .security import utcnow

STATUS_LABELS = {
    "awaiting_payment": "Awaiting payment",
    "paid": "Paid",
    "shipped": "Shipped",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
# Wording in the status history. "placed" only occurs in orders from before payments (FR87).
EVENT_LABELS = {**STATUS_LABELS, "awaiting_payment": "Order placed", "placed": "Placed"}

# (from, to) -> who may make the change (FR47). "system" covers payment confirmations
# and the payment deadline.
TRANSITIONS = {
    ("awaiting_payment", "paid"): {"system"},
    ("awaiting_payment", "cancelled"): {"customer", "admin", "system"},
    ("paid", "shipped"): {"admin"},
    ("paid", "cancelled"): {"customer", "admin"},
    ("shipped", "completed"): {"admin"},
}

PAYMENT_LABELS = {"pending": "Pending", "succeeded": "Paid", "failed": "Failed"}
REFUND_LABELS = {"pending": "Pending", "refunded": "Refunded", "failed": "Failed"}


class OrderChanged(Exception):
    """The order was no longer in the expected status when a change was applied."""


def system_actor(name: str) -> dict:
    return {"role": "system", "username": name}

PRICE_CHANGED = "Prices have changed since this page was opened. Please review the updated total and place the order again."


def order_number(order_id: int) -> str:
    return f"#{order_id:06d}"


def image_referenced_by_orders(conn: Database, file_name: str) -> bool:
    return conn.execute("SELECT 1 FROM order_items WHERE image = ? LIMIT 1", (file_name,)).fetchone() is not None


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")


def _record_event(conn: Database, order_id: int, new_status: str, actor: Row | dict, now: str) -> None:
    conn.execute(
        "INSERT INTO order_events (order_id, status, actor_role, actor_name, created_at) VALUES (?, ?, ?, ?, ?)",
        (order_id, new_status, actor["role"], actor["username"], now),
    )


def _order_for_request(conn: Database, user_id: int, request_id: str) -> int | None:
    row = conn.execute("SELECT id FROM orders WHERE user_id = ? AND request_id = ?", (user_id, request_id)).fetchone()
    return row["id"] if row else None


def place_order(
    conn: Database,
    customer: Row,
    source: str,
    buy_now_line: Line | None,
    expected_total_cents: int,
    request_id: str,
    payment_deadline: datetime,
) -> tuple[int, bool]:
    """Place an order atomically, awaiting payment until `payment_deadline` (FR41, FR79).

    Returns (order_id, created); created is False for a repeated request (FR43)."""
    try:
        return _place_order(conn, customer, source, buy_now_line, expected_total_cents, request_id, payment_deadline)
    except conn.IntegrityError:
        # The same request was placed concurrently by another process (PostgreSQL does not
        # serialise the two the way SQLite's write lock does); return the order it created.
        existing = _order_for_request(conn, customer["id"], request_id)
        if existing is None:
            raise
        return existing, False


def _place_order(
    conn: Database,
    customer: Row,
    source: str,
    buy_now_line: Line | None,
    expected_total_cents: int,
    request_id: str,
    payment_deadline: datetime,
) -> tuple[int, bool]:
    with write_transaction(conn):
        existing = _order_for_request(conn, customer["id"], request_id)
        if existing:
            return existing, False

        lines = cart_lines(conn, customer["id"]) if source == "cart" else [buy_now_line]
        summary = evaluate_lines(conn, lines)
        summary["source"] = source
        if not summary["valid"]:
            raise ValidationProblem(summary["issues"], status.HTTP_409_CONFLICT, extra={"summary": summary})
        if summary["total_cents"] != expected_total_cents:
            raise ValidationProblem([PRICE_CHANGED], status.HTTP_409_CONFLICT, extra={"summary": summary})

        now = utcnow().isoformat()
        order_id = conn.insert(
            """INSERT INTO orders (user_id, status, source, total_cents, request_id, created_at, updated_at, expires_at)
               VALUES (?, 'awaiting_payment', ?, ?, ?, ?, ?, ?)""",
            (customer["id"], source, summary["total_cents"], request_id, now, now, payment_deadline.isoformat()),
        )

        for line in lines:
            product = get_product(conn, line.product_id)
            # The write lock makes this guard redundant today; it keeps stock from
            # ever going negative should the locking strategy change (FR44).
            deducted = conn.execute(
                "UPDATE product_sizes SET stock = stock - ? WHERE product_id = ? AND size = ? AND stock >= ?",
                (line.quantity, line.product_id, line.size, line.quantity),
            ).rowcount
            if deducted != 1:
                raise ValidationProblem(
                    [f"Not enough stock left in size {line.size} of \"{product['name']}\"."], status.HTTP_409_CONFLICT
                )
            conn.execute(
                """INSERT INTO order_items
                   (order_id, product_id, product_name, image, size, unit_price_cents, quantity, subtotal_cents)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id,
                    product["id"],
                    product["name"],
                    product["image"],
                    line.size,
                    product["price_cents"],
                    line.quantity,
                    product["price_cents"] * line.quantity,
                ),
            )

        _record_event(conn, order_id, "awaiting_payment", customer, now)
        if source == "cart":
            conn.executemany("DELETE FROM cart_items WHERE id = ?", [(line.cart_item_id,) for line in lines])
    return order_id, True


def create_refunds(conn: Database, order_id: int, reason: str, now: str, payment_id: int | None = None) -> list[int]:
    """Record a pending full refund for each paid payment of the order that has none yet (FR82).

    Runs inside the caller's transaction; the refunds are sent to the provider after it commits."""
    query = "SELECT id, amount_cents FROM payments WHERE order_id = ? AND status = 'succeeded'"
    params: tuple = (order_id,)
    if payment_id is not None:
        query += " AND id = ?"
        params += (payment_id,)
    refund_ids = []
    for payment in conn.execute(query, params).fetchall():
        # The unique payment_id makes a second refund of the same payment impossible.
        row = conn.execute(
            """INSERT INTO refunds (payment_id, amount_cents, status, reason, created_at, updated_at)
               VALUES (?, ?, 'pending', ?, ?, ?) ON CONFLICT DO NOTHING RETURNING id""",
            (payment["id"], payment["amount_cents"], reason, now, now),
        ).fetchone()
        if row:
            refund_ids.append(row[0])
    return refund_ids


def apply_transition(
    conn: Database, order_id: int, current: str, new_status: str, actor: Row | dict, now: str
) -> list[int]:
    """Change the status inside the caller's transaction. Returns ids of refunds to send.

    The update only succeeds if the order is still in `current`, so two simultaneous changes
    cannot both win (FR47). Raises OrderChanged otherwise."""
    sets, params = ["status = ?", "updated_at = ?"], [new_status, now]
    if new_status == "paid":
        sets += ["paid_at = ?", "expires_at = NULL"]
        params.append(now)
    if new_status == "cancelled":
        sets.append("expires_at = NULL")
    updated = conn.execute(
        f"UPDATE orders SET {', '.join(sets)} WHERE id = ? AND status = ?", [*params, order_id, current]
    ).rowcount
    if updated != 1:
        raise OrderChanged

    refund_ids: list[int] = []
    if new_status == "cancelled":
        # Sizes that were removed, or products that were deleted, get nothing back (FR48).
        conn.executemany(
            "UPDATE product_sizes SET stock = stock + ? WHERE product_id = ? AND size = ?",
            [
                (item["quantity"], item["product_id"], item["size"])
                for item in conn.execute(
                    "SELECT product_id, size, quantity FROM order_items WHERE order_id = ?", (order_id,)
                )
            ],
        )
        conn.execute(
            """UPDATE payments SET status = 'failed', failure_reason = 'The order was cancelled before payment.',
               updated_at = ? WHERE order_id = ? AND status = 'pending'""",
            (now, order_id),
        )
        # Orders from before payments have no payments, so nothing is refunded (FR87).
        refund_ids = create_refunds(conn, order_id, "Order cancelled", now)
    _record_event(conn, order_id, new_status, actor, now)
    return refund_ids


def change_status(
    conn: Database, order_id: int, new_status: str, actor: Row | dict, owner_id: int | None = None
) -> list[int]:
    """Apply a status change allowed by FR47. Cancelling puts the stock back (FR48) and, for a
    paid order, records a refund. Returns the ids of refunds to send to the payment provider."""
    with write_transaction(conn):
        query = "SELECT id, status FROM orders WHERE id = ?"
        params: tuple = (order_id,)
        if owner_id is not None:
            query += " AND user_id = ?"
            params += (owner_id,)
        order = conn.execute(query, params).fetchone()
        if order is None:
            raise _not_found()

        current = order["status"]
        if actor["role"] not in TRANSITIONS.get((current, new_status), set()):
            if new_status == "cancelled":
                message = f"This order is {STATUS_LABELS[current]} and can no longer be cancelled."
            else:
                message = f"An order that is {STATUS_LABELS[current]} cannot be marked as {STATUS_LABELS[new_status]}."
            raise ValidationProblem([message], status.HTTP_409_CONFLICT)
        try:
            return apply_transition(conn, order_id, current, new_status, actor, utcnow().isoformat())
        except OrderChanged:
            raise ValidationProblem(
                ["This order was changed at the same time by someone else. Please reload it and try again."],
                status.HTTP_409_CONFLICT,
            ) from None


def _allowed_actions(current: str, role: str) -> list[str]:
    return [to for (frm, to), roles in TRANSITIONS.items() if frm == current and role in roles]


ORDER_SELECT = """
    SELECT o.*, u.username, u.display_name,
           (SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = o.id) AS item_count
    FROM orders o JOIN users u ON u.id = o.user_id
"""


def _seconds_left(expires_at: str | None) -> int | None:
    if not expires_at:
        return None
    return max(0, int((datetime.fromisoformat(expires_at) - utcnow()).total_seconds()))


def _summary(row: Row, viewer_role: str) -> dict:
    return {
        "id": row["id"],
        "number": order_number(row["id"]),
        "status": row["status"],
        "status_label": STATUS_LABELS[row["status"]],
        "source": row["source"],
        "total": format_cents(row["total_cents"]),
        "item_count": row["item_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "payment_deadline": row["expires_at"],
        "seconds_left": _seconds_left(row["expires_at"]) if row["status"] == "awaiting_payment" else None,
        "paid_at": row["paid_at"],
        "customer": {"username": row["username"], "display_name": row["display_name"]},
        "allowed_actions": _allowed_actions(row["status"], viewer_role),
    }


def list_orders(
    conn: Database, viewer_role: str, user_id: int | None = None, status_filter: str | None = None, keyword: str = ""
) -> list[dict]:
    clauses, params = [], []
    if user_id is not None:
        clauses.append("o.user_id = ?")
        params.append(user_id)
    if status_filter:
        clauses.append("o.status = ?")
        params.append(status_filter)
    needle = keyword.strip()
    if needle:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        # Portable '#' + six-digit number (FR45); LIKE is case-sensitive in PostgreSQL, so fold both sides.
        number = (
            "('#' || CASE WHEN length(CAST(o.id AS TEXT)) >= 6 THEN CAST(o.id AS TEXT) "
            "ELSE substr('000000' || CAST(o.id AS TEXT), length(CAST(o.id AS TEXT)) + 1) END)"
        )
        clauses.append(
            f"({number} LIKE ? ESCAPE '\\' OR casefold(u.username) LIKE ? ESCAPE '\\'"
            " OR casefold(u.display_name) LIKE ? ESCAPE '\\')"
        )
        params += [pattern, pattern.casefold(), pattern.casefold()]
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"{ORDER_SELECT}{where} ORDER BY o.id DESC", params).fetchall()
    return [_summary(row, viewer_role) for row in rows]


def get_order(conn: Database, order_id: int, viewer_role: str, user_id: int | None = None) -> dict:
    query, params = f"{ORDER_SELECT} WHERE o.id = ?", [order_id]
    if user_id is not None:
        query += " AND o.user_id = ?"
        params.append(user_id)
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise _not_found()

    order = _summary(row, viewer_role)
    order["items"] = [
        {
            "product_id": item["product_id"],
            "name": item["product_name"],
            "image_url": image_url(item["image"]),
            "size": item["size"],
            "unit_price": format_cents(item["unit_price_cents"]),
            "quantity": item["quantity"],
            "subtotal": format_cents(item["subtotal_cents"]),
        }
        for item in conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,))
    ]
    order["history"] = [
        {
            "status": event["status"],
            "status_label": EVENT_LABELS[event["status"]],
            "actor_role": event["actor_role"],
            "actor_name": event["actor_name"],
            "created_at": event["created_at"],
        }
        for event in conn.execute("SELECT * FROM order_events WHERE order_id = ? ORDER BY id", (order_id,))
    ]
    # Payment attempts and refunds, newest first (FR83).
    order["payments"] = [
        {
            "provider": payment["provider"],
            "reference": payment["reference"],
            "amount": format_cents(payment["amount_cents"]),
            "currency": payment["currency"],
            "status": payment["status"],
            "status_label": PAYMENT_LABELS[payment["status"]],
            "failure_reason": payment["failure_reason"],
            "created_at": payment["created_at"],
            "paid_at": payment["paid_at"],
        }
        for payment in conn.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY id DESC", (order_id,))
    ]
    order["refunds"] = [
        {
            "amount": format_cents(refund["amount_cents"]),
            "status": refund["status"],
            "status_label": REFUND_LABELS[refund["status"]],
            "reason": refund["reason"],
            "reference": refund["reference"],
            "failure_reason": refund["failure_reason"],
            "payment_reference": refund["payment_reference"],
            "created_at": refund["created_at"],
            "updated_at": refund["updated_at"],
        }
        for refund in conn.execute(
            """SELECT r.*, p.reference AS payment_reference FROM refunds r JOIN payments p ON p.id = r.payment_id
               WHERE p.order_id = ? ORDER BY r.id DESC""",
            (order_id,),
        )
    ]
    order["can_retry_refund"] = viewer_role == "admin" and any(r["status"] == "failed" for r in order["refunds"])
    return order
