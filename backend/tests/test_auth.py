from conftest import login


def test_admin_and_customer_login_redirect_to_role_home(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123", "role": "admin"})
    assert response.json()["user"]["home"] == "/admin.html"
    response = client.post("/api/auth/login", json={"username": "alice", "password": "alice123", "role": "customer"})
    assert response.json()["user"]["home"] == "/shop.html"


def test_invalid_credentials_show_error(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong", "role": "admin"})
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_account_cannot_use_other_role_login(client):
    response = client.post("/api/auth/login", json={"username": "alice", "password": "alice123", "role": "admin"})
    assert response.status_code == 401


def test_role_based_access_control(client, admin, customer):
    assert client.get("/api/admin/products", headers=customer).status_code == 403
    assert client.get("/api/cart", headers=admin).status_code == 403
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/admin/products", headers=admin).status_code == 200
    assert client.get("/api/cart", headers=customer).status_code == 200


def test_logout_invalidates_session(client):
    headers = login(client, "bob", "bob123", "customer")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_no_self_registration_endpoint(client):
    response = client.post("/api/auth/register", json={"username": "x", "password": "y"})
    assert response.status_code in (404, 405)
