"""Delivery: address book, delivery methods and fees, delivery details of orders (SRS rev. 9).

- addresses: customers' address books (FR100, FR101).
- shipping_methods: delivery methods and fees (FR103), with the two initial methods.
- orders: items total, delivery fee, delivery address and method as they were when the order
  was placed (FR106, FR107), and the carrier and tracking number once shipped (FR108).
  Earlier orders get an items total equal to their total and a fee of 0 (FR109).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NO_ID_REUSE = {"sqlite_autoincrement": True}
NOW = "2026-11-20T00:00:00+00:00"

ORDER_COLUMNS = [
    ("items_cents", sa.Integer),
    ("delivery_full_name", sa.Text),
    ("delivery_phone", sa.Text),
    ("delivery_line1", sa.Text),
    ("delivery_line2", sa.Text),
    ("delivery_city", sa.Text),
    ("delivery_region", sa.Text),
    ("delivery_postal_code", sa.Text),
    ("delivery_country", sa.Text),
    ("delivery_method", sa.Text),
    ("carrier", sa.Text),
    ("tracking_number", sa.Text),
]


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("line1", sa.Text, nullable=False),
        sa.Column("line2", sa.Text, nullable=False, server_default=""),
        sa.Column("city", sa.Text, nullable=False),
        sa.Column("region", sa.Text, nullable=False, server_default=""),
        sa.Column("postal_code", sa.Text, nullable=False),
        sa.Column("country", sa.Text, nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    op.create_index("idx_addresses_user", "addresses", ["user_id", "id"])

    shipping_methods = op.create_table(
        "shipping_methods",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("fee_cents", sa.Integer, nullable=False),
        sa.Column("free_over_cents", sa.Integer),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("fee_cents >= 0", name="shipping_methods_fee_check"),
        sa.CheckConstraint("free_over_cents IS NULL OR free_over_cents > 0", name="shipping_methods_free_over_check"),
        **NO_ID_REUSE,
    )
    op.execute("CREATE UNIQUE INDEX idx_shipping_methods_name ON shipping_methods (lower(name))")
    # Existing shops keep taking orders after the upgrade (FR103).
    op.bulk_insert(
        shipping_methods,
        [
            {"name": "Standard delivery", "description": "3–5 business days", "fee_cents": 500,
             "free_over_cents": 5000, "active": True, "created_at": NOW, "updated_at": NOW},
            {"name": "Express delivery", "description": "1–2 business days", "fee_cents": 1500,
             "free_over_cents": None, "active": True, "created_at": NOW, "updated_at": NOW},
        ],
    )

    for name, column_type in ORDER_COLUMNS:
        op.add_column("orders", sa.Column(name, column_type))
    op.add_column("orders", sa.Column("shipping_cents", sa.Integer, nullable=False, server_default="0"))
    op.execute("UPDATE orders SET items_cents = total_cents")  # earlier orders had no delivery fee (FR109)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        for name, _ in ORDER_COLUMNS:
            batch.drop_column(name)
        batch.drop_column("shipping_cents")
    op.drop_table("shipping_methods")
    op.drop_table("addresses")
