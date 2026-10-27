"""Login, logout and current-user endpoints (FR1-FR6)."""

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..database import get_db
from ..security import create_session, get_current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

ROLE_LABELS = {"admin": "Administrator", "customer": "Customer"}
HOME_PAGES = {"admin": "/admin.html", "customer": "/shop.html"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "customer"]


def _user_payload(user: sqlite3.Row) -> dict:
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "home": HOME_PAGES[user["role"]],
    }


@router.post("/login")
def login(body: LoginRequest, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    user = conn.execute("SELECT * FROM users WHERE username = ?", (body.username.strip(),)).fetchone()
    # A valid account used on the wrong login option is treated as invalid
    # credentials for that option.
    if user is None or not verify_password(body.password, user["password_hash"]) or user["role"] != body.role:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid username or password for {ROLE_LABELS[body.role]} Login.",
        )
    token = create_session(conn, user["id"], request.app.state.settings.token_ttl_hours)
    return {"token": token, "user": _user_payload(user)}


@router.post("/logout")
def logout(user: sqlite3.Row = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    conn.execute("DELETE FROM sessions WHERE token = ?", (user["token"],))
    conn.commit()
    return {"message": "You have been logged out."}


@router.get("/me")
def me(user: sqlite3.Row = Depends(get_current_user)):
    return _user_payload(user)
