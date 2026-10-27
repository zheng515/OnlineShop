import json

from conftest import PNG_BYTES, create_product


def test_add_view_and_list_product(client, admin):
    response = create_product(client, admin, name="Blue Shirt", price="19.99", stock={"M": 3, "S": 1})
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["price"] == 19.99
    assert [s["size"] for s in product["sizes"]] == ["S", "M"]

    detail = client.get(f"/api/admin/products/{product['id']}", headers=admin).json()
    assert detail["sizes"] == [{"size": "S", "stock": 1}, {"size": "M", "stock": 3}]
    assert client.get(detail["image_url"]).content == PNG_BYTES

    listing = client.get("/api/admin/products", headers=admin).json()
    assert listing["count"] == 1


def test_search_in_management(client, admin):
    create_product(client, admin, name="Red Hoodie")
    create_product(client, admin, name="Green Tee")
    names = [p["name"] for p in client.get("/api/admin/products?q=hood", headers=admin).json()["products"]]
    assert names == ["Red Hoodie"]


def test_validation_rules(client, admin):
    cases = [
        ({"name": ""}, "name is required"),
        ({"price": "0"}, "greater than zero"),
        ({"price": "-5"}, "greater than zero"),
        ({"price": "abc"}, "number"),
        ({"stock": {"S": -1}}, "non-negative"),
        ({"stock": {"S": 1.5}}, "non-negative"),
        ({"stock": {"XXL": 2}}, "not allowed"),
        ({"stock": {}}, "At least one size"),
        ({"image": None}, "image is required"),
    ]
    for override, expected in cases:
        response = create_product(client, admin, **override)
        assert response.status_code == 422, override
        assert expected.lower() in response.json()["detail"].lower(), (override, response.json())


def test_unsupported_image_rejected(client, admin):
    response = create_product(client, admin, image=b"not an image", filename="evil.png")
    assert response.status_code == 422
    assert "Unsupported image format" in response.json()["detail"]


def test_update_product_and_replace_image(client, admin):
    product = create_product(client, admin).json()
    old_image = product["image_url"]
    response = client.put(
        f"/api/admin/products/{product['id']}",
        data={"name": "Renamed", "price": "12.5", "stock": json.dumps({"L": 4, "XL": 0})},
        headers=admin,
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == "Renamed"
    assert updated["price"] == 12.5
    assert updated["image_url"] == old_image
    assert updated["sizes"] == [{"size": "L", "stock": 4}, {"size": "XL", "stock": 0}]

    gif = b"GIF89a" + b"\x00" * 20
    response = client.put(
        f"/api/admin/products/{product['id']}",
        data={"name": "Renamed", "price": "12.5", "stock": json.dumps({"L": 4})},
        files={"image": ("new.gif", gif, "image/gif")},
        headers=admin,
    )
    assert response.json()["image_url"] != old_image
    assert client.get(old_image).status_code == 404


def test_delete_product(client, admin):
    product = create_product(client, admin).json()
    assert client.delete(f"/api/admin/products/{product['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/admin/products/{product['id']}", headers=admin).status_code == 404
