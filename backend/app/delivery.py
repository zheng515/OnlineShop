"""Delivery: address book, delivery methods and fees, delivery at checkout (FR100-FR108)."""

import re
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from .database import Database, Row, write_transaction
from .errors import ValidationProblem
from .products import format_cents, parse_amount
from .security import utcnow

MAX_ADDRESSES = 10
MAX_FEE_CENTS = 100_000
MAX_THRESHOLD_CENTS = 100_000_000
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
PHONE_PATTERN = re.compile(r"^[0-9 +()\-]+$")
POSTAL_CODE_PATTERN = re.compile(r"^[A-Za-z0-9 \-]+$")


# --- Addresses (FR100-FR102) ------------------------------------------------


@dataclass(frozen=True)
class TextField:
    key: str
    label: str
    max_length: int
    required: bool = True


ADDRESS_FIELDS = (
    TextField("full_name", "Full name", 100),
    TextField("phone", "Phone number", 20),
    TextField("line1", "Address line 1", 100),
    TextField("line2", "Address line 2", 100, required=False),
    TextField("city", "City", 60),
    TextField("region", "State, province or region", 60, required=False),
    TextField("postal_code", "Postal code", 12),
)


def _clean_text(data: dict[str, Any], fields, problems: list[str]) -> dict[str, str]:
    cleaned = {}
    for spec in fields:
        value = data.get(spec.key)
        value = value.strip() if isinstance(value, str) else ""
        if not value:
            if spec.required:
                problems.append(f"{spec.label} is required.")
        elif CONTROL_CHARACTERS.search(value):
            problems.append(f"{spec.label} must be on one line without special characters.")
        elif len(value) > spec.max_length:
            problems.append(f"{spec.label} must be at most {spec.max_length} characters.")
        cleaned[spec.key] = value
    return cleaned


def clean_address(data: dict[str, Any], countries: tuple[str, ...]) -> dict[str, str]:
    """Check an address (FR101); raises ValidationProblem listing every problem."""
    problems: list[str] = []
    address = _clean_text(data, ADDRESS_FIELDS, problems)
    phone = address["phone"]
    phone_checked = phone and len(phone) <= 20 and not CONTROL_CHARACTERS.search(phone)
    if phone_checked and (not PHONE_PATTERN.match(phone) or sum(ch.isdigit() for ch in phone) < 6):
        problems.append("Phone number must have at least 6 digits and may only contain digits, spaces and + - ( ).")
    postal = address["postal_code"]
    if postal and len(postal) <= 12 and not POSTAL_CODE_PATTERN.match(postal):
        problems.append("Postal code may only contain letters, digits, spaces and hyphens.")

    country = data.get("country")
    country = country.strip() if isinstance(country, str) else ""
    if not country and len(countries) == 1:
        country = countries[0]  # the only country is chosen automatically (FR102)
    if not country:
        problems.append("Country is required.")
    elif country not in countries:
        problems.append(f"We do not deliver to {country}. Please choose one of: {', '.join(countries)}.")
    address["country"] = country
    if problems:
        raise ValidationProblem(problems)
    return address


def address_lines(address: dict | Row) -> list[str]:
    """The address as it is printed on a parcel."""
    place = " ".join(part for part in (address["region"], address["postal_code"]) if part)
    lines = [address["full_name"], address["line1"], address["line2"], f"{address['city']}, {place}", address["country"]]
    return [line for line in lines if line]


def serialize_address(row: Row, countries: tuple[str, ...]) -> dict:
    fields = ("id", "full_name", "phone", "line1", "line2", "city", "region", "postal_code", "country")
    address = {key: row[key] for key in fields}
    address["is_default"] = bool(row["is_default"])
    address["deliverable"] = row["country"] in countries
    address["lines"] = address_lines(row)
    return address


def list_addresses(conn: Database, user_id: int, countries: tuple[str, ...]) -> list[dict]:
    rows = conn.execute("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, id", (user_id,))
    return [serialize_address(row, countries) for row in rows.fetchall()]


def address_book(conn: Database, user_id: int, countries: tuple[str, ...]) -> dict:
    return {"addresses": list_addresses(conn, user_id, countries), "countries": list(countries), "max": MAX_ADDRESSES}


