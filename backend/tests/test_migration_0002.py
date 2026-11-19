"""Migration 0002 (payments) on a database that already holds orders (FR69, FR87)."""

from alembic import command

from app.database import connect
from app.migrations import _config, current_revision


def _seed_rev6_order(url: str) -> list[int]:
    """Three orders as rev. 6 created them (ids assigned by the database, as the app does)."""
    conn = connect(url)
    ids = []
    conn.execute("INSERT INTO users (username, password_hash, role, display_name) VALUES ('ann', 'x', 'customer', 'Ann')")
    for index, status in enumerate(("placed", "shipped", "cancelled"), start=1):
        order_id = conn.insert(
            """INSERT INTO orders (user_id, status, source, total_cents, request_id, created_at, updated_at)
               VALUES (1, ?, 'cart', 500, ?, '2026-11-01', '2026-11-01')""",
            (status, f"req-{index}"),
        )
        ids.append(order_id)
        conn.execute(
            """INSERT INTO order_items (order_id, product_id, product_name, image, size, unit_price_cents, quantity,
               subtotal_cents) VALUES (?, 1, 'Tee', 'tee.png', 'M', 500, 1, 500)""",
            (order_id,),
        )
        conn.execute(
            """INSERT INTO order_events (order_id, status, actor_role, actor_name, created_at)
               VALUES (?, 'placed', 'customer', 'ann', 'x')""",
            (order_id,),
        )
    conn.commit()
    conn.close()
    return ids


def test_existing_orders_survive_and_placed_becomes_paid(database_url):
    command.upgrade(_config(database_url), "0001")
    ids = _seed_rev6_order(database_url)

    command.upgrade(_config(database_url), "0002")
    assert current_revision(database_url) == "0002"
    conn = connect(database_url)
    statuses = [tuple(row) for row in conn.execute("SELECT id, status FROM orders ORDER BY id")]
    assert statuses == list(zip(ids, ["paid", "shipped", "cancelled"], strict=True))
    # Rebuilding the table must not cascade into the rows that point at it.
    assert conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM order_events").fetchone()[0] == 3
    assert conn.execute("SELECT expires_at, paid_at FROM orders WHERE id = ?", (ids[0],)).fetchone()[:] == (None, None)

    # Order numbers keep increasing, and the new statuses are accepted.
    new_id = conn.insert(
        """INSERT INTO orders (user_id, status, source, total_cents, request_id, created_at, updated_at, expires_at)
           VALUES (1, 'awaiting_payment', 'cart', 500, 'req-new', 'now', 'now', 'later')"""
    )
    conn.commit()
    assert new_id > max(ids)
    try:
        conn.execute("UPDATE orders SET status = 'placed' WHERE id = ?", (new_id,))
        raise AssertionError("old status accepted")
    except conn.IntegrityError:
        conn.rollback()
    conn.close()


def test_downgrade_restores_rev6_statuses(database_url):
    command.upgrade(_config(database_url), "0001")
    _seed_rev6_order(database_url)
    command.upgrade(_config(database_url), "0002")
    command.downgrade(_config(database_url), "0001")
    conn = connect(database_url)
    assert [row[0] for row in conn.execute("SELECT status FROM orders ORDER BY id")] == ["placed", "shipped", "cancelled"]
    assert conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] == 3
    conn.close()
    command.upgrade(_config(database_url), "0002")
    assert current_revision(database_url) == "0002"
