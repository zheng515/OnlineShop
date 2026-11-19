"""Administrator order management (FR47-FR49)."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..database import get_db
from ..order_service import STATUS_LABELS, change_status, get_order, list_orders
from ..security import require_admin

router = APIRouter(prefix="/api/admin/orders", tags=["admin"], dependencies=[Depends(require_admin)])

OrderStatus = Literal["placed", "shipped", "completed", "cancelled"]


class StatusChangeRequest(BaseModel):
    status: Literal["shipped", "completed", "cancelled"]


@router.get("")
def all_orders(status: OrderStatus | None = None, q: str = "", conn: sqlite3.Connection = Depends(get_db)):
    orders = list_orders(conn, "admin", status_filter=status, keyword=q)
    return {"orders": orders, "count": len(orders), "query": q, "status": status}


@router.get("/{order_id}")
def order_detail(order_id: int, conn: sqlite3.Connection = Depends(get_db)):
    return get_order(conn, order_id, "admin")


@router.post("/{order_id}/status")
def update_status(
    order_id: int, body: StatusChangeRequest, user=Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)
):
    change_status(conn, order_id, body.status, user)
    order = get_order(conn, order_id, "admin")
    order["message"] = f"Order {order['number']} is now {STATUS_LABELS[body.status]}."
    return order
