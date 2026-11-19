"""Initial schema: everything up to SRS rev. 5.

Matches the structure that app/legacy_schema.py gives older SQLite databases, so those can be
stamped at this revision.

Revision ID: 0001
Revises:
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# SQLite must never reuse ids of deleted rows: cart entries keep the id of a deleted
# product so the customer can be told it is gone (FR34).
NO_ID_REUSE = {"sqlite_autoincrement": True}


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer, primary_key=True)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.create_table(
        "meta",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    op.create_table(
        "users",
        _id(),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.CheckConstraint("role IN ('admin', 'customer')"),
        **NO_ID_REUSE,
    )
    # token_hash is a SHA-256 of the session identifier (FR51).
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf_token", sa.Text, nullable=False),
        sa.Column("expires_at", sa.Text, nullable=False),
    )
    op.create_table(
        "login_attempts",
        _id(),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("ip", sa.Text, nullable=False),
        sa.Column("success", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    op.create_index("idx_login_attempts_username", "login_attempts", ["username", "created_at"])
    op.create_index("idx_login_attempts_ip", "login_attempts", ["ip", "created_at"])

    op.create_table(
        "categories",
        _id(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    if dialect == "sqlite":
        op.execute("CREATE UNIQUE INDEX idx_categories_name ON categories (name COLLATE NOCASE)")
    else:
        op.execute("CREATE UNIQUE INDEX idx_categories_name ON categories (lower(name))")

    # image always holds the main image (first of product_images).
    op.create_table(
        "products",
        _id(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("price_cents", sa.Integer, nullable=False),
        sa.Column("image", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.CheckConstraint("price_cents > 0"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_products_category", "products", ["category_id"])
    op.create_index("idx_products_price", "products", ["price_cents"])

    # product_id is NULL for an uploaded image not yet attached to a product (FR14).
    op.create_table(
        "product_images",
        _id(),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE")),
        sa.Column("file", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    op.create_index("idx_product_images_product", "product_images", ["product_id", "position"])

    op.create_table(
        "product_sizes",
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("size", sa.Text, primary_key=True),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.CheckConstraint("size IN ('S', 'M', 'L', 'XL')"),
        sa.CheckConstraint("stock >= 0"),
    )

    # product_id has no foreign key on purpose: entries for deleted products stay (FR34).
    op.create_table(
        "cart_items",
        _id(),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer, nullable=False),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("size", sa.Text, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("added_at", sa.Text, nullable=False),
        sa.CheckConstraint("quantity > 0"),
        sa.UniqueConstraint("user_id", "product_id", "size"),
        **NO_ID_REUSE,
    )

    # request_id makes order placement idempotent per customer (FR43).
    op.create_table(
        "orders",
        _id(),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.CheckConstraint("status IN ('placed', 'shipped', 'completed', 'cancelled')"),
        sa.CheckConstraint("source IN ('cart', 'buy_now')"),
        sa.CheckConstraint("total_cents > 0"),
        sa.UniqueConstraint("user_id", "request_id"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_orders_user", "orders", ["user_id", "id"])

    # Items are a snapshot of what was ordered (FR45): no foreign key to products.
    op.create_table(
        "order_items",
        _id(),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer, nullable=False),
        sa.Column("product_name", sa.Text, nullable=False),
        sa.Column("image", sa.Text, nullable=False),
        sa.Column("size", sa.Text, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("subtotal_cents", sa.Integer, nullable=False),
        sa.CheckConstraint("quantity > 0"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_order_items_order", "order_items", ["order_id"])
    op.create_index("idx_order_items_image", "order_items", ["image"])

    op.create_table(
        "order_events",
        _id(),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("actor_role", sa.Text, nullable=False),
        sa.Column("actor_name", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    op.create_index("idx_order_events_order", "order_events", ["order_id"])

    if dialect == "postgresql":
        # SQL used by the application on both databases (app/database.py). SQLite has instr()
        # built in and gets casefold() from Python. lower() folds non-English letters as long
        # as the database uses a UTF-8 locale; unlike Python's casefold() it keeps "ß" (FR68).
        op.execute("CREATE FUNCTION casefold(text) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS 'SELECT lower($1)'")
        op.execute(
            "CREATE FUNCTION instr(text, text) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS 'SELECT strpos($1, $2)'"
        )


def downgrade() -> None:
    for table in (
        "order_events",
        "order_items",
        "orders",
        "cart_items",
        "product_sizes",
        "product_images",
        "products",
        "categories",
        "login_attempts",
        "sessions",
        "users",
        "meta",
    ):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION casefold(text)")
        op.execute("DROP FUNCTION instr(text, text)")
