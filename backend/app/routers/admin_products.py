"""Administrator product management (FR7-FR14, FR60-FR65)."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from ..database import get_db, write_transaction
from ..errors import ValidationProblem
from ..images import ImageUploadError, delete_image, has_file, image_url, save_image
from ..product_images import attach_images, cleanup_unattached, discard_files, record_upload
from ..products import ADMIN_PAGE_SIZE, ProductData, admin_view, get_product, search_products, validate_product
from ..security import require_admin, utcnow
from .catalog import catalogue_query

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

ADMIN_SORTS = ("newest", "price_asc", "price_desc", "name", "stock_asc")


class ProductIn(BaseModel):
    # Loosely typed on purpose: validate_product reports every problem in plain words (FR13).
    name: Any = ""
    price: Any = ""
    description: Any = ""
    category_id: Any = None
    stock: Any = Field(default_factory=dict)
    image_ids: Any = Field(default_factory=list)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Product not found. It may have been deleted.")


def _validate(conn: sqlite3.Connection, body: ProductIn, product_id: int | None = None) -> ProductData:
    return validate_product(conn, **body.model_dump(), product_id=product_id)


def _write_sizes(conn: sqlite3.Connection, product_id: int, sizes: dict[str, int]) -> None:
    conn.execute("DELETE FROM product_sizes WHERE product_id = ?", (product_id,))
    conn.executemany(
        "INSERT INTO product_sizes (product_id, size, stock) VALUES (?, ?, ?)",
        [(product_id, size, qty) for size, qty in sizes.items()],
    )


@router.post("/images", status_code=status.HTTP_201_CREATED)
async def upload_image(request: Request, image: UploadFile | None = File(None), conn: sqlite3.Connection = Depends(get_db)):
    """Upload one image; it becomes part of a product when that product is saved (FR14)."""
    settings = request.app.state.settings
    if not has_file(image):
        raise ValidationProblem(["Please choose an image file to upload."])
    try:
        file_name = await save_image(image, settings.upload_dir, settings.max_image_bytes)
    except ImageUploadError as exc:
        raise ValidationProblem([str(exc)]) from exc
    try:
        image_id = record_upload(conn, file_name)
    except sqlite3.Error:
        delete_image(settings.upload_dir, file_name)
        raise
    cleanup_unattached(conn, settings.upload_dir)
    return {"id": image_id, "url": image_url(file_name)}


@router.get("/products")
def list_all(
    q: str = "",
    category: str = "",
    sort: str = "newest",
    page: str = "1",
    conn: sqlite3.Connection = Depends(get_db),
):
    query = catalogue_query(q=q, category=category, sort=sort, page=page, allowed_sorts=ADMIN_SORTS, page_size=ADMIN_PAGE_SIZE)
    result = search_products(conn, query)
    result["products"] = [admin_view(p) for p in result["products"]]
    return {**result, "count": result["total"], "query": q}


@router.get("/products/{product_id}")
def detail(product_id: int, conn: sqlite3.Connection = Depends(get_db)):
    product = get_product(conn, product_id)
    if product is None:
        raise _not_found()
    return admin_view(product)


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create(body: ProductIn, conn: sqlite3.Connection = Depends(get_db)):
    data = _validate(conn, body)
    now = utcnow().isoformat()
    with write_transaction(conn):
        product_id = conn.execute(
            """INSERT INTO products (name, price_cents, image, description, category_id, created_at, updated_at)
               VALUES (?, ?, '', ?, ?, ?, ?)""",
            (data.name, data.price_cents, data.description, data.category_id, now, now),
        ).lastrowid
        _write_sizes(conn, product_id, data.sizes)
        attach_images(conn, product_id, data.image_ids)
    return admin_view(get_product(conn, product_id))


@router.put("/products/{product_id}")
def update(product_id: int, body: ProductIn, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    if get_product(conn, product_id) is None:
        raise _not_found()
    data = _validate(conn, body, product_id)
    with write_transaction(conn):
        conn.execute(
            """UPDATE products SET name = ?, price_cents = ?, description = ?, category_id = ?, updated_at = ?
               WHERE id = ?""",
            (data.name, data.price_cents, data.description, data.category_id, utcnow().isoformat(), product_id),
        )
        _write_sizes(conn, product_id, data.sizes)
        removed = attach_images(conn, product_id, data.image_ids)
    # Only after the save succeeded, so a failed save keeps the previous images (FR14).
    discard_files(conn, request.app.state.settings.upload_dir, removed)
    return admin_view(get_product(conn, product_id))


@router.delete("/products/{product_id}")
def delete(product_id: int, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    existing = get_product(conn, product_id)
    if existing is None:
        raise _not_found()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    discard_files(conn, request.app.state.settings.upload_dir, [image["file"] for image in existing["images"]])
    return {"message": f"\"{existing['name']}\" has been deleted."}
