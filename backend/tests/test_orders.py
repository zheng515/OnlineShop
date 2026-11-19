import threading
import uuid

from app.database import connect
from app.errors import ValidationProblem
from app.order_service import place_order
from app.orders import Line

from conftest import create_product, login, update_product, upload_image


def add_to_cart(client, headers, product_id, size, quantity):
    item = {"product_id": product_id, "size": size, "quantity": quantity}
    response = client.post("/api/cart/items", json=item, headers=headers)
    assert response.status_code == 201, response.text


def place(client, headers, expected_total, request_id=None, **source):
    body = {"source": "cart", **source, "expected_total": expected_total, "request_id": request_id or uuid.uuid4().hex}
    return client.post("/api/orders", json=body, headers=headers)


def stock_of(client, admin, product_id):
    return {s["size"]: s["stock"] for s in client.get(f"/api/admin/products/{product_id}", headers=admin).json()["sizes"]}


def test_cart_order_deducts_stock_and_empties_cart(client, admin, customer):
    shirt = create_product(client, admin, name="Shirt", price="10.00", stock={"S": 5, "M": 2}).json()
    add_to_cart(client, customer, shirt["id"], "S", 2)
    add_to_cart(client, customer, shirt["id"], "M", 1)

    response = place(client, customer, 30.0)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "placed"
    assert order["number"] == f"#{order['id']:06d}"
    assert order["total"] == 30.0
    assert [(i["size"], i["quantity"], i["subtotal"]) for i in order["items"]] == [("S", 2, 20.0), ("M", 1, 10.0)]
    assert order["history"][0]["status"] == "placed"
    assert order["allowed_actions"] == ["cancelled"]

    assert stock_of(client, admin, shirt["id"]) == {"S": 3, "M": 1}
    assert client.get("/api/cart", headers=customer).json()["empty"] is True


def test_buy_now_order_leaves_cart_untouched(client, admin, customer):
    shirt = create_product(client, admin, price="4.50", stock={"L": 3}).json()
    add_to_cart(client, customer, shirt["id"], "L", 1)
    response = place(client, customer, 9.0, source="buy_now", product_id=shirt["id"], size="L", quantity=2)
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "buy_now"
    assert stock_of(client, admin, shirt["id"]) == {"L": 1}
    assert client.get("/api/cart", headers=customer).json()["item_count"] == 1


def test_invalid_order_changes_nothing(client, admin, customer):
    shirt = create_product(client, admin, stock={"S": 5}).json()
    add_to_cart(client, customer, shirt["id"], "S", 4)
    update_product(client, admin, shirt["id"], stock={"S": 3})
    response = place(client, customer, 40.0)
    assert response.status_code == 409
    body = response.json()
    assert "Only 3 left" in body["detail"]
    assert body["summary"]["items"][0]["status"] == "insufficient_stock"
    assert stock_of(client, admin, shirt["id"]) == {"S": 3}
    assert client.get("/api/cart", headers=customer).json()["item_count"] == 4
    assert client.get("/api/orders", headers=customer).json()["count"] == 0


def test_empty_cart_cannot_be_ordered(client, customer):
    response = place(client, customer, 1.0)
    assert response.status_code == 409
    assert "empty" in response.json()["detail"]


def test_price_change_requires_confirmation(client, admin, customer):
    shirt = create_product(client, admin, price="10.00", stock={"S": 5}).json()
    add_to_cart(client, customer, shirt["id"], "S", 1)
    update_product(client, admin, shirt["id"], price="12.00")
    response = place(client, customer, 10.0)
    assert response.status_code == 409
    assert "Prices have changed" in response.json()["detail"]
    assert response.json()["summary"]["total"] == 12.0
    assert place(client, customer, 12.0).status_code == 201


def test_repeated_submission_creates_one_order(client, admin, customer):
    shirt = create_product(client, admin, price="5", stock={"M": 10}).json()
    body = {"source": "buy_now", "product_id": shirt["id"], "size": "M", "quantity": 2}
    first = place(client, customer, 10.0, request_id="same-request-1", **body)
    second = place(client, customer, 10.0, request_id="same-request-1", **body)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert stock_of(client, admin, shirt["id"]) == {"M": 8}
    assert client.get("/api/orders", headers=customer).json()["count"] == 1


def test_concurrent_orders_never_oversell(client, admin):
    shirt = create_product(client, admin, price="1", stock={"S": 3}).json()
    database_url = client.app.state.settings.database_url
    results: list[str] = []

    def buy(username):
        conn = connect(database_url)
        try:
            user = conn.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
            place_order(conn, user, "buy_now", Line(shirt["id"], "S", 1), 100, uuid.uuid4().hex)
            results.append("ok")
        except ValidationProblem:
            results.append("rejected")
        finally:
            conn.close()

    threads = [threading.Thread(target=buy, args=(name,)) for name in ["alice", "bob"] * 4]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("ok") == 3 and results.count("rejected") == 5
    assert stock_of(client, admin, shirt["id"]) == {"S": 0}


