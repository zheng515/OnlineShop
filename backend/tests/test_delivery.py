"""Address book, delivery methods and fees, delivery at checkout and in orders (FR100-FR109)."""

import uuid

from alembic import command
from test_accounts import emails

from app.database import connect
from app.migrations import _config

from conftest import TEST_DELIVERY_METHOD, complete_mock_payment, create_product, db, login

HOME = {
    "full_name": "Alice Example",
    "phone": "+1 (555) 010-0200",
    "line1": "12 Market Street",
    "line2": "Apt 4",
    "city": "Springfield",
    "region": "IL",
    "postal_code": "62701",
    "country": "United States",
}


def _sql(client, statement, params=()):
    conn = db(client)
    conn.execute(statement, params)
    conn.commit()
    conn.close()


def real_methods_only(client):
    """Remove the free test method, leaving the two methods the migration creates (FR103)."""
    _sql(client, "DELETE FROM shipping_methods WHERE name = ?", (TEST_DELIVERY_METHOD,))


def addresses(client, headers):
    return client.get("/api/account/addresses", headers=headers).json()["addresses"]


def add_address(client, headers, **changes):
    return client.post("/api/account/addresses", json={**HOME, **changes}, headers=headers)


def methods_by_name(summary):
    return {m["name"]: m for m in summary["delivery"]["methods"]}


def checkout(client, headers, product_id, quantity=1, **choice):
    body = {"source": "buy_now", "product_id": product_id, "size": "S", "quantity": quantity, **choice}
    return client.post("/api/checkout", json=body, headers=headers).json()


def place(client, headers, product_id, expected_total, address_id, method_id, quantity=1):
    body = {
        "source": "buy_now", "product_id": product_id, "size": "S", "quantity": quantity,
        "address_id": address_id, "shipping_method_id": method_id,
        "expected_total": expected_total, "request_id": uuid.uuid4().hex,
    }
    return client.post("/api/orders", json=body, headers=headers)


# --- Address book (FR100-FR102) ----------------------------------------------


def test_address_book_add_edit_default_and_delete(client, customer):
    first = addresses(client, customer)[0]
    assert first["is_default"] is True and first["deliverable"] is True

    response = add_address(client, customer)
    assert response.status_code == 201, response.text
    home = next(a for a in response.json()["addresses"] if a["id"] == response.json()["address_id"])
    assert home["is_default"] is False
    assert home["lines"] == ["Alice Example", "12 Market Street", "Apt 4", "Springfield, IL 62701", "United States"]

    edited = client.put(f"/api/account/addresses/{home['id']}", json={**HOME, "city": " Shelbyville ", "make_default": True},
                        headers=customer)
    assert edited.status_code == 200, edited.text
    book = edited.json()["addresses"]
    assert book[0]["id"] == home["id"] and book[0]["city"] == "Shelbyville" and book[0]["is_default"] is True
    assert [a["is_default"] for a in book].count(True) == 1

    # Deleting the default makes the oldest remaining address the default (FR100).
    deleted = client.delete(f"/api/account/addresses/{home['id']}", headers=customer)
    assert deleted.status_code == 200
    assert [(a["id"], a["is_default"]) for a in deleted.json()["addresses"]] == [(first["id"], True)]

    assert client.post(f"/api/account/addresses/{first['id']}/default", headers=customer).status_code == 200


def test_first_address_becomes_default(client, customer):
    _sql(client, "DELETE FROM addresses")
    response = add_address(client, customer, country="")  # the only delivery country is chosen automatically
    assert response.status_code == 201
    [address] = response.json()["addresses"]
    assert address["is_default"] is True and address["country"] == "United States"


