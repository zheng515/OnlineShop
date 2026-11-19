import sqlite3

from conftest import create_product, update_product

from app.config import PROJECT_ROOT, Settings
from app.database import connect, init_schema
from app.products import CatalogueQuery, search_products


def category(client, admin, name):
    response = client.post("/api/admin/categories", json={"name": name}, headers=admin)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def names(client, headers, query=""):
    return [p["name"] for p in client.get(f"/api/products{query}", headers=headers).json()["products"]]


# --- FR60 categories -----------------------------------------------------


def test_category_management(client, admin, customer):
    shirts = category(client, admin, "Shirts")
    category(client, admin, "Empty")
    assert client.post("/api/admin/categories", json={"name": "  shirts "}, headers=admin).status_code == 409
    assert client.post("/api/admin/categories", json={"name": " "}, headers=admin).status_code == 422
    assert client.post("/api/admin/categories", json={"name": "x" * 51}, headers=admin).status_code == 422
    assert client.post("/api/admin/categories", json={"name": "Hats"}, headers=customer).status_code == 403

    product = create_product(client, admin, name="Oxford", category_id=shirts).json()
    assert product["category"] == {"id": shirts, "name": "Shirts"}

    admin_view = client.get("/api/categories", headers=admin).json()["categories"]
    assert [(c["name"], c["product_count"]) for c in admin_view] == [("Empty", 0), ("Shirts", 1)]
    # Customers only see categories that have products.
    assert [c["name"] for c in client.get("/api/categories", headers=customer).json()["categories"]] == ["Shirts"]

    renamed = client.put(f"/api/admin/categories/{shirts}", json={"name": "Tops"}, headers=admin)
    assert renamed.status_code == 200
    assert client.get(f"/api/products/{product['id']}", headers=customer).json()["category"]["name"] == "Tops"

    assert client.delete(f"/api/admin/categories/{shirts}", headers=admin).status_code == 200
    assert client.get(f"/api/admin/products/{product['id']}", headers=admin).json()["category"] is None


def test_category_names_unique_ignoring_non_ascii_case(client, admin):
    category(client, admin, "Ärmel")
    assert client.post("/api/admin/categories", json={"name": "ärmel"}, headers=admin).status_code == 409


# --- FR16 search, FR61 description -----------------------------------------


def test_search_matches_name_and_description_case_insensitively(client, admin, customer):
    create_product(client, admin, name="Plain Tee")
    create_product(client, admin, name="Weekend Shirt", description="Made from ORGANIC cotton")
    create_product(client, admin, name="ÄRMELLOS Top")
    assert names(client, customer, "?q=organic") == ["Weekend Shirt"]
    assert names(client, customer, "?q=ärmel") == ["ÄRMELLOS Top"]
    assert names(client, customer, "?q=%25") == []  # no wildcard injection


def test_customer_detail_has_images_description_and_category(client, admin, customer):
    shirts = category(client, admin, "Shirts")
    product = create_product(client, admin, description="<b>bold</b>", category_id=shirts).json()
    detail = client.get(f"/api/products/{product['id']}", headers=customer).json()
    assert detail["description"] == "<b>bold</b>"  # stored as plain text; the page escapes it
    assert detail["images"] == [product["image_url"]]
    assert detail["category"]["name"] == "Shirts"


# --- FR63-FR65 pagination, sorting, filtering ----------------------------------


def test_customer_pagination(client, admin, customer):
    for index in range(30):
        create_product(client, admin, name=f"P{index:02d}")
    page = client.get("/api/products", headers=customer).json()
    assert (page["total"], page["pages"], page["page_size"], len(page["products"])) == (30, 3, 12, 12)
    last = client.get("/api/products?page=3", headers=customer).json()
    assert len(last["products"]) == 6
    assert client.get("/api/products?page=50", headers=customer).json()["page"] == 3
    assert client.get("/api/products?page=abc", headers=customer).json()["page"] == 1
    assert client.get("/api/products?page=0", headers=customer).json()["page"] == 1


