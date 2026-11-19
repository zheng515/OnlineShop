"""Customer orders: placement, payment, history and cancellation (FR41-FR48, FR50, FR78-FR80)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field

from ..database import Database, get_db
from ..order_service import change_status, get_order, list_orders, place_order
from ..orders import Line
from ..payments.service import expire_if_overdue, process_refunds, start_or_resume_payment
from ..security import require_customer, utcnow
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
    request: Request,
    response: Response,
    user=Depends(require_customer),
    conn: Database = Depends(get_db),
):
    settings = request.app.state.settings
    buy_now = Line(body.product_id, body.size, body.quantity) if body.source == "buy_now" else None
    deadline = utcnow() + timedelta(minutes=settings.payment_timeout_minutes)
    order_id, created = place_order(
        conn, user, body.source, buy_now, round(body.expected_total * 100), body.request_id, deadline
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    order = get_order(conn, order_id, "customer", user["id"])
    if order["status"] == "awaiting_payment":
        # Straight on to the payment provider (FR41, FR78).
        order["payment_url"] = start_or_resume_payment(conn, settings, order_id, user["id"])
    order["message"] = f"Order {order['number']} has been placed."
    return order


@router.get("")
def my_orders(user=Depends(require_customer), conn: Database = Depends(get_db)):
    orders = list_orders(conn, "customer", user_id=user["id"])
    return {"orders": orders, "count": len(orders)}


@router.get("/{order_id}")
def my_order(order_id: int, user=Depends(require_customer), conn: Database = Depends(get_db)):
    get_order(conn, order_id, "customer", user["id"])  # 404 for other customers' orders (FR50)
    expire_if_overdue(conn, order_id)
    return get_order(conn, order_id, "customer", user["id"])


@router.post("/{order_id}/pay")
def pay(order_id: int, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    """Start or resume paying for an order awaiting payment (FR80)."""
    return {"payment_url": start_or_resume_payment(conn, request.app.state.settings, order_id, user["id"])}


@router.post("/{order_id}/cancel")
def cancel(order_id: int, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    refund_ids = change_status(conn, order_id, "cancelled", user, owner_id=user["id"])
    process_refunds(conn, request.app.state.settings, refund_ids)
    order = get_order(conn, order_id, "customer", user["id"])
    order["message"] = f"Order {order['number']} has been cancelled."
    if refund_ids:
        order["message"] += " The amount paid is being refunded."
    return order
