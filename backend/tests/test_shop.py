import json

from conftest import create_product


def test_browse_and_case_insensitive_search(client, admin, customer):
    create_product(client, admin, name="Summer Dress")
    create_product(client, admin, name="Winter Coat")
    results = client.get("/api/products?q=SUMMER", headers=customer).json()
    assert [p["name"] for p in results["products"]] == ["Summer Dress"]
    assert set(results["products"][0]) >= {"name", "price", "image_url"}
    assert client.get("/api/products?q=nothing", headers=customer).json()["count"] == 0


def test_product_detail_shows_sizes_and_stock(client, admin, customer):
    product = create_product(client, admin, stock={"S": 0, "L": 3}).json()
    detail = client.get(f"/api/products/{product['id']}", headers=customer).json()
    assert detail["sizes"] == [
        {"size": "S", "stock": 0, "in_stock": False},
        {"size": "L", "stock": 3, "in_stock": True},
    ]


def test_add_to_cart_merges_duplicates_and_checks_stock(client, admin, customer):
    product = create_product(client, admin, price="2.50", stock={"M": 5}).json()
    item = {"product_id": product["id"], "size": "M", "quantity": 2}
    assert client.post("/api/cart/items", json=item, headers=customer).status_code == 201
    cart = client.post("/api/cart/items", json=item, headers=customer).json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 4
    assert cart["items"][0]["subtotal"] == 10.0
    assert cart["total"] == 10.0

    response = client.post("/api/cart/items", json=item, headers=customer)
    assert response.status_code == 409
    assert "already have 4" in response.json()["detail"]


def test_cannot_add_out_of_stock_or_missing_size(client, admin, customer):
    product = create_product(client, admin, stock={"S": 0}).json()
    out = client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 1}, headers=customer)
    assert out.status_code == 409 and "out of stock" in out.json()["detail"]
    missing = client.post("/api/cart/items", json={"product_id": product["id"], "size": "L", "quantity": 1}, headers=customer)
    assert missing.status_code == 409


def test_quantity_must_be_positive_integer(client, admin, customer):
    product = create_product(client, admin).json()
    for quantity in (0, -1, 1.5, "2"):
        response = client.post(
            "/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": quantity}, headers=customer
        )
        assert response.status_code == 422, quantity
        assert "positive whole number" in response.json()["detail"]


def test_update_and_remove_cart_items(client, admin, customer):
    product = create_product(client, admin, stock={"S": 3}).json()
    cart = client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 1}, headers=customer).json()
    item_id = cart["items"][0]["id"]
    assert client.patch(f"/api/cart/items/{item_id}", json={"quantity": 3}, headers=customer).json()["items"][0]["quantity"] == 3
    assert client.patch(f"/api/cart/items/{item_id}", json={"quantity": 4}, headers=customer).status_code == 409
    assert client.patch(f"/api/cart/items/{item_id}", json={"quantity": 0}, headers=customer).status_code == 422
    cart = client.delete(f"/api/cart/items/{item_id}", headers=customer).json()
    assert cart["empty"] is True


def test_cart_is_per_customer(client, admin, customer):
    from conftest import login

    product = create_product(client, admin).json()
    cart = client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 1}, headers=customer).json()
    bob = login(client, "bob", "bob123", "customer")
    assert client.get("/api/cart", headers=bob).json()["empty"] is True
    assert client.delete(f"/api/cart/items/{cart['items'][0]['id']}", headers=bob).status_code == 404


def test_empty_cart_cannot_checkout(client, customer):
    summary = client.post("/api/checkout", json={"source": "cart"}, headers=customer).json()
    assert summary["valid"] is False
    assert "empty" in summary["issues"][0]


def test_checkout_uses_current_price(client, admin, customer):
    product = create_product(client, admin, price="10", stock={"S": 5}).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 2}, headers=customer)
    client.put(
        f"/api/admin/products/{product['id']}",
        data={"name": product["name"], "price": "7.25", "stock": json.dumps({"S": 5})},
        headers=admin,
    )
    summary = client.post("/api/checkout", json={"source": "cart"}, headers=customer).json()
    assert summary["valid"] is True
    assert summary["items"][0]["unit_price"] == 7.25
    assert summary["total"] == 14.5


def test_checkout_revalidates_stock(client, admin, customer):
    product = create_product(client, admin, stock={"S": 5}).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 4}, headers=customer)
    client.put(
        f"/api/admin/products/{product['id']}",
        data={"name": product["name"], "price": "10", "stock": json.dumps({"S": 2})},
        headers=admin,
    )
    summary = client.post("/api/checkout", json={"source": "cart"}, headers=customer).json()
    assert summary["valid"] is False
    assert summary["items"][0]["status"] == "insufficient_stock"
    assert product["name"] in summary["issues"][0]


def test_deleted_product_in_cart_is_flagged(client, admin, customer):
    product = create_product(client, admin, name="Gone Soon").json()
    client.post("/api/cart/items", json={"product_id": product["id"], "size": "S", "quantity": 1}, headers=customer)
    client.delete(f"/api/admin/products/{product['id']}", headers=admin)
    cart = client.get("/api/cart", headers=customer).json()
    assert cart["items"][0]["status"] == "unavailable"
    assert "Gone Soon" in cart["items"][0]["message"]
    assert client.post("/api/checkout", json={"source": "cart"}, headers=customer).json()["valid"] is False


def test_buy_now_checkout_does_not_touch_cart(client, admin, customer):
    product = create_product(client, admin, price="3", stock={"M": 2}).json()
    body = {"source": "buy_now", "product_id": product["id"], "size": "M", "quantity": 2}
    summary = client.post("/api/checkout", json=body, headers=customer).json()
    assert summary["valid"] is True and summary["total"] == 6.0
    assert client.get("/api/cart", headers=customer).json()["empty"] is True

    body["quantity"] = 3
    assert client.post("/api/checkout", json=body, headers=customer).json()["valid"] is False

    incomplete = client.post("/api/checkout", json={"source": "buy_now"}, headers=customer)
    assert incomplete.status_code == 422
