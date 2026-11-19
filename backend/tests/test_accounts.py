"""Registration, email confirmation, password reset, account page, abuse limits (FR88-FR94, FR98)."""

import logging
import re
from datetime import timedelta

import pytest

from app import account_service, rate_limits
from app.security import utcnow

from conftest import db, login

GOOD = {"username": "carol", "email": "Carol@Example.com", "display_name": "Carol", "password": "goodPass1",
        "password_confirm": "goodPass1"}


def register(client, **changes):
    return client.post("/api/account/register", json={**GOOD, **changes})


def emails(client, to=None, kind=None):
    conn = db(client)
    rows = [dict(zip(r.keys(), r, strict=True)) for r in conn.execute("SELECT * FROM email_outbox ORDER BY id")]
    conn.close()
    return [r for r in rows if (to is None or r["to_address"] == to) and (kind is None or r["kind"] == kind)]


def token_from(email_row, page):
    match = re.search(rf"/{page}\?token=([\w-]+)", email_row["body"])
    assert match, email_row["body"]
    return match.group(1)


def attempt_login(client, identifier, password, role="customer"):
    response = client.post("/api/auth/login", json={"username": identifier, "password": password, "role": role})
    client.cookies.clear()
    return response


def confirm(client, address="carol@example.com"):
    token = token_from(emails(client, address, "verify_email")[-1], "verify-email.html")
    return client.post("/api/account/verify-email", json={"token": token})


# --- FR88 visitors -----------------------------------------------------------


def test_visitors_can_browse_but_not_shop(client):
    assert client.get("/api/products").status_code == 200
    assert client.get("/api/categories").status_code == 200
    assert client.post("/api/cart/items", json={"product_id": 1, "size": "S", "quantity": 1}).status_code == 401
    assert client.get("/api/account").status_code == 401


# --- FR89 registration ------------------------------------------------------------


def test_registration_creates_an_unconfirmed_customer(client, caplog):
    with caplog.at_level(logging.INFO, logger="onlineshop.security"):
        response = register(client)
    assert response.status_code == 201
    assert "confirm your address" in response.json()["message"]
    assert "registered user=carol email=carol@example.com" in caplog.text

    conn = db(client)
    user = conn.execute("SELECT role, email, email_verified_at FROM users WHERE username = 'carol'").fetchone()
    conn.close()
    assert user[:] == ("customer", "carol@example.com", None)
    [sent] = emails(client, "carol@example.com")
    assert sent["kind"] == "verify_email" and "Hello Carol" in sent["body"]
    assert "{{SHOP_URL}}/verify-email.html?token=" in sent["body"]
    assert "goodPass1" not in sent["body"]


def test_registration_reports_every_problem(client):
    response = register(client, username="x", email="nope", display_name=" ", password="short", password_confirm="other")
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any("Username must be" in e for e in errors)
    assert "Please enter a valid email address." in errors
    assert "Display name is required." in errors
    assert "The two passwords do not match." in errors
    assert any("8 to 128" in e for e in errors)


def test_taken_username_is_reported_regardless_of_case(client):
    response = register(client, username="ALICE", email="new@example.com")
    assert response.json()["detail"] == "This username is already taken. Please choose another one."


def test_existing_address_looks_successful_and_warns_the_owner(client):
    register(client)
    confirm(client)
    again = register(client, username="carol2")
    assert again.status_code == 201 and again.json() == register(client, username="carol3").json()
    conn = db(client)
    assert conn.execute("SELECT COUNT(*) FROM users WHERE email = 'carol@example.com'").fetchone()[0] == 1
    conn.close()
    assert emails(client, "carol@example.com", "registration_attempt")


def test_registration_cannot_create_administrators(client):
    response = client.post("/api/account/register", json={**GOOD, "role": "admin"})
    assert response.status_code == 201
    conn = db(client)
    assert conn.execute("SELECT role FROM users WHERE username = 'carol'").fetchone()[0] == "customer"
    conn.close()


