"""The customer's address book (FR100-FR102)."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import delivery
from ..database import Database, get_db
from ..security import require_customer

router = APIRouter(prefix="/api/account/addresses", tags=["account"], dependencies=[Depends(require_customer)])


class AddressIn(BaseModel):
    # Generous limits only bound the request; the real rules are checked by delivery.clean_address.
    full_name: str = Field("", max_length=500)
    phone: str = Field("", max_length=500)
    line1: str = Field("", max_length=500)
    line2: str = Field("", max_length=500)
    city: str = Field("", max_length=500)
    region: str = Field("", max_length=500)
    postal_code: str = Field("", max_length=500)
    country: str = Field("", max_length=500)
    make_default: bool = False

    def fields(self) -> dict:
        return self.model_dump(exclude={"make_default"})


def _countries(request: Request) -> tuple[str, ...]:
    return request.app.state.settings.delivery_countries


def _book(conn: Database, user, request: Request, message: str = "", **extra) -> dict:
    book = delivery.address_book(conn, user["id"], _countries(request))
    return {**book, **extra, **({"message": message} if message else {})}


@router.get("")
def my_addresses(request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    return _book(conn, user, request)


@router.post("", status_code=201)
def add_address(body: AddressIn, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    address_id = delivery.create_address(conn, user["id"], body.fields(), _countries(request), body.make_default)
    return _book(conn, user, request, "The address has been saved.", address_id=address_id)


@router.put("/{address_id}")
def edit_address(
    address_id: int, body: AddressIn, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)
):
    delivery.update_address(conn, user["id"], address_id, body.fields(), _countries(request), body.make_default)
    return _book(conn, user, request, "The address has been updated.", address_id=address_id)


@router.delete("/{address_id}")
def remove_address(address_id: int, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    delivery.delete_address(conn, user["id"], address_id)
    return _book(conn, user, request, "The address has been deleted.")


@router.post("/{address_id}/default")
def make_default(address_id: int, request: Request, user=Depends(require_customer), conn: Database = Depends(get_db)):
    delivery.set_default_address(conn, user["id"], address_id)
    return _book(conn, user, request, "Your default address has been changed.")
