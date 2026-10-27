"""Customer browsing, cart and checkout (FR15-FR34)."""

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from ..config import SIZES
from ..database import get_db
from ..errors import ValidationProblem
from ..orders import Line, cart_lines, evaluate_lines
from ..products import customer_detail, customer_summary, get_product, list_products
from ..security import require_customer, utcnow

router = APIRouter(prefix="/api", tags=["shop"], dependencies=[Depends(require_customer)])

Quantity = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
Size = Literal[SIZES]


class CartAddRequest(BaseModel):
    product_id: int
    size: Size
    quantity: Quantity


class CartUpdateRequest(BaseModel):
    quantity: Quantity


class CheckoutRequest(BaseModel):
    source: Literal["cart", "buy_now"]
    product_id: int | None = None
    size: Size | None = None
    quantity: Quantity | None = None

    @model_validator(mode="after")
    def _buy_now_fields(self):
        if self.source == "buy_now" and None in (self.product_id, self.size, self.quantity):
            raise ValueError("Buy Now requires a product, size and quantity.")
        return self


def _purchasable_stock(conn: sqlite3.Connection, product_id: int, size: str) -> tuple[dict, int]:
    product = get_product(conn, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This product is no longer available.")
    if size not in product["stock"]:
        raise ValidationProblem([f"Size {size} is not available for \"{product['name']}\"."], status.HTTP_409_CONFLICT)
    stock = product["stock"][size]
    if stock == 0:
        raise ValidationProblem([f"Size {size} of \"{product['name']}\" is out of stock."], status.HTTP_409_CONFLICT)
    return product, stock


def _cart(conn: sqlite3.Connection, user_id: int) -> dict:
    return evaluate_lines(conn, cart_lines(conn, user_id))


# --- Browsing -------------------------------------------------------------


@router.get("/products")
def browse(q: str = "", conn: sqlite3.Connection = Depends(get_db)):
    products = [customer_summary(p) for p in list_products(conn, q)]
    return {"products": products, "count": len(products), "query": q}


@router.get("/products/{product_id}")
def product_detail(product_id: int, conn: sqlite3.Connection = Depends(get_db)):
    product = get_product(conn, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This product is no longer available.")
    return customer_detail(product)


# --- Cart -----------------------------------------------------------------


@router.get("/cart")
def view_cart(user=Depends(require_customer), conn: sqlite3.Connection = Depends(get_db)):
    return _cart(conn, user["id"])


@router.post("/cart/items", status_code=status.HTTP_201_CREATED)
def add_to_cart(body: CartAddRequest, user=Depends(require_customer), conn: sqlite3.Connection = Depends(get_db)):
    product, stock = _purchasable_stock(conn, body.product_id, body.size)
    existing = conn.execute(
        "SELECT id, quantity FROM cart_items WHERE user_id = ? AND product_id = ? AND size = ?",
        (user["id"], body.product_id, body.size),
    ).fetchone()
    in_cart = existing["quantity"] if existing else 0
    new_quantity = in_cart + body.quantity
    if new_quantity > stock:
        message = f"Only {stock} available in size {body.size}."
        if in_cart:
            message += f" You already have {in_cart} in your cart."
        raise ValidationProblem([message], status.HTTP_409_CONFLICT)

    if existing:
        # Same product and size: merge into the existing entry (FR20).
        conn.execute(
            "UPDATE cart_items SET quantity = ?, product_name = ? WHERE id = ?",
            (new_quantity, product["name"], existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO cart_items (user_id, product_id, product_name, size, quantity, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], body.product_id, product["name"], body.size, body.quantity, utcnow().isoformat()),
        )
    conn.commit()
    cart = _cart(conn, user["id"])
    cart["message"] = f"Added {body.quantity} × \"{product['name']}\" (size {body.size}) to your cart."
    return cart


def _owned_item(conn: sqlite3.Connection, user_id: int, item_id: int) -> sqlite3.Row:
    item = conn.execute("SELECT * FROM cart_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This item is no longer in your cart.")
    return item


@router.patch("/cart/items/{item_id}")
def update_cart_item(
    item_id: int, body: CartUpdateRequest, user=Depends(require_customer), conn: sqlite3.Connection = Depends(get_db)
):
    item = _owned_item(conn, user["id"], item_id)
    product, stock = _purchasable_stock(conn, item["product_id"], item["size"])
    if body.quantity > stock:
        raise ValidationProblem(
            [f"Only {stock} available in size {item['size']} of \"{product['name']}\"."], status.HTTP_409_CONFLICT
        )
    conn.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (body.quantity, item_id))
    conn.commit()
    return _cart(conn, user["id"])


@router.delete("/cart/items/{item_id}")
def remove_cart_item(item_id: int, user=Depends(require_customer), conn: sqlite3.Connection = Depends(get_db)):
    _owned_item(conn, user["id"], item_id)
    conn.execute("DELETE FROM cart_items WHERE id = ?", (item_id,))
    conn.commit()
    return _cart(conn, user["id"])


# --- Checkout -------------------------------------------------------------


@router.post("/checkout")
def checkout_summary(body: CheckoutRequest, user=Depends(require_customer), conn: sqlite3.Connection = Depends(get_db)):
    """Build the checkout summary, revalidating stock and prices against current data.

    Used both to display the Checkout page and to revalidate before the
    customer continues to payment. No order is placed and stock is not
    reduced: payment and fulfilment are out of scope (FR32).
    """
    if body.source == "cart":
        summary = _cart(conn, user["id"])
    else:
        summary = evaluate_lines(conn, [Line(body.product_id, body.size, body.quantity)])
    summary["source"] = body.source
    return summary
