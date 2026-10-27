import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, Settings
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
        yield test_client


def login(client: TestClient, username: str, password: str, role: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin", "admin123", "admin")


@pytest.fixture
def customer(client):
    return login(client, "alice", "alice123", "customer")


def create_product(client, admin, name="Test Tee", price="10.00", stock=None, image=PNG_BYTES, filename="tee.png"):
    stock = {"S": 5, "M": 2} if stock is None else stock
    files = {"image": (filename, image, "image/png")} if image is not None else None
    return client.post(
        "/api/admin/products",
        data={"name": name, "price": price, "stock": json.dumps(stock)},
        files=files,
        headers=admin,
    )
