"""Payments: order payment statuses and deadline, payments, refunds, notifications (SRS rev. 7).

- orders.status: 'placed' becomes 'paid' (FR87); new 'awaiting_payment'.
- orders.expires_at (payment deadline, FR79) and orders.paid_at.
- payments, refunds and payment_events (processed notifications, FR81).
- mock_payment_sessions: state of the built-in mock provider (FR84), which stands in for an
  external service and would not exist with a real provider.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NO_ID_REUSE = {"sqlite_autoincrement": True}
NEW_STATUSES = "('awaiting_payment', 'paid', 'shipped', 'completed', 'cancelled')"
OLD_STATUSES = "('placed', 'shipped', 'completed', 'cancelled')"


def _rebuild_sqlite_orders(status_check: str, status_expr: str, with_payment_columns: bool) -> None:
    """SQLite cannot change a CHECK constraint, so the table is rebuilt (SQLite's documented
    procedure). Foreign keys are off for migration connections, so dropping the old table does
    not cascade into order_items and order_events, which keep pointing at orders(id)."""
    bind = op.get_bind()
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError("Foreign keys must be off while rebuilding the orders table")
    sequence = bind.exec_driver_sql("SELECT seq FROM sqlite_sequence WHERE name = 'orders'").scalar()
    extra_columns = "expires_at TEXT, paid_at TEXT," if with_payment_columns else ""
    op.execute(
        f"""CREATE TABLE orders_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            total_cents INTEGER NOT NULL,
            request_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            {extra_columns}
            CHECK (status IN {status_check}),
            CHECK (source IN ('cart', 'buy_now')),
            CHECK (total_cents > 0),
            UNIQUE (user_id, request_id),
            FOREIGN KEY(user_id) REFERENCES users (id)
        )"""
    )
    columns = "id, user_id, status, source, total_cents, request_id, created_at, updated_at"
    selected = columns.replace("status", status_expr, 1)
    op.execute(f"INSERT INTO orders_new ({columns}) SELECT {selected} FROM orders")
    op.execute("DROP TABLE orders")
    op.execute("ALTER TABLE orders_new RENAME TO orders")
    op.execute("CREATE INDEX idx_orders_user ON orders (user_id, id)")
    if sequence is not None:
        # Order numbers must never be reused, even those of orders created and then removed.
        op.execute(f"UPDATE sqlite_sequence SET seq = max(seq, {int(sequence)}) WHERE name = 'orders'")


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        _rebuild_sqlite_orders(
            NEW_STATUSES, "CASE status WHEN 'placed' THEN 'paid' ELSE status END", with_payment_columns=True
        )
    else:
        op.drop_constraint("orders_status_check", "orders", type_="check")
        op.execute("UPDATE orders SET status = 'paid' WHERE status = 'placed'")
        op.create_check_constraint("orders_status_check", "orders", f"status IN {NEW_STATUSES}")
        op.add_column("orders", sa.Column("expires_at", sa.Text))
        op.add_column("orders", sa.Column("paid_at", sa.Text))
    op.create_index("idx_orders_awaiting_payment", "orders", ["status", "expires_at"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("reference", sa.Text, nullable=False, unique=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("paid_at", sa.Text),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="payments_status_check"),
        sa.CheckConstraint("amount_cents > 0", name="payments_amount_check"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_payments_order", "payments", ["order_id"])

    # One refund per payment at most (FR82): the unique constraint makes that a database rule.
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payment_id", sa.Integer, sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("reference", sa.Text),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("status IN ('pending', 'refunded', 'failed')", name="refunds_status_check"),
        **NO_ID_REUSE,
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False),
        sa.Column("received_at", sa.Text, nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="payment_events_unique"),
        **NO_ID_REUSE,
    )

    op.create_table(
        "mock_payment_sessions",
        sa.Column("reference", sa.Text, primary_key=True),
        sa.Column("merchant_order", sa.Text, nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("return_url", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("refunded_at", sa.Text),
        sa.CheckConstraint(
            "status IN ('open', 'succeeded', 'failed', 'abandoned')", name="mock_payment_sessions_status_check"
        ),
    )


def downgrade() -> None:
    op.drop_table("mock_payment_sessions")
    op.drop_table("payment_events")
    op.drop_table("refunds")
    op.drop_table("payments")
    op.drop_index("idx_orders_awaiting_payment", "orders")
    legacy = "CASE status WHEN 'paid' THEN 'placed' WHEN 'awaiting_payment' THEN 'cancelled' ELSE status END"
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite_orders(OLD_STATUSES, legacy, with_payment_columns=False)
    else:
        op.drop_constraint("orders_status_check", "orders", type_="check")
        op.execute(f"UPDATE orders SET status = {legacy}")
        op.create_check_constraint("orders_status_check", "orders", f"status IN {OLD_STATUSES}")
        op.drop_column("orders", "paid_at")
        op.drop_column("orders", "expires_at")
