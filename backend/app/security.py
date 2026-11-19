"""Password hashing, cookie sessions, CSRF protection and role-based access (FR5, FR51, FR52, FR59)."""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status

from .config import Settings
from .database import Database, Row, get_db
from .errors import ValidationProblem

PBKDF2_ITERATIONS = 120_000

SESSION_COOKIE = "shop_session"
CSRF_COOKIE = "shop_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

security_log = logging.getLogger("onlineshop.security")


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
    return datetime.now(UTC)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn: Database, user_id: int, ttl_hours: int) -> tuple[str, str]:
    """Create a session. Returns (session token, CSRF token); only the token's hash is stored."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = utcnow()
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)",
        (_token_hash(token), user_id, csrf, (now + timedelta(hours=ttl_hours)).isoformat()),
    )
    conn.commit()
    return token, csrf


def end_session(conn: Database, token_hash: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    conn.commit()


def end_all_sessions(conn: Database, user_id: int) -> None:
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()


def set_session_cookies(response: Response, settings: Settings, token: str, csrf: str) -> None:
    max_age = settings.token_ttl_hours * 3600
    common = {"max_age": max_age, "path": "/", "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    # Readable by page scripts on purpose: they copy it into the CSRF header.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


def clear_session_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=settings.cookie_secure, samesite="lax")


def get_current_user(request: Request, conn: Database = Depends(get_db)) -> Row:
    token = request.cookies.get(SESSION_COOKIE)
    row = None
    if token:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.display_name, s.token_hash, s.csrf_token
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (_token_hash(token), utcnow().isoformat()),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired or you are not logged in. Please log in again.",
        )
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent.encode(), row["csrf_token"].encode()):
            security_log.warning(
                "csrf_rejected user=%s ip=%s path=%s", row["username"], client_ip(request), request.url.path
            )
            raise ValidationProblem(
                ["The security check for this request failed. Please reload the page and try again."],
                status.HTTP_403_FORBIDDEN,
                extra={"code": "csrf_failed"},
            )
    return row


def require_admin(user: Row = Depends(get_current_user)) -> Row:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can manage products.")
    return user


def require_customer(user: Row = Depends(get_current_user)) -> Row:
    if user["role"] != "customer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only customers can use shopping functions.")
    return user
