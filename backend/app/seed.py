"""Demo accounts and demo products for development and demonstrations (FR3, FR39, FR54).

Real accounts are created with the account command (app/accounts.py).
"""

from pathlib import Path

from .database import Database
from .security import hash_password, utcnow, verify_password

# Publicly known passwords: only created when demo data is enabled.
DEMO_USERS = [
    ("admin", "admin123", "admin", "Administrator"),
    ("alice", "alice123", "customer", "Alice"),
    ("bob", "bob12345", "customer", "Bob"),
]
# Confirmed addresses, so the demo shows account and order emails (FR96).
DEMO_EMAILS = {"alice": "alice@example.com", "bob": "bob@example.com"}

DEMO_CATEGORIES = ["T-Shirts", "Shirts", "Hoodies & Sweatshirts", "Jackets"]

# (name, price in cents, colour, stock, category, description)
DEMO_PRODUCTS = [
    ("Classic Cotton T-Shirt", 1999, "#3b82f6", {"S": 12, "M": 20, "L": 15, "XL": 8}, "T-Shirts",
     "Soft, breathable 100% cotton tee with a regular fit.\nMachine washable at 30 °C."),
    ("Striped Polo Shirt", 3450, "#10b981", {"S": 5, "M": 0, "L": 9}, "Shirts",
     "Piqué polo with a two-button placket and classic stripes."),
    ("Hooded Sweatshirt", 5900, "#f59e0b", {"M": 7, "L": 4, "XL": 2}, "Hoodies & Sweatshirts",
     "Brushed fleece hoodie with a kangaroo pocket and adjustable hood."),
    ("Linen Summer Shirt", 4200, "#ef4444", {"S": 3, "M": 6, "L": 0, "XL": 0}, "Shirts",
     "Lightweight linen shirt that keeps you cool on hot days."),
    ("Graphic Print Tee", 2499, "#8b5cf6", {"S": 0, "M": 0, "L": 0, "XL": 0}, "T-Shirts",
     "Cotton tee with a bold front print. Currently sold out."),
    ("Denim Jacket", 8999, "#0ea5e9", {"M": 4, "L": 6, "XL": 3}, "Jackets",
     "Timeless denim jacket with button-flap chest pockets."),
    ("V-Neck Essential Tee", 1599, "#64748b", {"S": 10, "M": 10, "L": 10}, "T-Shirts",
     "Everyday V-neck tee in a slim fit."),
    ("Oxford Button-Down Shirt", 4900, "#93c5fd", {"S": 4, "M": 8, "L": 8, "XL": 4}, "Shirts",
     "Crisp Oxford cotton shirt with a button-down collar."),
    ("Zip-Up Hoodie", 6400, "#334155", {"S": 2, "M": 5, "L": 5, "XL": 1}, "Hoodies & Sweatshirts",
     "Full-zip hoodie with ribbed cuffs and hem."),
    ("Crew Neck Sweatshirt", 4500, "#a855f7", {"M": 6, "L": 0}, "Hoodies & Sweatshirts",
     "Relaxed crew neck sweatshirt in heavyweight cotton."),
    ("Lightweight Bomber Jacket", 9900, "#166534", {"M": 3, "L": 2}, "Jackets",
     "Water-repellent bomber with a ribbed collar."),
    ("Long Sleeve Henley", 2899, "#b45309", {"S": 6, "M": 6, "L": 6, "XL": 6}, "T-Shirts",
     "Waffle-knit henley with a three-button placket."),
    ("Flannel Check Shirt", 3999, "#dc2626", {"S": 0, "M": 3, "L": 7, "XL": 2}, "Shirts",
     "Warm brushed flannel shirt in a classic check."),
    ("Puffer Jacket", 12900, "#1e3a8a", {"S": 2, "M": 4, "L": 4, "XL": 2}, "Jackets",
     "Insulated puffer jacket for cold days."),
    ("Pocket Tee", 1799, "#facc15", {"S": 8, "M": 0, "L": 8}, "T-Shirts",
     "Garment-dyed tee with a chest pocket."),
    ("Windbreaker", 5500, "#0d9488", {"M": 0, "L": 0, "XL": 5}, "Jackets",
     "Packable windbreaker with an adjustable hood."),
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


def _back_svg(color: str, label: str) -> str:
    # A second demo image per product so the gallery has something to show (FR62).
    return _shirt_svg(color, f"{label} (back)").replace("Q240 105 200 105 Q160 105 140 70", "Q240 80 200 80 Q160 80 140 70")


def seed(conn: Database, upload_dir: Path, with_demo_data: bool) -> None:
    if not with_demo_data:
        return
    # Several server workers may start at once: ON CONFLICT makes each insert safe to repeat.
    now = utcnow().isoformat()
    for username, password, role, display_name in DEMO_USERS:
        email = DEMO_EMAILS.get(username)
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO users (username, password_hash, role, display_name, email, email_verified_at)
                   VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (username, hash_password(password), role, display_name, email, now if email else None),
            )
        elif email:
            # Demo accounts created before accounts had email addresses.
            conn.execute(
                """UPDATE users SET email = ?, email_verified_at = ? WHERE username = ? AND email IS NULL
                   AND NOT EXISTS (SELECT 1 FROM users WHERE email = ?)""",
                (email, now, username, email),
            )
    conn.commit()

    # Demo products are only created once, so an administrator deleting them does not
    # bring them back on the next restart. Claiming the flag first means only one worker
    # creates them; the others' inserts wait for it and then do nothing.
    claimed = conn.execute(
        "INSERT INTO meta (key, value) VALUES ('demo_products_seeded', '1') ON CONFLICT DO NOTHING"
    ).rowcount == 1
    if claimed:
        upload_dir.mkdir(parents=True, exist_ok=True)
        now = utcnow().isoformat()
        category_ids = {}
        for name in DEMO_CATEGORIES:
            existing = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
            category_ids[name] = existing["id"] if existing else conn.insert(
                "INSERT INTO categories (name, created_at) VALUES (?, ?)", (name, now)
            )
        for index, (name, price_cents, color, stock, category, description) in enumerate(DEMO_PRODUCTS, start=1):
            files = [f"demo-{index}.svg", f"demo-{index}-back.svg"]
            (upload_dir / files[0]).write_text(_shirt_svg(color, name), encoding="utf-8")
            (upload_dir / files[1]).write_text(_back_svg(color, name), encoding="utf-8")
            product_id = conn.insert(
                """INSERT INTO products (name, price_cents, image, description, category_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, price_cents, files[0], description, category_ids[category], now, now),
            )
            conn.executemany(
                "INSERT INTO product_sizes (product_id, size, stock) VALUES (?, ?, ?)",
                [(product_id, size, qty) for size, qty in stock.items()],
            )
            conn.executemany(
                "INSERT INTO product_images (product_id, file, position, uploaded_at) VALUES (?, ?, ?, ?)",
                [(product_id, file_name, position, now) for position, file_name in enumerate(files)],
            )
    conn.commit()


def accounts_with_demo_passwords(conn: Database) -> list[str]:
    """Usernames that still use their publicly known demo password."""
    found = []
    for username, password, _, _ in DEMO_USERS:
        row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
        if row and verify_password(password, row["password_hash"]):
            found.append(username)
    return found
