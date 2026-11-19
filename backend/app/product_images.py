"""Product image records: staged uploads, attaching to products and cleanup (FR14, FR62)."""

import sqlite3
from datetime import timedelta
from pathlib import Path

from .images import delete_image
from .order_service import image_referenced_by_orders
from .security import utcnow

UNATTACHED_LIFETIME = timedelta(hours=24)


def record_upload(conn: sqlite3.Connection, file_name: str) -> int:
    image_id = conn.execute(
        "INSERT INTO product_images (product_id, file, position, uploaded_at) VALUES (NULL, ?, 0, ?)",
        (file_name, utcnow().isoformat()),
    ).lastrowid
    conn.commit()
    return image_id


def attach_images(conn: sqlite3.Connection, product_id: int, image_ids: list[int]) -> list[str]:
    """Make image_ids the product's images, in order. Returns files no longer used by the product.

    Runs inside the caller's transaction; delete the returned files only after it commits.
    """
    removed = [
        row["file"]
        for row in conn.execute(
            f"SELECT file FROM product_images WHERE product_id = ? AND id NOT IN ({','.join('?' * len(image_ids))})",
            [product_id, *image_ids],
        )
    ]
    conn.execute(
        f"DELETE FROM product_images WHERE product_id = ? AND id NOT IN ({','.join('?' * len(image_ids))})",
        [product_id, *image_ids],
    )
    conn.executemany(
        "UPDATE product_images SET product_id = ?, position = ? WHERE id = ?",
        [(product_id, position, image_id) for position, image_id in enumerate(image_ids)],
    )
    main = conn.execute("SELECT file FROM product_images WHERE id = ?", (image_ids[0],)).fetchone()["file"]
    conn.execute("UPDATE products SET image = ? WHERE id = ?", (main, product_id))
    return removed


def discard_files(conn: sqlite3.Connection, upload_dir: Path, files: list[str]) -> None:
    """Delete image files nothing refers to any more; order history keeps its images (FR45)."""
    for file_name in files:
        still_used = conn.execute("SELECT 1 FROM product_images WHERE file = ? LIMIT 1", (file_name,)).fetchone()
        if not still_used and not image_referenced_by_orders(conn, file_name):
            delete_image(upload_dir, file_name)


def cleanup_unattached(conn: sqlite3.Connection, upload_dir: Path) -> None:
    """Remove uploads that were never attached to a product within the allowed time (FR14)."""
    cutoff = (utcnow() - UNATTACHED_LIFETIME).isoformat()
    files = [
        row["file"]
        for row in conn.execute(
            "SELECT file FROM product_images WHERE product_id IS NULL AND uploaded_at < ?", (cutoff,)
        )
    ]
    if not files:
        return
    conn.execute("DELETE FROM product_images WHERE product_id IS NULL AND uploaded_at < ?", (cutoff,))
    conn.commit()
    discard_files(conn, upload_dir, files)
