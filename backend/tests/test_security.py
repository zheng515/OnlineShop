import logging
from datetime import timedelta

import pytest
from conftest import login

from app import login_throttle
from app.accounts import AccountError, create_user, password_problems, set_password
from app.database import connect
from app.security import utcnow


def attempt(client, username="alice", password="wrong", role="customer"):
    response = client.post("/api/auth/login", json={"username": username, "password": password, "role": role})
    client.cookies.clear()
    return response


def db(client):
    return connect(client.app.state.settings.db_path)


# --- FR51 session cookies -------------------------------------------------


def test_session_cookie_is_httponly_lax_and_not_in_body(client):
    response = client.post("/api/auth/login", json={"username": "alice", "password": "alice123", "role": "customer"})
    assert response.status_code == 200
    assert "token" not in response.json()
    cookies = {c.split("=", 1)[0]: c.lower() for c in response.headers.get_list("set-cookie")}
    assert "httponly" in cookies["shop_session"] and "samesite=lax" in cookies["shop_session"]
    assert "httponly" not in cookies["shop_csrf"]
    assert "secure" not in cookies["shop_session"]  # plain HTTP in tests


def test_secure_cookie_and_hsts_when_https(client):
    client.app.state.settings.cookie_secure = True
    response = client.post("/api/auth/login", json={"username": "alice", "password": "alice123", "role": "customer"})
    assert all("secure" in c.lower() for c in response.headers.get_list("set-cookie"))
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_only_a_hash_of_the_session_is_stored(client):
    headers = login(client, "alice", "alice123", "customer")
    token = headers["Cookie"].split("shop_session=")[1].split(";")[0]
    conn = db(client)
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
    conn.close()
    assert stored and token not in stored


def test_bearer_tokens_are_not_accepted(client):
    headers = login(client, "alice", "alice123", "customer")
    token = headers["Cookie"].split("shop_session=")[1].split(";")[0]
    assert client.get("/api/cart", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_each_login_gets_a_new_session(client):
    first = login(client, "alice", "alice123", "customer")
    second = login(client, "alice", "alice123", "customer")
    assert first["Cookie"] != second["Cookie"]


def test_logout_clears_cookies(client):
    headers = login(client, "alice", "alice123", "customer")
    response = client.post("/api/auth/logout", headers=headers)
    assert all('=""' in c or "max-age=0" in c.lower() for c in response.headers.get_list("set-cookie"))


# --- FR52 CSRF and origin checks -----------------------------------------


def test_state_changes_need_the_csrf_token(client, customer, caplog):
    without = {"Cookie": customer["Cookie"]}
    with caplog.at_level(logging.WARNING, logger="onlineshop.security"):
        response = client.post("/api/auth/logout", headers=without)
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert "csrf_rejected user=alice" in caplog.text

    wrong = {**customer, "X-CSRF-Token": "not-the-token"}
    assert client.delete("/api/cart/items/1", headers=wrong).status_code == 403
    # Reads do not need the token.
    assert client.get("/api/cart", headers=without).status_code == 200


def test_cross_site_requests_are_rejected(client, customer):
    evil = {**customer, "Origin": "https://evil.example"}
    response = client.post("/api/auth/logout", headers=evil)
    assert response.status_code == 403 and response.json()["code"] == "origin_rejected"

    login_csrf = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "alice123", "role": "customer"},
        headers={"Referer": "https://evil.example/page"},
    )
    assert login_csrf.status_code == 403

    same_site = {**customer, "Origin": "http://testserver"}
    assert client.get("/api/auth/me", headers=same_site).status_code == 200
    assert client.post("/api/auth/logout", headers=same_site).status_code == 200


# --- FR53 login throttling -----------------------------------------------


def test_username_locked_after_five_failures(client, caplog):
    for _ in range(5):
        assert attempt(client).status_code == 401
    with caplog.at_level(logging.WARNING, logger="onlineshop.security"):
        locked = attempt(client, password="alice123")
    assert locked.status_code == 429
    assert "try again in 15 minutes" in locked.json()["detail"]
    assert 0 < int(locked.headers["retry-after"]) <= 900
    assert "login_throttled user=alice" in caplog.text
    # Other usernames are not affected.
    assert attempt(client, "bob", "bob12345").status_code == 200


def test_lock_is_the_same_for_unknown_usernames(client):
    for _ in range(5):
        attempt(client, "ghost")
        attempt(client, "alice")
    unknown, known = attempt(client, "ghost"), attempt(client, "alice")
    assert unknown.status_code == known.status_code == 429
    assert unknown.json()["detail"] == known.json()["detail"]


