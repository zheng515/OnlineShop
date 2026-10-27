"""Preconfigured accounts (FR3) and optional demo products."""

import sqlite3
from pathlib import Path

from .security import hash_password, utcnow

# Customer self-registration is out of scope, so all accounts are created here.
DEFAULT_USERS = [
    ("admin", "admin123", "admin", "Administrator"),
    ("alice", "alice123", "customer", "Alice"),
    ("bob", "bob123", "customer", "Bob"),
]

DEMO_PRODUCTS = [
    ("Classic Cotton T-Shirt", 1999, "#3b82f6", {"S": 12, "M": 20, "L": 15, "XL": 8}),
    ("Striped Polo Shirt", 3450, "#10b981", {"S": 5, "M": 0, "L": 9}),
    ("Hooded Sweatshirt", 5900, "#f59e0b", {"M": 7, "L": 4, "XL": 2}),
    ("Linen Summer Shirt", 4200, "#ef4444", {"S": 3, "M": 6, "L": 0, "XL": 0}),
    ("Graphic Print Tee", 2499, "#8b5cf6", {"S": 0, "M": 0, "L": 0, "XL": 0}),
    ("Denim Jacket", 8999, "#0ea5e9", {"M": 4, "L": 6, "XL": 3}),
]


def _shirt_svg(color: str, label: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">
  <rect width="400" height="400" fill="#f3f4f6"/>
  <path d="M140 70 L95 95 L50 150 L95 185 L120 160 L120 330 L280 330 L280 160 L305 185 L350 150
           L305 95 L260 70 Q240 105 200 105 Q160 105 140 70 Z" fill="{color}" stroke="#1f2937"
        stroke-width="4" stroke-linejoin="round"/>
  <text x="200" y="370" font-family="Arial, sans-serif" font-size="22" text-anchor="middle"
        fill="#374151">{label}</text>
</svg>
"""


def seed(conn: sqlite3.Connection, upload_dir: Path, with_demo_products: bool) -> None:
    for username, password, role, display_name in DEFAULT_USERS:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), role, display_name),
            )

    # Demo products are only created once, so an administrator deleting them
    # does not bring them back on the next restart.
    already_seeded = conn.execute("SELECT 1 FROM meta WHERE key = 'demo_products_seeded'").fetchone()
    if with_demo_products and not already_seeded:
        upload_dir.mkdir(parents=True, exist_ok=True)
        now = utcnow().isoformat()
        for index, (name, price_cents, color, stock) in enumerate(DEMO_PRODUCTS, start=1):
            file_name = f"demo-{index}.svg"
            (upload_dir / file_name).write_text(_shirt_svg(color, name), encoding="utf-8")
            cursor = conn.execute(
                "INSERT INTO products (name, price_cents, image, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, price_cents, file_name, now, now),
            )
            conn.executemany(
                "INSERT INTO product_sizes (product_id, size, stock) VALUES (?, ?, ?)",
                [(cursor.lastrowid, size, qty) for size, qty in stock.items()],
            )
        conn.execute("INSERT INTO meta (key, value) VALUES ('demo_products_seeded', '1')")
    conn.commit()
