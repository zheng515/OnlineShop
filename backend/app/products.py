"""Product data access, catalogue queries, serialisation and validation (FR13, FR60-FR67)."""

import math
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from .config import SIZES
from .errors import ValidationProblem
from .images import image_url

MAX_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 2000
MAX_PRICE = Decimal("1000000")
MAX_STOCK = 1_000_000
MAX_IMAGES = 8

CUSTOMER_PAGE_SIZE = 12
ADMIN_PAGE_SIZE = 20

TOTAL_STOCK_SQL = "(SELECT COALESCE(SUM(stock), 0) FROM product_sizes WHERE product_id = p.id)"
SORTS = {
    "newest": "p.id DESC",
    "price_asc": "p.price_cents ASC, p.id DESC",
    "price_desc": "p.price_cents DESC, p.id DESC",
    "name": "casefold(p.name) ASC, p.id DESC",
    "stock_asc": f"{TOTAL_STOCK_SQL} ASC, p.id DESC",
}
CUSTOMER_SORTS = ("newest", "price_asc", "price_desc", "name")


def format_cents(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def parse_amount(text: str) -> int | None:
    """Parse a non-negative money amount with at most two decimals into cents; None if invalid."""
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > MAX_PRICE or value != value.quantize(Decimal("0.01")):
        return None
    return int(value * 100)


# --- Reading ---------------------------------------------------------------


PRODUCT_SELECT = """
    SELECT p.*, c.name AS category_name
    FROM products p LEFT JOIN categories c ON c.id = p.category_id
"""


def get_product(conn: sqlite3.Connection, product_id: int) -> dict | None:
    row = conn.execute(f"{PRODUCT_SELECT} WHERE p.id = ?", (product_id,)).fetchone()
    if row is None:
        return None
    return _hydrate(conn, [row])[0]


@dataclass
class CatalogueQuery:
    keyword: str = ""
    category_id: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    size: str | None = None
    in_stock_only: bool = False
    sort: str = "newest"
    page: int = 1
    page_size: int = CUSTOMER_PAGE_SIZE
    notices: list[str] = field(default_factory=list)


def search_products(conn: sqlite3.Connection, query: CatalogueQuery) -> dict:
    """One page of products matching the query; all filtering and sorting is done in SQL (FR67)."""
    clauses: list[str] = []
    params: list[Any] = []
    needle = query.keyword.strip().casefold()
    if needle:
        clauses.append("(instr(casefold(p.name), ?) > 0 OR instr(casefold(p.description), ?) > 0)")
        params += [needle, needle]
    if query.category_id is not None:
        clauses.append("p.category_id = ?")
        params.append(query.category_id)
    if query.min_price_cents is not None:
        clauses.append("p.price_cents >= ?")
        params.append(query.min_price_cents)
    if query.max_price_cents is not None:
        clauses.append("p.price_cents <= ?")
        params.append(query.max_price_cents)
    if query.size:
        clauses.append("EXISTS (SELECT 1 FROM product_sizes s WHERE s.product_id = p.id AND s.size = ? AND s.stock > 0)")
        params.append(query.size)
    if query.in_stock_only:
        clauses.append("EXISTS (SELECT 1 FROM product_sizes s WHERE s.product_id = p.id AND s.stock > 0)")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    total = conn.execute(f"SELECT COUNT(*) FROM products p{where}", params).fetchone()[0]
    pages = max(1, math.ceil(total / query.page_size))
    page = min(max(1, query.page), pages)
    rows = conn.execute(
        f"{PRODUCT_SELECT}{where} ORDER BY {SORTS[query.sort]} LIMIT ? OFFSET ?",
        [*params, query.page_size, (page - 1) * query.page_size],
    ).fetchall()
    return {
        "products": _hydrate(conn, rows),
        "total": total,
        "page": page,
        "pages": pages,
        "page_size": query.page_size,
        "notices": query.notices,
    }


def _hydrate(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    stock: dict[int, dict[str, int]] = {pid: {} for pid in ids}
    for size_row in conn.execute(
        f"SELECT product_id, size, stock FROM product_sizes WHERE product_id IN ({placeholders})", ids
    ):
        stock[size_row["product_id"]][size_row["size"]] = size_row["stock"]
    images: dict[int, list[dict]] = {pid: [] for pid in ids}
    for image_row in conn.execute(
        f"SELECT id, product_id, file FROM product_images WHERE product_id IN ({placeholders}) ORDER BY position, id",
        ids,
    ):
        images[image_row["product_id"]].append(
            {"id": image_row["id"], "file": image_row["file"], "url": image_url(image_row["file"])}
        )

    products = []
    for row in rows:
        sizes = [{"size": size, "stock": stock[row["id"]][size]} for size in SIZES if size in stock[row["id"]]]
        category = {"id": row["category_id"], "name": row["category_name"]} if row["category_id"] else None
        products.append(
            {
                "id": row["id"],
                "name": row["name"],
                "price": format_cents(row["price_cents"]),
                "price_cents": row["price_cents"],
                "description": row["description"],
                "category": category,
                "image": row["image"],
                "image_url": image_url(row["image"]),
                "images": images[row["id"]],
                "sizes": sizes,
                "stock": {s["size"]: s["stock"] for s in sizes},
                "total_stock": sum(s["stock"] for s in sizes),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return products


def admin_view(product: dict) -> dict:
    view = {
        key: product[key]
        for key in ("id", "name", "price", "description", "category", "image_url", "sizes", "total_stock", "created_at", "updated_at")
    }
    view["images"] = [{"id": image["id"], "url": image["url"]} for image in product["images"]]
    return view


def customer_summary(product: dict) -> dict:
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "image_url": product["image_url"],
        "category": product["category"],
        "in_stock": product["total_stock"] > 0,
    }


def customer_detail(product: dict) -> dict:
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "description": product["description"],
        "category": product["category"],
        "image_url": product["image_url"],
        "images": [image["url"] for image in product["images"]],
        "sizes": [{**s, "in_stock": s["stock"] > 0} for s in product["sizes"]],
        "all_sizes": list(SIZES),
    }


# --- Validation (FR13) -------------------------------------------------------


@dataclass
class ProductData:
    name: str
    price_cents: int
    description: str
    category_id: int | None
    sizes: dict[str, int]
    image_ids: list[int]


def validate_product(
    conn: sqlite3.Connection,
    *,
    name: Any,
    price: Any,
    description: Any,
    category_id: Any,
    stock: Any,
    image_ids: Any,
    product_id: int | None = None,
) -> ProductData:
    """Validate a product for saving. Raises ValidationProblem listing every problem."""
    errors: list[str] = []

    clean_name = str(name or "").strip()
    if not clean_name:
        errors.append("Product name is required.")
    elif len(clean_name) > MAX_NAME_LENGTH:
        errors.append(f"Product name must be at most {MAX_NAME_LENGTH} characters.")

    price_cents = 0
    try:
        price_value = Decimal(str(price).strip())
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

    clean_description = str(description or "").strip()
    if len(clean_description) > MAX_DESCRIPTION_LENGTH:
        errors.append(f"Description must be at most {MAX_DESCRIPTION_LENGTH} characters.")

    if category_id is not None and (
        not isinstance(category_id, int)
        or isinstance(category_id, bool)  # JSON true is an int in Python
        or conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None
    ):
        errors.append("The selected category no longer exists. Please choose another one.")

    sizes: dict[str, int] = {}
    if not isinstance(stock, dict):
        errors.append("Stock information is malformed.")
    else:
        for size, quantity in stock.items():
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
        if not stock:
            errors.append("At least one size must be available.")

    errors += _image_problems(conn, image_ids, product_id)

    if errors:
        raise ValidationProblem(errors)
    return ProductData(clean_name, price_cents, clean_description, category_id, sizes, list(image_ids))


def _image_problems(conn: sqlite3.Connection, image_ids: Any, product_id: int | None) -> list[str]:
    if not isinstance(image_ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in image_ids):
        return ["Image information is malformed."]
    if not image_ids:
        return ["At least one product image is required."]
    if len(image_ids) > MAX_IMAGES:
        return [f"A product can have at most {MAX_IMAGES} images."]
    if len(set(image_ids)) != len(image_ids):
        return ["The same image was added more than once."]
    placeholders = ",".join("?" * len(image_ids))
    usable = {
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM product_images WHERE id IN ({placeholders}) AND (product_id IS NULL OR product_id IS ?)",
            [*image_ids, product_id],
        )
    }
    if usable != set(image_ids):
        return ["Some images are no longer available. Please upload them again."]
    return []
