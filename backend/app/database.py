"""SQLite storage: connection handling and schema."""

import sqlite3
from collections.abc import Iterator
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

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
    image       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

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
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()