def _owned_address(conn: Database, user_id: int, address_id: int) -> Row:
    row = conn.execute("SELECT * FROM addresses WHERE id = ? AND user_id = ?", (address_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This address is no longer in your address book.")
    return row


def _make_default(conn: Database, user_id: int, address_id: int) -> None:
    conn.execute("UPDATE addresses SET is_default = (id = ?) WHERE user_id = ?", (address_id, user_id))


def create_address(
    conn: Database, user_id: int, data: dict, countries: tuple[str, ...], make_default: bool = False
) -> int:
    address = clean_address(data, countries)
    with write_transaction(conn):
        count = conn.execute("SELECT COUNT(*) FROM addresses WHERE user_id = ?", (user_id,)).fetchone()[0]
        if count >= MAX_ADDRESSES:
            raise ValidationProblem(
                [f"You can keep at most {MAX_ADDRESSES} addresses. Please delete one before adding another."],
                status.HTTP_409_CONFLICT,
            )
        now = utcnow().isoformat()
        address_id = conn.insert(
            """INSERT INTO addresses (user_id, full_name, phone, line1, line2, city, region, postal_code, country,
                                      is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, *(address[f.key] for f in ADDRESS_FIELDS), address["country"], False, now, now),
        )
        if make_default or count == 0:  # the first address becomes the default (FR100)
            _make_default(conn, user_id, address_id)
    return address_id


def update_address(
    conn: Database, user_id: int, address_id: int, data: dict, countries: tuple[str, ...], make_default: bool = False
) -> None:
    address = clean_address(data, countries)
    with write_transaction(conn):
        _owned_address(conn, user_id, address_id)
        conn.execute(
            """UPDATE addresses SET full_name = ?, phone = ?, line1 = ?, line2 = ?, city = ?, region = ?,
                                    postal_code = ?, country = ?, updated_at = ?
               WHERE id = ?""",
            (*(address[f.key] for f in ADDRESS_FIELDS), address["country"], utcnow().isoformat(), address_id),
        )
        if make_default:
            _make_default(conn, user_id, address_id)


def delete_address(conn: Database, user_id: int, address_id: int) -> None:
    with write_transaction(conn):
        row = _owned_address(conn, user_id, address_id)
        conn.execute("DELETE FROM addresses WHERE id = ?", (address_id,))
        if row["is_default"]:
            oldest = conn.execute("SELECT MIN(id) FROM addresses WHERE user_id = ?", (user_id,)).fetchone()[0]
            if oldest is not None:
                _make_default(conn, user_id, oldest)


def set_default_address(conn: Database, user_id: int, address_id: int) -> None:
    with write_transaction(conn):
        _owned_address(conn, user_id, address_id)
        _make_default(conn, user_id, address_id)


# --- Delivery methods (FR103, FR104) -----------------------------------------

METHOD_FIELDS = (TextField("name", "Name", 50), TextField("description", "Description", 100, required=False))


def clean_method(data: dict[str, Any]) -> dict:
    problems: list[str] = []
    method = _clean_text(data, METHOD_FIELDS, problems)

    fee_text = str(data.get("fee") if data.get("fee") is not None else "").strip()
    fee_cents = parse_amount(fee_text) if fee_text else None
    if not fee_text:
        problems.append("Fee is required (enter 0 for free delivery).")
    elif fee_cents is None or fee_cents > MAX_FEE_CENTS:
        problems.append("Fee must be an amount from 0.00 to 1000.00 with at most two decimal places.")

    threshold_text = str(data.get("free_over") if data.get("free_over") is not None else "").strip()
    free_over_cents = None
    if threshold_text:
        free_over_cents = parse_amount(threshold_text)
        if free_over_cents is None or not 0 < free_over_cents <= MAX_THRESHOLD_CENTS:
            problems.append(
                "Free delivery threshold must be an amount from 0.01 to 1000000.00 with at most two decimal places,"
                " or empty."
            )
    if problems:
        raise ValidationProblem(problems)
    return {**method, "fee_cents": fee_cents, "free_over_cents": free_over_cents, "active": bool(data.get("active", True))}


def method_fee(method: Row | dict, items_cents: int) -> int:
    threshold = method["free_over_cents"]
    return 0 if threshold is not None and items_cents >= threshold else method["fee_cents"]


def serialize_method(row: Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "fee": format_cents(row["fee_cents"]),
        "free_over": format_cents(row["free_over_cents"]),
        "active": bool(row["active"]),
        "updated_at": row["updated_at"],
    }


def list_methods(conn: Database) -> list[dict]:
    rows = conn.execute("SELECT * FROM shipping_methods ORDER BY fee_cents, casefold(name), id").fetchall()
    return [serialize_method(row) for row in rows]


def _save_method(conn: Database, method: dict, method_id: int | None) -> int:
    now = utcnow().isoformat()
    try:
        with write_transaction(conn):
            if method_id is None:
                return conn.insert(
                    """INSERT INTO shipping_methods
                       (name, description, fee_cents, free_over_cents, active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (method["name"], method["description"], method["fee_cents"], method["free_over_cents"],
                     method["active"], now, now),
                )
            updated = conn.execute(
                """UPDATE shipping_methods SET name = ?, description = ?, fee_cents = ?, free_over_cents = ?, active = ?,
                                               updated_at = ? WHERE id = ?""",
                (method["name"], method["description"], method["fee_cents"], method["free_over_cents"],
                 method["active"], now, method_id),
            ).rowcount
            if updated != 1:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "This delivery method no longer exists.")
            return method_id
    except conn.IntegrityError:
        raise ValidationProblem([f"A delivery method named \"{method['name']}\" already exists."]) from None


def create_method(conn: Database, data: dict) -> int:
    return _save_method(conn, clean_method(data), None)


def update_method(conn: Database, method_id: int, data: dict) -> int:
    return _save_method(conn, clean_method(data), method_id)


def delete_method(conn: Database, method_id: int) -> str:
    with write_transaction(conn):
        row = conn.execute("SELECT name FROM shipping_methods WHERE id = ?", (method_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "This delivery method no longer exists.")
        conn.execute("DELETE FROM shipping_methods WHERE id = ?", (method_id,))
    return row["name"]


# --- Delivery at checkout (FR105, FR106) ---------------------------------------

ADDRESS_GONE = "The delivery address you chose is no longer in your address book. Please choose another one."
METHOD_GONE = "The delivery method you chose is no longer available. Please choose another one."
NO_METHODS = "Delivery is not available at the moment, so orders cannot be placed. Please try again later."


def _customer_method(row: Row, items_cents: int) -> dict:
    fee = method_fee(row, items_cents)
    threshold = row["free_over_cents"]
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "fee": format_cents(fee),
        "fee_cents": fee,
        "free_over": format_cents(threshold),
        # How much more to buy for free delivery with this method, if a threshold applies.
        "amount_to_free": format_cents(threshold - items_cents) if fee and threshold is not None else None,
    }


def apply_delivery(
    conn: Database,
    summary: dict,
    user_id: int,
    countries: tuple[str, ...],
    address_id: int | None,
    method_id: int | None,
) -> dict:
    """Add the delivery address, methods and fee to a checkout summary (FR105, FR106).

    Without an address id the default address is used; without a method id the cheapest
    active method. `ready` says whether the order can be placed as it is."""
    items_cents = summary["total_cents"]
    issues: list[str] = []

    if address_id is None:
        row = conn.execute(
            "SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, id LIMIT 1", (user_id,)
        ).fetchone()
        if row is None:
            issues.append("Please add a delivery address.")
    else:
        row = conn.execute("SELECT * FROM addresses WHERE id = ? AND user_id = ?", (address_id, user_id)).fetchone()
        if row is None:
            issues.append(ADDRESS_GONE)
    address = serialize_address(row, countries) if row else None
    if address and not address["deliverable"]:
        issues.append(f"We no longer deliver to {address['country']}. Please choose another address.")

    active = conn.execute("SELECT * FROM shipping_methods WHERE active = ?", (True,)).fetchall()
    methods = sorted(
        (_customer_method(m, items_cents) for m in active), key=lambda m: (m["fee_cents"], m["name"].casefold(), m["id"])
    )
    method = None
    if not methods:
        issues.append(NO_METHODS)
    elif method_id is None:
        method = methods[0]
    else:
        method = next((m for m in methods if m["id"] == method_id), None)
        if method is None:
            issues.append(METHOD_GONE)

    shipping_cents = method["fee_cents"] if method else 0
    summary.update(
        items_total=summary["total"],
        items_total_cents=items_cents,
        shipping_fee=format_cents(shipping_cents) if method else None,
        shipping_cents=shipping_cents,
        total=format_cents(items_cents + shipping_cents),
        total_cents=items_cents + shipping_cents,
        delivery={"address": address, "method": method, "methods": methods},
        delivery_issues=issues,
        ready=summary["valid"] and not issues,
    )
    return summary


def order_delivery_values(summary: dict) -> dict:
    """The delivery details an order records as they were when it was placed (FR107)."""
    address, method = summary["delivery"]["address"], summary["delivery"]["method"]
    return {
        "items_cents": summary["items_total_cents"],
        "shipping_cents": summary["shipping_cents"],
        "delivery_method": method["name"],
        **{f"delivery_{key}": address[key] for key in (
            "full_name", "phone", "line1", "line2", "city", "region", "postal_code", "country")},
    }
