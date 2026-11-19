from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.accounts import create_user
from app.config import PROJECT_ROOT, Settings
from app.database import connect
from app.main import create_app

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "shop.db",
        upload_dir=tmp_path / "uploads",
        frontend_dir=PROJECT_ROOT / "frontend",
        seed_demo_data=False,
    )
    with TestClient(create_app(settings)) as test_client:
        conn = connect(settings.db_path)
        for username, password, role in TEST_USERS:
            create_user(conn, username, password, role, username.title())
        conn.close()
        yield test_client


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
