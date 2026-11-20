import os
import uuid
from pathlib import Path
from urllib.parse import quote

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.accounts import create_user
from app.config import PROJECT_ROOT, Settings
from app.database import close_pools, connect
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

# Set to a PostgreSQL URL to run the whole suite against PostgreSQL (FR68, FR74), e.g.
# SHOP_TEST_DATABASE_URL=postgresql://shop:shop@localhost:5432/shop_test
POSTGRES_URL = os.environ.get("SHOP_TEST_DATABASE_URL", "")
sqlite_only = pytest.mark.skipif(bool(POSTGRES_URL), reason="checks SQLite-specific behaviour")


@pytest.fixture
def database_url(tmp_path: Path):
    """A fresh, empty database for one test: a SQLite file, or its own PostgreSQL schema."""
    if not POSTGRES_URL:
        yield f"sqlite:///{tmp_path / 'shop.db'}"
        return
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
    separator = "&" if "?" in POSTGRES_URL else "?"
    yield f"{POSTGRES_URL}{separator}options={quote(f'-csearch_path={schema}')}"
    close_pools()
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def client(tmp_path: Path, database_url: str):
    settings = Settings(
        db_path=tmp_path / "shop.db",
        database_url=database_url,
        upload_dir=tmp_path / "uploads",
        frontend_dir=PROJECT_ROOT / "frontend",
        seed_demo_data=False,
    )
    with TestClient(create_app(settings)) as test_client:
        conn = connect(settings.database_url)
        for username, password, role in TEST_USERS:
            create_user(conn, username, password, role, username.title())
        setup_test_delivery(conn)
        conn.close()
        yield test_client


def db(client: TestClient):
    """A direct connection to the test app's database."""
    return connect(client.app.state.settings.database_url)


TEST_DELIVERY_METHOD = "Test delivery"


def setup_test_delivery(conn) -> None:
    """Give each test customer an address and add a free delivery method, which is then the
    cheapest, so order tests can reason about item prices alone. Delivery addresses, methods
    and fees themselves are tested in test_delivery.py (FR100-FR109)."""
    now = "2026-01-01T00:00:00+00:00"
    for (user_id,) in conn.execute("SELECT id FROM users WHERE role = 'customer'").fetchall():
        conn.execute(
            """INSERT INTO addresses (user_id, full_name, phone, line1, line2, city, region, postal_code, country,
                                      is_default, created_at, updated_at)
               VALUES (?, 'Test Customer', '555 0100 00', '1 Test Street', '', 'Testville', 'TS', '12345',
                       'United States', ?, ?, ?)""",
            (user_id, True, now, now),
        )
    conn.execute(
        """INSERT INTO shipping_methods (name, description, fee_cents, free_over_cents, active, created_at, updated_at)
           VALUES (?, '', 0, NULL, ?, ?, ?)""",
        (TEST_DELIVERY_METHOD, True, now, now),
    )
    conn.commit()


def delivery_choice(client: TestClient, headers: dict) -> dict:
    """The customer's first address and the free test delivery method, as sent when placing an order."""
    book = client.get("/api/account/addresses", headers=headers)
    # Administrators have no address book (FR100); any id will do for checking they are refused.
    address_id = book.json()["addresses"][0]["id"] if book.status_code == 200 else 1
    conn = db(client)
    try:
        method_id = conn.execute("SELECT id FROM shipping_methods WHERE name = ?", (TEST_DELIVERY_METHOD,)).fetchone()[0]
    finally:
        conn.close()
    return {"address_id": address_id, "shipping_method_id": method_id}


def direct_delivery_choice(conn, username: str):
    """The same choice for calling order_service.place_order directly."""
    from app.config import Settings
    from app.order_service import DeliveryChoice

    address_id = conn.execute(
        "SELECT a.id FROM addresses a JOIN users u ON u.id = a.user_id WHERE u.username = ?", (username,)
    ).fetchone()[0]
    method_id = conn.execute("SELECT id FROM shipping_methods WHERE name = ?", (TEST_DELIVERY_METHOD,)).fetchone()[0]
    return DeliveryChoice(address_id, method_id, Settings.delivery_countries)


TEST_USERS = [("admin", "admin123", "admin"), ("alice", "alice123", "customer"), ("bob", "bob12345", "customer")]


def login(client: TestClient, username: str, password: str, role: str) -> dict:
    """Log in and return headers that carry that user's session cookie and CSRF token.

    The client's own cookie jar is cleared, so several users can be used side by side.
    """
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    assert response.status_code == 200, response.text
    session, csrf = response.cookies["shop_session"], response.cookies["shop_csrf"]
    client.cookies.clear()
    return {"Cookie": f"shop_session={session}; shop_csrf={csrf}", "X-CSRF-Token": csrf}


@pytest.fixture
def admin(client):
    return login(client, "admin", "admin123", "admin")


@pytest.fixture
def customer(client):
    return login(client, "alice", "alice123", "customer")


def upload_image(client, admin, data=PNG_BYTES, filename="tee.png"):
    return client.post("/api/admin/images", files={"image": (filename, data, "image/png")}, headers=admin)


def create_product(client, admin, name="Test Tee", price="10.00", stock=None, image=PNG_BYTES, filename="tee.png", **extra):
    """Create a product, uploading one image first. Returns the failed upload response if the upload fails."""
    stock = {"S": 5, "M": 2} if stock is None else stock
    image_ids = []
    if image is not None:
        uploaded = upload_image(client, admin, image, filename)
        if uploaded.status_code != 201:
            return uploaded
        image_ids = [uploaded.json()["id"]]
    body = {"name": name, "price": price, "stock": stock, "image_ids": image_ids, **extra}
    return client.post("/api/admin/products", json=body, headers=admin)


def update_product(client, admin, product_id, **changes):
    """PUT the product's current data with `changes` applied."""
    current = client.get(f"/api/admin/products/{product_id}", headers=admin).json()
    body = {
        "name": current["name"],
        "price": str(current["price"]),
        "description": current["description"],
        "category_id": current["category"]["id"] if current["category"] else None,
        "stock": {s["size"]: s["stock"] for s in current["sizes"]},
        "image_ids": [image["id"] for image in current["images"]],
        **changes,
    }
    return client.put(f"/api/admin/products/{product_id}", json=body, headers=admin)


def complete_mock_payment(client: TestClient, payment_url: str, outcome: str = "succeed"):
    """Choose an outcome on the mock provider's page, as the customer would (FR84)."""
    reference = payment_url.split("session=", 1)[1]
    return client.post(f"/api/mock-provider/sessions/{reference}/complete", json={"outcome": outcome})
