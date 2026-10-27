"""Pricing and stock checks shared by the cart and checkout (FR25, FR28-FR30, FR33, FR34).

Prices are always taken from the current product record, never from the
moment an item was added to the cart.
"""

import sqlite3
from dataclasses import dataclass

from .products import format_cents, get_product


@dataclass
class Line:
    product_id: int
    size: str
    quantity: int
    product_name: str = ""
    cart_item_id: int | None = None


def evaluate_lines(conn: sqlite3.Connection, lines: list[Line]) -> dict:
    items = []
    total_cents = 0
    for line in lines:
        product = get_product(conn, line.product_id)
        name = product["name"] if product else (line.product_name or f"Product #{line.product_id}")
        item = {
            "id": line.cart_item_id,
            "product_id": line.product_id,
            "name": name,
            "image_url": product["image_url"] if product else None,
            "size": line.size,
            "quantity": line.quantity,
            "unit_price": None,
            "subtotal": None,
            "available_stock": 0,
            "status": "ok",
            "message": None,
        }
        if product is None:
            item["status"] = "unavailable"
            item["message"] = f"\"{name}\" is no longer available and cannot be checked out."
        elif line.size not in product["stock"]:
            item["status"] = "unavailable"
            item["message"] = f"Size {line.size} of \"{name}\" is no longer available."
        else:
            stock = product["stock"][line.size]
            subtotal_cents = product["price_cents"] * line.quantity
            total_cents += subtotal_cents
            item.update(
                unit_price=product["price"],
                subtotal=format_cents(subtotal_cents),
                available_stock=stock,
            )
            if stock == 0:
                item["status"] = "out_of_stock"
                item["message"] = f"Size {line.size} of \"{name}\" is out of stock."
            elif line.quantity > stock:
                item["status"] = "insufficient_stock"
                item["message"] = (
                    f"Only {stock} left in size {line.size} of \"{name}\" "
                    f"(you selected {line.quantity})."
                )
        items.append(item)

    issues = [item["message"] for item in items if item["message"]]
    if not items:
        issues.append("Your cart is empty. Add some products before checking out.")
    return {
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "total": format_cents(total_cents),
        "empty": not items,
        "valid": bool(items) and not issues,
        "issues": issues,
    }


def cart_lines(conn: sqlite3.Connection, user_id: int) -> list[Line]:
    rows = conn.execute(
        "SELECT id, product_id, product_name, size, quantity FROM cart_items WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    return [
        Line(
            product_id=row["product_id"],
            size=row["size"],
            quantity=row["quantity"],
            product_name=row["product_name"],
            cart_item_id=row["id"],
        )
        for row in rows
    ]
