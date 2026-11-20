"""Administrator order management (FR47-FR49, FR82)."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..database import Database, get_db
from ..delivery import CONTROL_CHARACTERS
from ..errors import ValidationProblem
from ..order_service import STATUS_LABELS, ShippingDetails, change_status, get_order, list_orders
from ..payments.service import expire_if_overdue, process_refunds, retry_failed_refunds
from ..security import require_admin

router = APIRouter(prefix="/api/admin/orders", tags=["admin"], dependencies=[Depends(require_admin)])

OrderStatus = Literal["awaiting_payment", "paid", "shipped", "completed", "cancelled"]


class StatusChangeRequest(BaseModel):
    status: Literal["shipped", "completed", "cancelled"]
    # Only used when marking an order as shipped (FR108).
    carrier: str = Field("", max_length=50)
    tracking_number: str = Field("", max_length=50)

    def shipping(self) -> ShippingDetails | None:
        if self.status != "shipped":
            return None
        details = ShippingDetails(self.carrier.strip(), self.tracking_number.strip())
        if CONTROL_CHARACTERS.search(details.carrier + details.tracking_number):
            raise ValidationProblem(["Carrier and tracking number must be on one line without special characters."])
        return details


@router.get("")
def all_orders(status: OrderStatus | None = None, q: str = "", conn: Database = Depends(get_db)):
    orders = list_orders(conn, "admin", status_filter=status, keyword=q)
    return {"orders": orders, "count": len(orders), "query": q, "status": status}


@router.get("/{order_id}")
def order_detail(order_id: int, conn: Database = Depends(get_db)):
    get_order(conn, order_id, "admin")
    expire_if_overdue(conn, order_id)
    return get_order(conn, order_id, "admin")


@router.post("/{order_id}/status")
def update_status(
    order_id: int, body: StatusChangeRequest, request: Request, user=Depends(require_admin), conn: Database = Depends(get_db)
):
    refund_ids = change_status(conn, order_id, body.status, user, shipping=body.shipping())
    process_refunds(conn, request.app.state.settings, refund_ids)
    order = get_order(conn, order_id, "admin")
    order["message"] = f"Order {order['number']} is now {STATUS_LABELS[body.status]}."
    if refund_ids:
        order["message"] += " The payment is being refunded."
    return order


@router.post("/{order_id}/refunds/retry")
def retry_refund(order_id: int, request: Request, conn: Database = Depends(get_db)):
    get_order(conn, order_id, "admin")
    retry_failed_refunds(conn, request.app.state.settings, order_id)
    order = get_order(conn, order_id, "admin")
    failed = [r for r in order["refunds"] if r["status"] == "failed"]
    order["message"] = "The refund failed again." if failed else "The refund has been completed."
    return order