def test_customer_history_and_cancel_restores_stock(client, admin, customer):
    shirt = create_product(client, admin, price="2", stock={"S": 4, "M": 4}).json()
    order = place(client, customer, 6.0, source="buy_now", product_id=shirt["id"], size="S", quantity=3).json()

    history = client.get("/api/orders", headers=customer).json()
    assert [o["id"] for o in history["orders"]] == [order["id"]]
    assert history["orders"][0]["item_count"] == 3

    response = client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert cancelled["status"] == "cancelled"
    assert [e["status"] for e in cancelled["history"]] == ["placed", "cancelled"]
    assert cancelled["allowed_actions"] == []
    assert stock_of(client, admin, shirt["id"]) == {"S": 4, "M": 4}

    again = client.post(f"/api/orders/{order['id']}/cancel", headers=customer)
    assert again.status_code == 409
    assert "can no longer be cancelled" in again.json()["detail"]


def test_cancel_skips_deleted_products_and_removed_sizes(client, admin, customer):
    keep = create_product(client, admin, name="Keep", price="1", stock={"S": 2, "M": 2}).json()
    gone = create_product(client, admin, name="Gone", price="1", stock={"S": 2}).json()
    add_to_cart(client, customer, keep["id"], "S", 1)
    add_to_cart(client, customer, keep["id"], "M", 1)
    add_to_cart(client, customer, gone["id"], "S", 1)
    order = place(client, customer, 3.0).json()

    update_product(client, admin, keep["id"], stock={"S": 1})
    client.delete(f"/api/admin/products/{gone['id']}", headers=admin)

    assert client.post(f"/api/orders/{order['id']}/cancel", headers=customer).status_code == 200
    assert stock_of(client, admin, keep["id"]) == {"S": 2}


def test_order_keeps_snapshot_after_product_changes(client, admin, customer):
    shirt = create_product(client, admin, name="Original", price="8", stock={"S": 5}).json()
    order = place(client, customer, 8.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()

    new_image = upload_image(client, admin).json()["id"]
    update_product(client, admin, shirt["id"], name="Renamed", price="99", image_ids=[new_image])
    client.delete(f"/api/admin/products/{shirt['id']}", headers=admin)

    item = client.get(f"/api/orders/{order['id']}", headers=customer).json()["items"][0]
    assert (item["name"], item["unit_price"]) == ("Original", 8.0)
    assert item["image_url"] == shirt["image_url"]
    assert client.get(item["image_url"]).status_code == 200


def test_customers_only_see_their_own_orders(client, admin, customer):
    shirt = create_product(client, admin, price="1", stock={"S": 5}).json()
    order = place(client, customer, 1.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    bob = login(client, "bob", "bob12345", "customer")
    assert client.get("/api/orders", headers=bob).json()["count"] == 0
    assert client.get(f"/api/orders/{order['id']}", headers=bob).status_code == 404
    assert client.post(f"/api/orders/{order['id']}/cancel", headers=bob).status_code == 404
    assert client.get("/api/admin/orders", headers=customer).status_code == 403
    assert place(client, admin, 1.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).status_code == 403


def test_admin_status_flow(client, admin, customer):
    shirt = create_product(client, admin, price="3", stock={"S": 5}).json()
    order = place(client, customer, 3.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    url = f"/api/admin/orders/{order['id']}/status"

    assert client.post(url, json={"status": "completed"}, headers=admin).status_code == 409
    shipped = client.post(url, json={"status": "shipped"}, headers=admin).json()
    assert shipped["status"] == "shipped" and shipped["allowed_actions"] == ["completed"]
    assert client.post(f"/api/orders/{order['id']}/cancel", headers=customer).status_code == 409
    assert client.post(url, json={"status": "cancelled"}, headers=admin).status_code == 409
    completed = client.post(url, json={"status": "completed"}, headers=admin).json()
    assert [(e["status"], e["actor_role"]) for e in completed["history"]] == [
        ("placed", "customer"),
        ("shipped", "admin"),
        ("completed", "admin"),
    ]
    assert client.post(url, json={"status": "placed"}, headers=admin).status_code == 422


def test_admin_order_list_filter_and_search(client, admin, customer):
    shirt = create_product(client, admin, price="1", stock={"S": 10}).json()
    first = place(client, customer, 1.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    bob = login(client, "bob", "bob12345", "customer")
    second = place(client, bob, 1.0, source="buy_now", product_id=shirt["id"], size="S", quantity=1).json()
    client.post(f"/api/admin/orders/{first['id']}/status", json={"status": "shipped"}, headers=admin)

    def ids(query):
        return [o["id"] for o in client.get(f"/api/admin/orders{query}", headers=admin).json()["orders"]]

    assert ids("") == [second["id"], first["id"]]
    assert ids("?status=shipped") == [first["id"]]
    assert ids("?q=BOB") == [second["id"]]
    assert ids(f"?q={first['number'].replace('#', '%23')}") == [first["id"]]
    assert ids("?q=nobody") == []
    detail = client.get(f"/api/admin/orders/{first['id']}", headers=admin).json()
    assert detail["customer"]["username"] == "alice"


def test_concurrent_duplicate_submissions_create_one_order(client, admin):
    shirt = create_product(client, admin, price="1", stock={"S": 10}).json()
    database_url = client.app.state.settings.database_url
    results: list[tuple[int, bool]] = []

    def submit():
        conn = connect(database_url)
        try:
            user = conn.execute("SELECT id, username, role FROM users WHERE username = 'alice'").fetchone()
            results.append(place_order(conn, user, "buy_now", Line(shirt["id"], "S", 1), 100, "same-request-xyz"))
        finally:
            conn.close()

    threads = [threading.Thread(target=submit) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({order_id for order_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    assert stock_of(client, admin, shirt["id"]) == {"S": 9}
