"""Administrator product management (FR7-FR14)."""

import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from ..database import get_db
from ..errors import ValidationProblem
from ..images import ImageUploadError, delete_image, has_file, save_image
from ..products import admin_view, get_product, list_products, validate_product_fields
from ..security import require_admin, utcnow

router = APIRouter(prefix="/api/admin/products", tags=["admin"], dependencies=[Depends(require_admin)])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Product not found. It may have been deleted.")


async def _store_image(request: Request, image: UploadFile) -> str:
    settings = request.app.state.settings
    try:
        return await save_image(image, settings.upload_dir, settings.max_image_bytes)
    except ImageUploadError as exc:
        raise ValidationProblem([str(exc)]) from exc


def _write_sizes(conn: sqlite3.Connection, product_id: int, sizes: dict[str, int]) -> None:
    conn.execute("DELETE FROM product_sizes WHERE product_id = ?", (product_id,))
    conn.executemany(
        "INSERT INTO product_sizes (product_id, size, stock) VALUES (?, ?, ?)",
        [(product_id, size, qty) for size, qty in sizes.items()],
    )


@router.get("")
def list_all(q: str = "", conn: sqlite3.Connection = Depends(get_db)):
    products = [admin_view(p) for p in list_products(conn, q)]
    return {"products": products, "count": len(products), "query": q}


@router.get("/{product_id}")
def detail(product_id: int, conn: sqlite3.Connection = Depends(get_db)):
    product = get_product(conn, product_id)
    if product is None:
        raise _not_found()
    return admin_view(product)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    request: Request,
    name: str = Form(""),
    price: str = Form(""),
    stock: str = Form(""),
    image: UploadFile | None = File(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    errors: list[str] = []
    try:
        clean_name, price_cents, sizes = validate_product_fields(name, price, stock)
    except ValidationProblem as problem:
        errors.extend(problem.errors)
    if not has_file(image):
        errors.append("Product image is required.")
    if errors:
        raise ValidationProblem(errors)

    file_name = await _store_image(request, image)
    now = utcnow().isoformat()
    try:
        cursor = conn.execute(
            "INSERT INTO products (name, price_cents, image, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (clean_name, price_cents, file_name, now, now),
        )
        _write_sizes(conn, cursor.lastrowid, sizes)
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        delete_image(request.app.state.settings.upload_dir, file_name)
        raise
    return admin_view(get_product(conn, cursor.lastrowid))


@router.put("/{product_id}")
async def update(
    product_id: int,
    request: Request,
    name: str = Form(""),
    price: str = Form(""),
    stock: str = Form(""),
    image: UploadFile | None = File(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = get_product(conn, product_id)
    if existing is None:
        raise _not_found()
    clean_name, price_cents, sizes = validate_product_fields(name, price, stock)

    upload_dir = request.app.state.settings.upload_dir
    new_file = await _store_image(request, image) if has_file(image) else None
    try:
        conn.execute(
            "UPDATE products SET name = ?, price_cents = ?, image = ?, updated_at = ? WHERE id = ?",
            (clean_name, price_cents, new_file or existing["image"], utcnow().isoformat(), product_id),
        )
        _write_sizes(conn, product_id, sizes)
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        if new_file:
            delete_image(upload_dir, new_file)
        raise
    if new_file:
        delete_image(upload_dir, existing["image"])
    return admin_view(get_product(conn, product_id))


@router.delete("/{product_id}")
def delete(product_id: int, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    existing = get_product(conn, product_id)
    if existing is None:
        raise _not_found()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    delete_image(request.app.state.settings.upload_dir, existing["image"])
    return {"message": f"\"{existing['name']}\" has been deleted."}
