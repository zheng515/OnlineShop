from conftest import PNG_BYTES, create_product, update_product, upload_image


def test_add_view_and_list_product(client, admin):
    response = create_product(client, admin, name="Blue Shirt", price="19.99", stock={"M": 3, "S": 1}, description="Soft.\nWarm.")
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["price"] == 19.99
    assert product["description"] == "Soft.\nWarm."
    assert product["category"] is None
    assert [s["size"] for s in product["sizes"]] == ["S", "M"]

    detail = client.get(f"/api/admin/products/{product['id']}", headers=admin).json()
    assert detail["sizes"] == [{"size": "S", "stock": 1}, {"size": "M", "stock": 3}]
    assert detail["image_url"] == detail["images"][0]["url"]
    assert client.get(detail["image_url"]).content == PNG_BYTES

    listing = client.get("/api/admin/products", headers=admin).json()
    assert listing["count"] == 1 and listing["pages"] == 1


def test_search_in_management(client, admin):
    create_product(client, admin, name="Red Hoodie")
    create_product(client, admin, name="Green Tee", description="Pairs well with a hoodie")
    names = [p["name"] for p in client.get("/api/admin/products?q=HOOD", headers=admin).json()["products"]]
    assert names == ["Green Tee", "Red Hoodie"]


def test_validation_rules(client, admin):
    # Category 1 exists, so `true` (an int in Python) must still be rejected.
    assert client.post("/api/admin/categories", json={"name": "Shirts"}, headers=admin).json()["id"] == 1
    cases = [
        ({"name": ""}, "name is required"),
        ({"price": "0"}, "greater than zero"),
        ({"price": "-5"}, "greater than zero"),
        ({"price": "abc"}, "number"),
        ({"price": "1.234"}, "two decimal places"),
        ({"stock": {"S": -1}}, "non-negative"),
        ({"stock": {"S": 1.5}}, "non-negative"),
        ({"stock": {"XXL": 2}}, "not allowed"),
        ({"stock": {}}, "At least one size"),
        ({"image": None}, "At least one product image"),
        ({"description": "x" * 2001}, "at most 2000"),
        ({"category_id": 999}, "category no longer exists"),
        ({"category_id": True}, "category no longer exists"),
    ]
    for override, expected in cases:
        response = create_product(client, admin, **override)
        assert response.status_code == 422, override
        assert expected.lower() in response.json()["detail"].lower(), (override, response.json())


def test_all_problems_reported_together(client, admin):
    response = create_product(client, admin, name="", price="0", stock={}, image=None)
    assert len(response.json()["errors"]) == 4


def test_unsupported_image_rejected(client, admin):
    response = upload_image(client, admin, b"not an image", "evil.png")
    assert response.status_code == 422
    assert "Unsupported image format" in response.json()["detail"]


def test_image_rules(client, admin):
    ids = [upload_image(client, admin).json()["id"] for _ in range(9)]
    too_many = create_product(client, admin, image=None, image_ids=ids)
    assert "at most 8 images" in too_many.json()["detail"]
    duplicate = create_product(client, admin, image=None, image_ids=[ids[0], ids[0]])
    assert "more than once" in duplicate.json()["detail"]

    owner = create_product(client, admin, image=None, image_ids=[ids[0]]).json()
    stolen = create_product(client, admin, image=None, image_ids=[ids[0]])
    assert stolen.status_code == 422 and "no longer available" in stolen.json()["detail"]
    assert update_product(client, admin, owner["id"], image_ids=[]).status_code == 422


def test_reorder_add_and_remove_images(client, admin):
    first, second, third = (upload_image(client, admin).json() for _ in range(3))
    product = create_product(client, admin, image=None, image_ids=[first["id"], second["id"]]).json()
    assert [i["id"] for i in product["images"]] == [first["id"], second["id"]]

    updated = update_product(client, admin, product["id"], image_ids=[third["id"], second["id"]]).json()
    assert [i["id"] for i in updated["images"]] == [third["id"], second["id"]]
    assert updated["image_url"] == third["url"]
    assert client.get(first["url"]).status_code == 404  # removed image deleted
    assert client.get(second["url"]).status_code == 200


def test_update_product(client, admin):
    product = create_product(client, admin).json()
    response = update_product(client, admin, product["id"], name="Renamed", price="12.5", stock={"L": 4, "XL": 0})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert (updated["name"], updated["price"]) == ("Renamed", 12.5)
    assert updated["image_url"] == product["image_url"]
    assert updated["sizes"] == [{"size": "L", "stock": 4}, {"size": "XL", "stock": 0}]


def test_delete_product_removes_its_images(client, admin):
    product = create_product(client, admin).json()
    assert client.delete(f"/api/admin/products/{product['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/admin/products/{product['id']}", headers=admin).status_code == 404
    assert client.get(product["image_url"]).status_code == 404


def test_admin_sorting_filtering_and_pages(client, admin):
    shirts = client.post("/api/admin/categories", json={"name": "Shirts"}, headers=admin).json()
    for index in range(25):
        create_product(client, admin, name=f"P{index:02d}", price=str(index + 1), stock={"S": 25 - index},
                       category_id=shirts["id"] if index % 5 == 0 else None)

    first = client.get("/api/admin/products", headers=admin).json()
    assert (first["total"], first["pages"], len(first["products"])) == (25, 2, 20)
    assert first["products"][0]["name"] == "P24"
    second = client.get("/api/admin/products?page=2", headers=admin).json()
    assert [p["name"] for p in second["products"]] == ["P04", "P03", "P02", "P01", "P00"]
    assert client.get("/api/admin/products?page=99", headers=admin).json()["page"] == 2

    low_stock = client.get("/api/admin/products?sort=stock_asc", headers=admin).json()["products"]
    assert low_stock[0]["name"] == "P24" and low_stock[0]["total_stock"] == 1
    in_category = client.get(f"/api/admin/products?category={shirts['id']}", headers=admin).json()
    assert in_category["total"] == 5
    assert all(p["category"]["name"] == "Shirts" for p in in_category["products"])


def test_unattached_uploads_are_cleaned_up_after_24_hours(client, admin, monkeypatch):
    from datetime import timedelta

    from app import product_images
    from app.security import utcnow

    stale = upload_image(client, admin).json()
    kept = create_product(client, admin).json()
    later = utcnow() + timedelta(hours=25)
    monkeypatch.setattr(product_images, "utcnow", lambda: later)
    fresh = upload_image(client, admin).json()  # each upload triggers the cleanup

    assert client.get(stale["url"]).status_code == 404
    assert client.get(fresh["url"]).status_code == 200
    assert client.get(kept["image_url"]).status_code == 200
    assert create_product(client, admin, image=None, image_ids=[stale["id"]]).status_code == 422