# --- FR90 confirmation and login -----------------------------------------------------


def test_unconfirmed_accounts_cannot_log_in_until_confirmed(client):
    register(client)
    refused = attempt_login(client, "carol", "goodPass1")
    assert refused.status_code == 403
    assert refused.json()["code"] == "email_unverified"
    assert "shop_session" not in refused.cookies

    assert confirm(client).json()["message"] == "Your email address is confirmed. You can now log in."
    assert attempt_login(client, "carol", "goodPass1").status_code == 200
    # Usernames and email addresses both work, ignoring letter case (FR2).
    assert attempt_login(client, "CAROL@example.COM", "goodPass1").status_code == 200
    assert attempt_login(client, "Carol", "goodPass1").status_code == 200


def test_confirmation_links_work_once(client):
    register(client)
    token = token_from(emails(client, kind="verify_email")[-1], "verify-email.html")
    assert client.post("/api/account/verify-email", json={"token": token}).status_code == 200
    again = client.post("/api/account/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["code"] == "invalid_token"
    assert client.post("/api/account/verify-email", json={"token": "made-up"}).json()["code"] == "invalid_token"


def test_expired_confirmation_link(client, monkeypatch):
    register(client)
    later = utcnow() + timedelta(hours=25)
    monkeypatch.setattr(account_service, "utcnow", lambda: later)
    assert confirm(client).status_code == 400


def test_resending_confirmation_replaces_the_old_link(client):
    register(client)
    first = token_from(emails(client, kind="verify_email")[-1], "verify-email.html")
    answer = client.post("/api/account/resend-verification", json={"email": "carol@example.com"})
    unknown = client.post("/api/account/resend-verification", json={"email": "nobody@example.com"})
    assert answer.json() == unknown.json()  # reveals nothing (FR90)
    assert len(emails(client, kind="verify_email")) == 2
    assert client.post("/api/account/verify-email", json={"token": first}).status_code == 400
    assert confirm(client).status_code == 200


# --- FR91 password reset ---------------------------------------------------------------


def test_password_reset(client):
    customer = login(client, "alice", "alice123", "customer")
    conn = db(client)
    conn.execute("UPDATE users SET email = 'alice@example.com', email_verified_at = 'x' WHERE username = 'alice'")
    conn.commit()
    conn.close()

    answer = client.post("/api/account/forgot-password", json={"email": "ALICE@example.com"})
    unknown = client.post("/api/account/forgot-password", json={"email": "nobody@example.com"})
    assert answer.json() == unknown.json()
    token = token_from(emails(client, "alice@example.com", "reset_password")[-1], "reset-password.html")

    weak = client.post("/api/account/reset-password", json={"token": token, "password": "weak", "password_confirm": "weak"})
    assert weak.status_code == 422
    new_password = {"token": token, "password": "newPass77", "password_confirm": "newPass77"}
    done = client.post("/api/account/reset-password", json=new_password)
    assert done.status_code == 200, done.text
    assert client.get("/api/auth/me", headers=customer).status_code == 401  # all sessions ended
    assert attempt_login(client, "alice", "newPass77").status_code == 200
    assert emails(client, "alice@example.com", "password_changed")
    other_password = {**new_password, "password": "otherPass8", "password_confirm": "otherPass8"}
    reused = client.post("/api/account/reset-password", json=other_password)
    assert reused.json()["code"] == "invalid_token"


def test_reset_links_expire_after_an_hour_and_confirm_the_address(client, monkeypatch):
    register(client)
    client.post("/api/account/forgot-password", json={"email": "carol@example.com"})
    token = token_from(emails(client, kind="reset_password")[-1], "reset-password.html")
    later = utcnow() + timedelta(minutes=61)
    monkeypatch.setattr(account_service, "utcnow", lambda: later)
    body = {"token": token, "password": "newPass77", "password_confirm": "newPass77"}
    assert client.post("/api/account/reset-password", json=body).status_code == 400

    monkeypatch.undo()
    client.post("/api/account/forgot-password", json={"email": "carol@example.com"})
    body["token"] = token_from(emails(client, kind="reset_password")[-1], "reset-password.html")
    assert client.post("/api/account/reset-password", json=body).status_code == 200
    # The reset link proved the address, so the account can log in (FR91).
    assert attempt_login(client, "carol", "newPass77").status_code == 200


# --- FR92 account page ---------------------------------------------------------------


def test_account_page_display_name_and_password(client):
    register(client)
    confirm(client)
    headers = login(client, "carol", "goodPass1", "customer")
    other = login(client, "carol", "goodPass1", "customer")
    assert client.get("/api/account", headers=headers).json() == {
        "username": "carol", "email": "carol@example.com", "display_name": "Carol", "email_verified": True, "role": "customer",
    }
    renamed = client.patch("/api/account", json={"display_name": "  Caroline "}, headers=headers).json()
    assert renamed["display_name"] == "Caroline"
    assert client.patch("/api/account", json={"display_name": ""}, headers=headers).status_code == 422

    wrong = client.post("/api/account/password", json={"current_password": "nope", "new_password": "newPass77",
                                                       "new_password_confirm": "newPass77"}, headers=headers)
    assert wrong.json()["detail"] == "The current password is not correct."
    changed = client.post("/api/account/password", json={"current_password": "goodPass1", "new_password": "newPass77",
                                                         "new_password_confirm": "newPass77"}, headers=headers)
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 200  # this session stays
    assert client.get("/api/auth/me", headers=other).status_code == 401  # others end
    assert emails(client, "carol@example.com", "password_changed")


# --- FR93 tokens, FR94 limits ---------------------------------------------------------------


def test_only_token_hashes_are_stored(client):
    register(client)
    token = token_from(emails(client, kind="verify_email")[-1], "verify-email.html")
    conn = db(client)
    stored = [row[0] for row in conn.execute("SELECT token_hash FROM user_tokens")]
    conn.close()
    assert stored and token not in stored


def test_registration_is_limited_per_client_address(client, caplog):
    for index in range(10):
        assert register(client, username=f"user{index}", email=f"user{index}@example.com").status_code == 201
    with caplog.at_level(logging.WARNING, logger="onlineshop.security"):
        refused = register(client, username="user10", email="user10@example.com")
    assert refused.status_code == 429
    assert "rate_limited kind=register" in caplog.text


def test_reset_emails_are_limited_per_address_without_revealing_it(client):
    register(client)
    answers = [client.post("/api/account/forgot-password", json={"email": "carol@example.com"}).json() for _ in range(5)]
    assert len({a["message"] for a in answers}) == 1
    assert len(emails(client, "carol@example.com", "reset_password")) == 3


def test_rate_limit_window(client, monkeypatch):
    conn = db(client)
    for _ in range(2):
        assert rate_limits.allow(conn, "test", "k", 2, timedelta(hours=1))
    assert not rate_limits.allow(conn, "test", "k", 2, timedelta(hours=1))
    later = utcnow() + timedelta(minutes=61)
    monkeypatch.setattr(rate_limits, "utcnow", lambda: later)
    assert rate_limits.allow(conn, "test", "k", 2, timedelta(hours=1))
    conn.close()


# --- Account command with email --------------------------------------------------------------


def test_operator_created_accounts_count_as_confirmed(client):
    from app.accounts import AccountError, create_user

    conn = db(client)
    create_user(conn, "dave", "goodPass1", "customer", "Dave", "Dave@Example.com")
    with pytest.raises(AccountError):
        create_user(conn, "dave2", "goodPass1", "customer", "Dave", "dave@example.com")
    conn.close()
    assert attempt_login(client, "dave@example.com", "goodPass1").status_code == 200
