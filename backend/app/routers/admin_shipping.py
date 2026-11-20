"""Delivery methods and fees, managed by administrators (FR103, FR104)."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import delivery
from ..database import Database, get_db
from ..security import require_admin

router = APIRouter(prefix="/api/admin/shipping-methods", tags=["admin"], dependencies=[Depends(require_admin)])


class MethodIn(BaseModel):
    name: str = Field("", max_length=500)
    description: str = Field("", max_length=500)
    # Amounts arrive as text or numbers and are checked by delivery.clean_method.
    fee: Any = ""
    free_over: Any = ""
    active: bool = True


def _list(conn: Database, message: str = "", **extra) -> dict:
    methods = delivery.list_methods(conn)
    result = {"methods": methods, "active_count": sum(m["active"] for m in methods), **extra}
    if message:
        result["message"] = message
    return result


@router.get("")
def all_methods(conn: Database = Depends(get_db)):
    return _list(conn)


@router.post("", status_code=201)
def add_method(body: MethodIn, conn: Database = Depends(get_db)):
    method_id = delivery.create_method(conn, body.model_dump())
    return _list(conn, f"Delivery method \"{body.name.strip()}\" has been added.", method_id=method_id)


@router.put("/{method_id}")
def edit_method(method_id: int, body: MethodIn, conn: Database = Depends(get_db)):
    delivery.update_method(conn, method_id, body.model_dump())
    return _list(conn, f"Delivery method \"{body.name.strip()}\" has been updated.", method_id=method_id)


@router.delete("/{method_id}")
def remove_method(method_id: int, conn: Database = Depends(get_db)):
    name = delivery.delete_method(conn, method_id)
    return _list(conn, f"Delivery method \"{name}\" has been deleted.")