def test_lock_expires_and_refused_attempts_do_not_extend_it(client, monkeypatch):
    for _ in range(5):
        attempt(client)
    start = utcnow()
    monkeypatch.setattr(login_throttle, "utcnow", lambda: start + timedelta(minutes=10))
    assert attempt(client, password="alice123").status_code == 429
    monkeypatch.setattr(login_throttle, "utcnow", lambda: start + timedelta(minutes=15, seconds=5))
    assert attempt(client, password="alice123").status_code == 200


def test_success_resets_the_username_count(client):
    for _ in range(4):
        attempt(client)
    assert attempt(client, password="alice123").status_code == 200
    for _ in range(4):
        assert attempt(client).status_code == 401
    assert attempt(client, password="alice123").status_code == 200


def test_client_address_locked_after_thirty_failures(client):
    for index in range(30):
        attempt(client, f"user{index}")
    assert attempt(client, "bob", "bob12345").status_code == 429


# --- FR54 accounts and passwords -----------------------------------------


@pytest.mark.parametrize(
    "password, problem",
    [("short1", "8 to 128"), ("lettersonly", "letter and one digit"), ("12345678", "letter and one digit"), ("Carol123", "different")],
)
def test_password_policy(password, problem):
    assert any(problem in p for p in password_problems("carol123", password))
    assert password_problems("carol", "goodPass1") == []


def test_account_command_creates_users_and_rejects_bad_input(client):
    conn = db(client)
    create_user(conn, "carol", "goodPass1", "customer", "Carol")
    with pytest.raises(AccountError):
        create_user(conn, "carol", "goodPass1", "customer")
    with pytest.raises(AccountError):
        create_user(conn, "dave", "weak", "customer")
    with pytest.raises(AccountError):
        create_user(conn, "x", "goodPass1", "customer")
    conn.close()
    assert attempt(client, "carol", "goodPass1").status_code == 200


def test_set_password_ends_sessions(client):
    headers = login(client, "alice", "alice123", "customer")
    conn = db(client)
    set_password(conn, "alice", "newPass99")
    conn.close()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert attempt(client, "alice", "newPass99").status_code == 200


def test_account_cli(client, monkeypatch, capsys):
    from app import accounts

    monkeypatch.setenv("SHOP_DB_PATH", str(client.app.state.settings.db_path))
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("cliPass12\n"))
    assert accounts.main(["create", "erin", "--role", "customer", "--password-stdin"]) == 0
    assert accounts.main(["list"]) == 0
    assert "erin" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("short\n"))
    assert accounts.main(["set-password", "erin", "--password-stdin"]) == 1


def test_login_page_shows_no_credentials(client):
    page = client.get("/index.html").text
    for secret in ("admin123", "alice123", "bob12345"):
        assert secret not in page


# --- FR55, FR57, FR58 ------------------------------------------------------


def test_security_headers(client):
    response = client.get("/index.html")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "strict-transport-security" not in response.headers
    assert "content-security-policy" not in client.get("/docs").headers


def test_oversized_requests_are_rejected(client, admin):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
    response = client.post(
        "/api/admin/products",
        data={"name": "Big", "price": "1", "stock": '{"S": 1}'},
        files={"image": ("big.png", big, "image/png")},
        headers=admin,
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_streamed_oversized_body_is_rejected(client, admin):
    # No Content-Length: the limit must be enforced while the body streams in.
    def chunks():
        yield b'--x\r\nContent-Disposition: form-data; name="image"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n'
        for _ in range(7):
            yield b"x" * (1024 * 1024)

    response = client.post("/api/admin/products", content=chunks(), headers={**admin, "Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413


def test_unexpected_errors_are_generic(client, monkeypatch, caplog):
    from fastapi.testclient import TestClient

    from app.routers import shop

    def boom(*args, **kwargs):
        raise RuntimeError("secret database detail")

    monkeypatch.setattr(shop, "list_products", boom)
    headers = login(client, "alice", "alice123", "customer")
    quiet = TestClient(client.app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="onlineshop"):
        response = quiet.get("/api/products", headers=headers)
    assert response.status_code == 500
    assert "secret" not in response.text
    assert "Something went wrong" in response.json()["detail"]
    assert "secret database detail" in caplog.text


# --- FR59 security logging --------------------------------------------------


def test_security_events_are_logged_without_secrets(client, caplog):
    with caplog.at_level(logging.INFO, logger="onlineshop.security"):
        attempt(client, password="wrong-password")
        headers = login(client, "alice", "alice123", "customer")
        client.post("/api/auth/logout", headers=headers)
    text = caplog.text
    assert "login_failed user=alice" in text and "login_succeeded user=alice" in text and "logout user=alice" in text
    token = headers["Cookie"].split("shop_session=")[1].split(";")[0]
    for secret in ("wrong-password", "alice123", token, headers["X-CSRF-Token"]):
        assert secret not in text
