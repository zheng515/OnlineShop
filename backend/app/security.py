"""Password hashing, session tokens and role-based access dependencies."""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status

from .database import get_db

PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_session(conn: sqlite3.Connection, user_id: int, ttl_hours: int) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, (now + timedelta(hours=ttl_hours)).isoformat()),
    )
    conn.commit()
    return token


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_user(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> sqlite3.Row:
    token = _bearer_token(request)
    if token:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.display_name, s.token
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, utcnow().isoformat()),
        ).fetchone()
        if row:
            return row
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired or you are not logged in. Please log in again.",
    )


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can manage products.")
    return user


def require_customer(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    if user["role"] != "customer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only customers can use shopping functions.")
    return user
