"""Product data access, serialisation and validation (FR13)."""

import json
import sqlite3
from decimal import Decimal, InvalidOperation

from .config import SIZES
from .errors import ValidationProblem
from .images import image_url

MAX_NAME_LENGTH = 100
MAX_PRICE = Decimal("1000000")
MAX_STOCK = 1_000_000


def format_cents(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def get_product(conn: sqlite3.Connection, product_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        return None
    return _with_sizes(conn, [row])[0]


def list_products(conn: sqlite3.Connection, keyword: str = "") -> list[dict]:
    rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    # Case-insensitive matching is done in Python so it also works for
    # non-ASCII names, which SQLite's LIKE does not case-fold.
    needle = keyword.strip().casefold()
    if needle:
        rows = [row for row in rows if needle in row["name"].casefold()]
    return _with_sizes(conn, rows)


def _with_sizes(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    stock: dict[int, dict[str, int]] = {pid: {} for pid in ids}
    for size_row in conn.execute(
        f"SELECT product_id, size, stock FROM product_sizes WHERE product_id IN ({placeholders})", ids
    ):
        stock[size_row["product_id"]][size_row["size"]] = size_row["stock"]

    products = []
    for row in rows:
        sizes = [{"size": size, "stock": stock[row["id"]][size]} for size in SIZES if size in stock[row["id"]]]
        products.append(
            {
                "id": row["id"],
                "name": row["name"],
                "price": format_cents(row["price_cents"]),
                "price_cents": row["price_cents"],
                "image": row["image"],
                "image_url": image_url(row["image"]),
                "sizes": sizes,
                "stock": {s["size"]: s["stock"] for s in sizes},
                "total_stock": sum(s["stock"] for s in sizes),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return products


def admin_view(product: dict) -> dict:
    return {key: product[key] for key in ("id", "name", "price", "image_url", "sizes", "total_stock", "created_at", "updated_at")}


def customer_summary(product: dict) -> dict:
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "image_url": product["image_url"],
        "in_stock": product["total_stock"] > 0,
    }


def customer_detail(product: dict) -> dict:
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "image_url": product["image_url"],
        "sizes": [{**s, "in_stock": s["stock"] > 0} for s in product["sizes"]],
        "all_sizes": list(SIZES),
    }


def validate_product_fields(name: str, price: str, stock: str) -> tuple[str, int, dict[str, int]]:
    """Validate the textual product fields. Raises ValidationProblem listing every problem."""
    errors: list[str] = []

    clean_name = (name or "").strip()
    if not clean_name:
        errors.append("Product name is required.")
    elif len(clean_name) > MAX_NAME_LENGTH:
        errors.append(f"Product name must be at most {MAX_NAME_LENGTH} characters.")

    price_cents = 0
    try:
        price_value = Decimal((price or "").strip())
        if not price_value.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        errors.append("Price must be a number greater than zero.")
    else:
        if price_value <= 0:
            errors.append("Price must be greater than zero.")
        elif price_value > MAX_PRICE:
            errors.append(f"Price must not exceed {MAX_PRICE}.")
        elif price_value != price_value.quantize(Decimal("0.01")):
            errors.append("Price can have at most two decimal places.")
        else:
            price_cents = int(price_value * 100)

    sizes: dict[str, int] = {}
    try:
        raw_stock = json.loads(stock) if stock else {}
    except json.JSONDecodeError:
        raw_stock = None
    if not isinstance(raw_stock, dict):
        errors.append("Stock information is malformed.")
    else:
        for size, quantity in raw_stock.items():
            if size not in SIZES:
                errors.append(f"Size '{size}' is not allowed. Sizes must be one of {', '.join(SIZES)}.")
                continue
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                errors.append(f"Stock for size {size} must be a non-negative whole number.")
                continue
            if quantity > MAX_STOCK:
                errors.append(f"Stock for size {size} must not exceed {MAX_STOCK}.")
                continue
            sizes[size] = quantity
        if not raw_stock:
            errors.append("At least one size must be available.")

    if errors:
        raise ValidationProblem(errors)
    return clean_name, price_cents, sizes