def test_sorting(client, admin, customer):
    create_product(client, admin, name="banana", price="5")
    create_product(client, admin, name="Apple", price="9")
    create_product(client, admin, name="cherry", price="5")
    assert names(client, customer) == ["cherry", "Apple", "banana"]
    assert names(client, customer, "?sort=price_asc") == ["cherry", "banana", "Apple"]
    assert names(client, customer, "?sort=price_desc") == ["Apple", "cherry", "banana"]
    assert names(client, customer, "?sort=name") == ["Apple", "banana", "cherry"]
    # Admin-only sort is ignored for customers.
    assert names(client, customer, "?sort=stock_asc") == ["cherry", "Apple", "banana"]


def test_filters_combine(client, admin, customer):
    shirts = category(client, admin, "Shirts")
    create_product(client, admin, name="Cheap shirt", price="10", stock={"S": 1, "M": 0}, category_id=shirts)
    create_product(client, admin, name="Dear shirt", price="50", stock={"M": 2}, category_id=shirts)
    create_product(client, admin, name="Sold out shirt", price="20", stock={"S": 0}, category_id=shirts)
    create_product(client, admin, name="Cheap hat", price="10", stock={"S": 3})

    assert names(client, customer, f"?category={shirts}") == ["Sold out shirt", "Dear shirt", "Cheap shirt"]
    assert names(client, customer, "?min_price=15&max_price=50") == ["Sold out shirt", "Dear shirt"]
    assert names(client, customer, "?size=M") == ["Dear shirt"]
    assert names(client, customer, "?in_stock=1") == ["Cheap hat", "Dear shirt", "Cheap shirt"]
    assert names(client, customer, f"?category={shirts}&in_stock=1&max_price=10&q=cheap") == ["Cheap shirt"]


def test_invalid_price_range_is_ignored_with_a_notice(client, admin, customer):
    create_product(client, admin, name="A", price="10")
    create_product(client, admin, name="B", price="30")
    reversed_range = client.get("/api/products?min_price=40&max_price=20", headers=customer).json()
    assert reversed_range["total"] == 2
    assert "higher than the maximum" in reversed_range["notices"][0]
    bad = client.get("/api/products?min_price=-1", headers=customer).json()
    assert bad["total"] == 2 and "not applied" in bad["notices"][0]
    assert client.get("/api/products?min_price=1.234", headers=customer).json()["notices"]


def test_search_runs_in_sql_and_loads_only_one_page(client, admin):
    for index in range(15):
        create_product(client, admin, name=f"P{index:02d}")
    conn = connect(client.app.state.settings.db_path)
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    result = search_products(conn, CatalogueQuery(page=2, page_size=5))
    conn.close()
    assert [p["name"] for p in result["products"]] == ["P09", "P08", "P07", "P06", "P05"]
    assert any("LIMIT" in s for s in statements)


# --- Migration of databases created before rev. 5 ---------------------------


def test_old_database_is_migrated(tmp_path):
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.executescript(
        """CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
               price_cents INTEGER NOT NULL, image TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
           INSERT INTO products (name, price_cents, image, created_at, updated_at)
               VALUES ('Old tee', 100, 'old.png', '2026-01-01', '2026-01-01');"""
    )
    old.commit()
    old.close()

    conn = connect(db_path)
    init_schema(conn)
    init_schema(conn)  # idempotent
    result = search_products(conn, CatalogueQuery())
    conn.close()
    product = result["products"][0]
    assert (product["description"], product["category"]) == ("", None)
    assert [i["file"] for i in product["images"]] == ["old.png"]


def test_demo_data_has_categories_descriptions_and_galleries(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(db_path=tmp_path / "db", upload_dir=tmp_path / "up", frontend_dir=PROJECT_ROOT / "frontend")
    with TestClient(create_app(settings)):
        pass
    conn = connect(settings.db_path)
    result = search_products(conn, CatalogueQuery(page_size=100))
    conn.close()
    assert result["total"] == 16
    assert all(p["category"] and p["description"] and len(p["images"]) == 2 for p in result["products"])


def test_editing_keeps_other_fields(client, admin):
    shirts = category(client, admin, "Shirts")
    product = create_product(client, admin, description="Keep me", category_id=shirts).json()
    updated = update_product(client, admin, product["id"], price="3").json()
    assert (updated["description"], updated["category"]["id"]) == ("Keep me", shirts)


def test_duplicate_category_message_names_the_existing_one(client, admin):
    category(client, admin, "T-Shirts")
    response = client.post("/api/admin/categories", json={"name": "t-shirts"}, headers=admin)
    assert response.json()["detail"] == 'A category named "T-Shirts" already exists.'
