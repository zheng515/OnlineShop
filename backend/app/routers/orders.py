"""Customer orders: placement, history and cancellation (FR41-FR48, FR50)."""


from fastapi import APIRouter, Depends, Response, status
from pydantic import Field

from ..database import Database, get_db
from ..order_service import change_status, get_order, list_orders, place_order
from ..orders import Line
from ..security import require_customer
from .shop import CheckoutRequest

router = APIRouter(prefix="/api/orders", tags=["orders"], dependencies=[Depends(require_customer)])


class PlaceOrderRequest(CheckoutRequest):
    # The total the customer saw when choosing Place Order (FR42).
    expected_total: float = Field(gt=0)
    # Generated once per Payment page visit so a repeated submission is recognised (FR43).
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


@router.post("", status_code=status.HTTP_201_CREATED)
def place(
    body: PlaceOrderRequest,
    response: Response,
    user=Depends(require_customer),
    conn: Database = Depends(get_db),
):
    buy_now = Line(body.product_id, body.size, body.quantity) if body.source == "buy_now" else None
    order_id, created = place_order(
        conn, user, body.source, buy_now, round(body.expected_total * 100), body.request_id
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    order = get_order(conn, order_id, "customer", user["id"])
    order["message"] = f"Order {order['number']} has been placed."
    return order


@router.get("")
def my_orders(user=Depends(require_customer), conn: Database = Depends(get_db)):
    orders = list_orders(conn, "customer", user_id=user["id"])
    return {"orders": orders, "count": len(orders)}


@router.get("/{order_id}")
def my_order(order_id: int, user=Depends(require_customer), conn: Database = Depends(get_db)):
    return get_order(conn, order_id, "customer", user["id"])


@router.post("/{order_id}/cancel")
def cancel(order_id: int, user=Depends(require_customer), conn: Database = Depends(get_db)):
    change_status(conn, order_id, "cancelled", user, owner_id=user["id"])
    order = get_order(conn, order_id, "customer", user["id"])
    order["message"] = f"Order {order['number']} has been cancelled."
    return order