def test_address_rules_are_reported_together(client, customer):
    response = add_address(
        client, customer, full_name="  ", phone="call me", line1="x" * 101, city="Line\nbreak", postal_code="12#45",
        country="Atlantis",
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [
        "Full name is required.",
        "Address line 1 must be at most 100 characters.",
        "City must be on one line without special characters.",
        "Phone number must have at least 6 digits and may only contain digits, spaces and + - ( ).",
        "Postal code may only contain letters, digits, spaces and hyphens.",
        "We do not deliver to Atlantis. Please choose one of: United States.",
    ]
    assert add_address(client, customer, phone="12345").status_code == 422  # fewer than 6 digits


def test_at_most_ten_addresses(client, customer):
    for _ in range(9):
        assert add_address(client, customer).status_code == 201
    response = add_address(client, customer)
    assert response.status_code == 409
    assert "at most 10 addresses" in response.json()["detail"]


def test_addresses_are_private_and_customers_only(client, admin, customer):
    bob = login(client, "bob", "bob12345", "customer")
    bobs = addresses(client, bob)[0]
    assert client.put(f"/api/account/addresses/{bobs['id']}", json=HOME, headers=customer).status_code == 404
    assert client.delete(f"/api/account/addresses/{bobs['id']}", headers=customer).status_code == 404
    assert client.post(f"/api/account/addresses/{bobs['id']}/default", headers=customer).status_code == 404
    assert checkout(client, customer, 1, address_id=bobs["id"])["delivery"]["address"] is None
    assert client.get("/api/account/addresses", headers=admin).status_code == 403
    assert client.get("/api/account/addresses").status_code == 401


def test_addresses_in_countries_no_longer_delivered_to(client, admin, customer):
    client.app.state.settings.delivery_countries = ("Canada", "United States")
    assert add_address(client, customer, country="").status_code == 422  # two countries: one must be chosen
    response = add_address(client, customer, country="Canada", postal_code="K1A 0B1")
    assert response.status_code == 201
    canadian = response.json()["address_id"]

    shirt = create_product(client, admin, price="10", stock={"S": 5}).json()
    client.app.state.settings.delivery_countries = ("United States",)
    book = client.get("/api/account/addresses", headers=customer).json()
    assert book["countries"] == ["United States"]
    assert next(a for a in book["addresses"] if a["id"] == canadian)["deliverable"] is False
    summary = checkout(client, customer, shirt["id"], address_id=canadian)
    assert summary["ready"] is False
    assert summary["delivery_issues"] == ["We no longer deliver to Canada. Please choose another address."]


# --- Delivery methods (FR103, FR104) -------------------------------------------


def test_upgrade_creates_standard_and_express_delivery(client, admin):
    real_methods_only(client)
    data = client.get("/api/admin/shipping-methods", headers=admin).json()
    assert [(m["name"], m["description"], m["fee"], m["free_over"], m["active"]) for m in data["methods"]] == [
        ("Standard delivery", "3–5 business days", 5.0, 50.0, True),
        ("Express delivery", "1–2 business days", 15.0, None, True),
    ]
    assert data["active_count"] == 2


def test_admin_manages_methods(client, admin, customer):
    response = client.post(
        "/api/admin/shipping-methods",
        json={"name": " Pickup ", "description": "Collect from our store", "fee": "0", "free_over": ""},
        headers=admin,
    )
    assert response.status_code == 201, response.text
    method_id = response.json()["method_id"]
    assert response.json()["message"] == 'Delivery method "Pickup" has been added.'

    duplicate = client.post("/api/admin/shipping-methods", json={"name": "pickup", "fee": "1"}, headers=admin)
    assert duplicate.status_code == 422 and "already exists" in duplicate.json()["detail"]

    edited = client.put(
        f"/api/admin/shipping-methods/{method_id}",
        json={"name": "Pickup", "description": "", "fee": "2.50", "free_over": "20", "active": False},
        headers=admin,
    )
    assert edited.status_code == 200, edited.text
    pickup = next(m for m in edited.json()["methods"] if m["id"] == method_id)
    assert (pickup["fee"], pickup["free_over"], pickup["active"]) == (2.5, 20.0, False)

    assert client.delete(f"/api/admin/shipping-methods/{method_id}", headers=admin).status_code == 200
    assert client.delete(f"/api/admin/shipping-methods/{method_id}", headers=admin).status_code == 404
    assert client.get("/api/admin/shipping-methods", headers=customer).status_code == 403


def test_method_rules_are_reported_together(client, admin):
    response = client.post(
        "/api/admin/shipping-methods",
        json={"name": "", "description": "d" * 101, "fee": "1000.01", "free_over": "0"},
        headers=admin,
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [
        "Name is required.",
        "Description must be at most 100 characters.",
        "Fee must be an amount from 0.00 to 1000.00 with at most two decimal places.",
        "Free delivery threshold must be an amount from 0.01 to 1000000.00 with at most two decimal places, or empty.",
    ]
    missing_fee = client.post("/api/admin/shipping-methods", json={"name": "X", "fee": ""}, headers=admin)
    assert missing_fee.json()["errors"] == ["Fee is required (enter 0 for free delivery)."]


# --- Checkout (FR105, FR106) ----------------------------------------------------


def test_checkout_uses_default_address_and_cheapest_method(client, admin, customer):
    real_methods_only(client)
    shirt = create_product(client, admin, price="20", stock={"S": 5}).json()
    summary = checkout(client, customer, shirt["id"])
    assert summary["ready"] is True and summary["delivery_issues"] == []
    assert summary["delivery"]["address"]["is_default"] is True
    assert summary["delivery"]["method"]["name"] == "Standard delivery"
    assert (summary["items_total"], summary["shipping_fee"], summary["total"]) == (20.0, 5.0, 25.0)
    standard = methods_by_name(summary)["Standard delivery"]
    assert standard["amount_to_free"] == 30.0

    express = methods_by_name(summary)["Express delivery"]
    summary = checkout(client, customer, shirt["id"], shipping_method_id=express["id"])
    assert (summary["shipping_fee"], summary["total"]) == (15.0, 35.0)


def test_free_delivery_threshold(client, admin, customer):
    real_methods_only(client)
    shirt = create_product(client, admin, price="25", stock={"S": 5}).json()
    summary = checkout(client, customer, shirt["id"], quantity=2)  # items total 50.00 reaches the threshold
    standard = methods_by_name(summary)["Standard delivery"]
    assert (standard["fee"], standard["amount_to_free"]) == (0.0, None)
    assert (summary["shipping_fee"], summary["total"]) == (0.0, 50.0)
    # Free is now cheaper than express, so it is listed first.
    assert [m["name"] for m in summary["delivery"]["methods"]] == ["Standard delivery", "Express delivery"]


def test_checkout_reports_delivery_problems(client, admin, customer):
    shirt = create_product(client, admin, price="10", stock={"S": 5}).json()
    method_id = checkout(client, customer, shirt["id"])["delivery"]["method"]["id"]

    _sql(client, "UPDATE shipping_methods SET active = ? WHERE id = ?", (False, method_id))
    summary = checkout(client, customer, shirt["id"], shipping_method_id=method_id)
    assert summary["ready"] is False and summary["delivery"]["method"] is None
    assert summary["delivery_issues"] == ["The delivery method you chose is no longer available. Please choose another one."]

    _sql(client, "UPDATE shipping_methods SET active = ?", (False,))
    summary = checkout(client, customer, shirt["id"])
    assert summary["delivery_issues"] == [
        "Delivery is not available at the moment, so orders cannot be placed. Please try again later."
    ]

    _sql(client, "DELETE FROM addresses")
    summary = checkout(client, customer, shirt["id"], address_id=12345)
    assert summary["delivery_issues"][0] == (
        "The delivery address you chose is no longer in your address book. Please choose another one."
    )
    assert checkout(client, customer, shirt["id"])["delivery_issues"][0] == "Please add a delivery address."


# --- Orders (FR41, FR42, FR106-FR109) -------------------------------------------------


def test_order_records_delivery_and_charges_the_fee(client, admin, customer):
    real_methods_only(client)
    shirt = create_product(client, admin, price="20", stock={"S": 5}).json()
    address_id = add_address(client, customer).json()["address_id"]
    summary = checkout(client, customer, shirt["id"], address_id=address_id)
    method = summary["delivery"]["method"]

    response = place(client, customer, shirt["id"], 25.0, address_id, method["id"])
    assert response.status_code == 201, response.text
    order = response.json()
    assert (order["items_total"], order["shipping_fee"], order["total"]) == (20.0, 5.0, 25.0)
    assert order["delivery"]["method"] == "Standard delivery"
    assert order["delivery"]["address"]["phone"] == HOME["phone"]
    assert order["delivery"]["address"]["lines"][-2:] == ["Springfield, IL 62701", "United States"]

    complete_mock_payment(client, order["payment_url"])
    paid = client.get(f"/api/orders/{order['id']}", headers=customer).json()
    assert paid["status"] == "paid" and paid["payments"][0]["amount"] == 25.0

    # The order keeps the address and method as they were (FR107).
    client.put(f"/api/account/addresses/{address_id}", json={**HOME, "line1": "1 Other Road"}, headers=customer)
    client.put(f"/api/admin/shipping-methods/{method['id']}",
               json={"name": "Renamed", "fee": "9", "free_over": ""}, headers=admin)
    client.delete(f"/api/account/addresses/{address_id}", headers=customer)
    again = client.get(f"/api/admin/orders/{order['id']}", headers=admin).json()
    assert again["delivery"]["address"]["line1"] == "12 Market Street"
    assert (again["delivery"]["method"], again["shipping_fee"]) == ("Standard delivery", 5.0)

    # Cancelling refunds everything paid, delivery fee included (FR106).
    cancelled = client.post(f"/api/orders/{order['id']}/cancel", headers=customer).json()
    assert cancelled["refunds"][0]["amount"] == 25.0


def test_order_needs_a_valid_delivery_choice(client, admin, customer):
    real_methods_only(client)
    shirt = create_product(client, admin, price="20", stock={"S": 5}).json()
    summary = checkout(client, customer, shirt["id"])
    address_id, method_id = summary["delivery"]["address"]["id"], summary["delivery"]["method"]["id"]

    # The fee changed after the Payment page showed the total (FR42).
    _sql(client, "UPDATE shipping_methods SET fee_cents = 700 WHERE id = ?", (method_id,))
    response = place(client, customer, shirt["id"], 25.0, address_id, method_id)
    assert response.status_code == 409
    assert response.json()["summary"]["total"] == 27.0

    client.delete(f"/api/account/addresses/{address_id}", headers=customer)
    response = place(client, customer, shirt["id"], 27.0, address_id, method_id)
    assert response.status_code == 409
    assert "no longer in your address book" in response.json()["detail"]

    body = {"source": "buy_now", "product_id": shirt["id"], "size": "S", "quantity": 1, "expected_total": 27.0,
            "request_id": uuid.uuid4().hex}
    missing = client.post("/api/orders", json=body, headers=customer)
    assert missing.status_code == 422
    assert missing.json()["errors"] == [
        "Please choose a delivery address on the checkout page.",
        "Please choose a delivery method on the checkout page.",
    ]
    # Nothing was ordered, so the stock is untouched.
    assert client.get(f"/api/products/{shirt['id']}").json()["sizes"][0]["stock"] == 5


def test_shipping_details_reach_the_customer(client, admin, customer):
    _sql(client, "UPDATE users SET email = 'alice@example.com', email_verified_at = 'x' WHERE username = 'alice'")
    real_methods_only(client)
    shirt = create_product(client, admin, price="20", stock={"S": 5}).json()
    summary = checkout(client, customer, shirt["id"])
    order = place(client, customer, shirt["id"], 25.0, summary["delivery"]["address"]["id"],
                  summary["delivery"]["method"]["id"]).json()

    placed = emails(client, "alice@example.com", "order_awaiting_payment")[0]["body"]
    assert "Items: $20.00" in placed and "Delivery (Standard delivery): $5.00" in placed and "Total: $25.00" in placed
    assert "  Test Customer\n  1 Test Street\n  Testville, TS 12345\n  United States" in placed

    complete_mock_payment(client, order["payment_url"])
    url = f"/api/admin/orders/{order['id']}/status"
    bad = client.post(url, json={"status": "shipped", "carrier": "UPS\nX"}, headers=admin)
    assert bad.status_code == 422
    too_long = client.post(url, json={"status": "shipped", "tracking_number": "1" * 51}, headers=admin)
    assert too_long.json()["errors"] == ["Tracking number must be at most 50 characters."]

    shipped = client.post(url, json={"status": "shipped", "carrier": " UPS ", "tracking_number": "1Z999"}, headers=admin)
    assert shipped.status_code == 200, shipped.text
    mine = client.get(f"/api/orders/{order['id']}", headers=customer).json()
    assert mine["shipping"] == {"carrier": "UPS", "tracking_number": "1Z999"}
    body = emails(client, "alice@example.com", "order_shipped")[0]["body"]
    assert "Carrier: UPS" in body and "Tracking number: 1Z999" in body


def test_shipping_without_details(client, admin, customer):
    shirt = create_product(client, admin, price="20", stock={"S": 5}).json()
    summary = checkout(client, customer, shirt["id"])
    order = place(client, customer, shirt["id"], 20.0, summary["delivery"]["address"]["id"],
                  summary["delivery"]["method"]["id"]).json()
    complete_mock_payment(client, order["payment_url"])
    client.post(f"/api/admin/orders/{order['id']}/status", json={"status": "shipped"}, headers=admin)
    assert client.get(f"/api/orders/{order['id']}", headers=customer).json()["shipping"] == {
        "carrier": None, "tracking_number": None,
    }


def test_orders_from_earlier_versions_have_no_delivery_details(database_url):
    command.upgrade(_config(database_url), "0003")
    conn = connect(database_url)
    conn.execute("INSERT INTO users (username, password_hash, role, display_name) VALUES ('ann', 'x', 'customer', 'Ann')")
    order_id = conn.insert(
        """INSERT INTO orders (user_id, status, source, total_cents, request_id, created_at, updated_at)
           VALUES (1, 'paid', 'cart', 1234, 'req-1', '2026-11-01', '2026-11-01')"""
    )
    conn.commit()
    conn.close()

    command.upgrade(_config(database_url), "0004")
    conn = connect(database_url)
    row = conn.execute("SELECT items_cents, shipping_cents, delivery_method FROM orders WHERE id = ?", (order_id,)).fetchone()
    assert tuple(row) == (1234, 0, None)
    assert conn.execute("SELECT COUNT(*) FROM shipping_methods WHERE active = ?", (True,)).fetchone()[0] == 2
    conn.close()

    from app.order_service import get_order

    conn = connect(database_url)
    order = get_order(conn, order_id, "admin")
    conn.close()
    assert order["delivery"] is None and (order["items_total"], order["shipping_fee"]) == (12.34, 0.0)

    command.downgrade(_config(database_url), "0003")
    command.upgrade(_config(database_url), "head")
