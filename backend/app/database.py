"""SQLite storage: connection handling and schema."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'customer')),
    display_name  TEXT NOT NULL
);

-- token_hash is a SHA-256 of the session identifier; the identifier itself
-- only ever lives in the browser's HttpOnly cookie (FR51).
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    ip         TEXT NOT NULL,
    success    INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_username ON login_attempts (username, created_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts (ip, created_at);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_name ON categories (name COLLATE NOCASE);

-- image always holds the main image (first of product_images), kept in sync
-- so lists, carts and order snapshots need no join.
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    image       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL
);

-- product_id is NULL for an uploaded image not yet attached to a product (FR14).
CREATE TABLE IF NOT EXISTS product_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER REFERENCES products(id) ON DELETE CASCADE,
    file        TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON product_images (product_id, position);

CREATE TABLE IF NOT EXISTS product_sizes (
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    size       TEXT NOT NULL CHECK (size IN ('S', 'M', 'L', 'XL')),
    stock      INTEGER NOT NULL CHECK (stock >= 0),
    PRIMARY KEY (product_id, size)
);

-- product_id deliberately has no foreign key: when a product is deleted the
-- cart entry is kept so the customer can be told it is no longer available
-- (FR34). product_name is a snapshot used to identify such entries.
CREATE TABLE IF NOT EXISTS cart_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    size         TEXT NOT NULL,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    added_at     TEXT NOT NULL,
    UNIQUE (user_id, product_id, size)
);

-- request_id makes order placement idempotent per customer (FR43).
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    status      TEXT NOT NULL CHECK (status IN ('placed', 'shipped', 'completed', 'cancelled')),
    source      TEXT NOT NULL CHECK (source IN ('cart', 'buy_now')),
    total_cents INTEGER NOT NULL CHECK (total_cents > 0),
    request_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, request_id)
);

-- Items are a snapshot of what was ordered (FR45), so product_id has no
-- foreign key and the name, image and price are copied.
CREATE TABLE IF NOT EXISTS order_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id       INTEGER NOT NULL,
    product_name     TEXT NOT NULL,
    image            TEXT NOT NULL,
    size             TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    subtotal_cents   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS order_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders (user_id, id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_products_price ON products (price_cents);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_image ON order_items (image);
CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events (order_id);
"""


def _casefold(value: str | None) -> str | None:
    return None if value is None else value.casefold()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # SQLite's own LIKE/lower() only fold ASCII; this folds all letters (FR16).
    conn.create_function("casefold", 1, _casefold, deterministic=True)
    return conn


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if not existing:
        return
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_schema(conn: sqlite3.Connection) -> None:
    # Databases created before rev. 4 stored raw session tokens. Sessions are
    # short-lived, so the old table is dropped (logging everyone out) rather
    # than migrated.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
    if columns and "token_hash" not in columns:
        conn.execute("DROP TABLE sessions")
    # Rev. 5 columns on databases created earlier; must exist before the
    # schema script creates indexes on them.
    _add_missing_columns(
        conn,
        "products",
        {
            "description": "TEXT NOT NULL DEFAULT ''",
            "category_id": "INTEGER REFERENCES categories(id) ON DELETE SET NULL",
        },
    )
    conn.executescript(SCHEMA)
    # Products from before rev. 5 had a single image column only.
    conn.execute(
        """INSERT INTO product_images (product_id, file, position, uploaded_at)
           SELECT p.id, p.image, 0, p.created_at FROM products p
           WHERE NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id = p.id)"""
    )
    conn.commit()


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run a block as one atomic write.

    BEGIN IMMEDIATE takes SQLite's write lock up front, so stock read inside
    the block cannot be changed by another request before the block commits.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()
