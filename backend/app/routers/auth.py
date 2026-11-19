"""Login, logout and current-user endpoints (FR1-FR6, FR51, FR53, FR59)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..database import Database, Row, get_db
from ..errors import ValidationProblem
from ..login_throttle import record_attempt, refusal_message, retry_after_seconds
from ..security import (
    clear_session_cookies,
    client_ip,
    create_session,
    end_session,
    get_current_user,
    security_log,
    set_session_cookies,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

ROLE_LABELS = {"admin": "Administrator", "customer": "Customer"}
HOME_PAGES = {"admin": "/admin.html", "customer": "/shop.html"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "customer"]


def _user_payload(user: Row) -> dict:
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "home": HOME_PAGES[user["role"]],
    }


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, conn: Database = Depends(get_db)):
    settings = request.app.state.settings
    # Username or email address; both are matched regardless of letter case (FR2, FR89), and the
    # throttle counts them the same way so changing the case gives no extra attempts (FR53).
    identifier = body.username.strip()
    login_key = identifier.lower()
    ip = client_ip(request)

    wait = retry_after_seconds(conn, login_key, ip)
    if wait is not None:
        # Refused attempts are not recorded, so they do not extend the wait (FR53).
        security_log.warning("login_throttled user=%s ip=%s retry_after=%s", login_key, ip, wait)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, refusal_message(wait), headers={"Retry-After": str(wait)})

    if "@" in identifier:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (login_key,)).fetchone()
    else:
        user = conn.execute("SELECT * FROM users WHERE lower(username) = ?", (login_key,)).fetchone()
    # A valid account used on the wrong login option is treated as invalid
    # credentials for that option.
    if user is None or not verify_password(body.password, user["password_hash"]) or user["role"] != body.role:
        record_attempt(conn, login_key, ip, success=False)
        security_log.warning("login_failed user=%s ip=%s role=%s", login_key, ip, body.role)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid username or password for {ROLE_LABELS[body.role]} Login.",
        )

    record_attempt(conn, login_key, ip, success=True)
    if user["email"] and not user["email_verified_at"]:
        # The password was right, but the address must be confirmed first (FR2, FR90).
        security_log.info("login_unverified user=%s ip=%s", user["username"], ip)
        raise ValidationProblem(
            ["Please confirm your email address first. We sent you a link when you registered."],
            status.HTTP_403_FORBIDDEN,
            extra={"code": "email_unverified", "email": user["email"]},
        )
    token, csrf = create_session(conn, user["id"], settings.token_ttl_hours)
    set_session_cookies(response, settings, token, csrf)
    security_log.info("login_succeeded user=%s ip=%s", user["username"], ip)
    return {"user": _user_payload(user)}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: Row = Depends(get_current_user),
    conn: Database = Depends(get_db),
):
    end_session(conn, user["token_hash"])
    clear_session_cookies(response, request.app.state.settings)
    security_log.info("logout user=%s ip=%s", user["username"], client_ip(request))
    return {"message": "You have been logged out."}


@router.get("/me")
def me(user: Row = Depends(get_current_user)):
    return _user_payload(user)
