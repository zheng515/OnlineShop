"""Categories (FR60) and parsing of catalogue list parameters (FR63-FR66)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..config import SIZES
from ..database import get_db
from ..errors import ValidationProblem
from ..products import CUSTOMER_PAGE_SIZE, CUSTOMER_SORTS, CatalogueQuery, parse_amount
from ..security import get_current_user, require_admin, utcnow

MAX_CATEGORY_NAME = 50

router = APIRouter(prefix="/api", tags=["catalog"])


def catalogue_query(
    *,
    q: str = "",
    category: str = "",
    min_price: str = "",
    max_price: str = "",
    size: str = "",
    in_stock: str = "",
    sort: str = "newest",
    page: str = "1",
    allowed_sorts: tuple[str, ...] = CUSTOMER_SORTS,
    page_size: int = CUSTOMER_PAGE_SIZE,
) -> CatalogueQuery:
    """Turn raw query-string values into a query. Unusable values are ignored, with a notice where
    the customer typed them (FR63, FR65), so a shared or edited link still shows a list."""
    query = CatalogueQuery(keyword=q, page_size=page_size)
    query.sort = sort if sort in allowed_sorts else "newest"
    query.page = int(page) if page.isdigit() and int(page) > 0 else 1
    query.category_id = int(category) if category.isdigit() else None
    query.size = size if size in SIZES else None
    query.in_stock_only = in_stock in ("1", "true")

    low = parse_amount(min_price) if min_price.strip() else None
    high = parse_amount(max_price) if max_price.strip() else None
    if (min_price.strip() and low is None) or (max_price.strip() and high is None):
        query.notices.append("Prices must be amounts of 0 or more with at most two decimal places. The price range was not applied.")
    elif low is not None and high is not None and low > high:
        query.notices.append("The minimum price is higher than the maximum price. The price range was not applied.")
    else:
        query.min_price_cents, query.max_price_cents = low, high
    return query


# --- Categories -----------------------------------------------------------


class CategoryIn(BaseModel):
    name: str = ""


def _clean_name(conn: sqlite3.Connection, name: str, category_id: int | None = None) -> str:
    clean = name.strip()
    if not clean:
        raise ValidationProblem(["Category name is required."])
    if len(clean) > MAX_CATEGORY_NAME:
        raise ValidationProblem([f"Category name must be at most {MAX_CATEGORY_NAME} characters."])
    clash = conn.execute(
        "SELECT name FROM categories WHERE casefold(name) = ? AND id IS NOT ?", (clean.casefold(), category_id)
    ).fetchone()
    if clash:
        raise ValidationProblem([f"A category named \"{clash['name']}\" already exists."], status.HTTP_409_CONFLICT)
    return clean


def _categories(conn: sqlite3.Connection, non_empty_only: bool) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.name, (SELECT COUNT(*) FROM products p WHERE p.category_id = c.id) AS product_count
           FROM categories c ORDER BY casefold(c.name)"""
    ).fetchall()
    return [dict(row) for row in rows if row["product_count"] or not non_empty_only]


@router.get("/categories")
def list_categories(user=Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    # Customers only see categories they can actually browse (FR60).
    categories = _categories(conn, non_empty_only=user["role"] != "admin")
    return {"categories": categories}


@router.post("/admin/categories", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_category(body: CategoryIn, conn: sqlite3.Connection = Depends(get_db)):
    name = _clean_name(conn, body.name)
    category_id = conn.execute(
        "INSERT INTO categories (name, created_at) VALUES (?, ?)", (name, utcnow().isoformat())
    ).lastrowid
    conn.commit()
    return {"id": category_id, "name": name, "product_count": 0, "message": f"Category \"{name}\" has been added."}


@router.put("/admin/categories/{category_id}", dependencies=[Depends(require_admin)])
def rename_category(category_id: int, body: CategoryIn, conn: sqlite3.Connection = Depends(get_db)):
    if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found. It may have been deleted.")
    name = _clean_name(conn, body.name, category_id)
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
    conn.commit()
    return {"id": category_id, "name": name, "message": f"Category renamed to \"{name}\"."}


@router.delete("/admin/categories/{category_id}", dependencies=[Depends(require_admin)])
def delete_category(category_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found. It may have been deleted.")
    # products.category_id is ON DELETE SET NULL: the products become uncategorised.
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    return {"message": f"Category \"{row['name']}\" has been deleted. Its products are now uncategorised."}
