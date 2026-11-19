"""Customer accounts: registration, email confirmation, password reset, account page (FR89-FR94)."""

import hashlib
import re
import secrets
from datetime import timedelta

from fastapi import status

from .accounts import USERNAME_PATTERN, password_problems
from .database import Database, Row, write_transaction
from .email import templates
from .email.outbox import queue_email
from .errors import ValidationProblem
from .rate_limits import allow
from .security import end_all_sessions, hash_password, security_log, utcnow, verify_password

VERIFY_LIFETIME = timedelta(hours=24)
RESET_LIFETIME = timedelta(hours=1)
PER_IP_LIMIT, PER_ADDRESS_LIMIT, LIMIT_WINDOW = 10, 3, timedelta(hours=1)
EMAIL_PATTERN = re.compile(r"^[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+\.[^@\s\x00-\x1f\x7f]+$")
MAX_DISPLAY_NAME = 50
INVALID_LINK = "This link is invalid or has expired. You can ask for a new one."


def normalise_email(value: str) -> str:
    return value.strip().lower()


def email_problems(email: str) -> list[str]:
    if not email:
        return ["Email address is required."]
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        return ["Please enter a valid email address."]
    return []


def display_name_problems(name: str) -> list[str]:
    if not name:
        return ["Display name is required."]
    if len(name) > MAX_DISPLAY_NAME:
        return [f"Display name must be at most {MAX_DISPLAY_NAME} characters."]
    return []


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(conn: Database, user_id: int, purpose: str, lifetime: timedelta) -> str:
    """A new single-use token; earlier unused tokens of the same kind stop working (FR93)."""
    now = utcnow()
    conn.execute(
        "UPDATE user_tokens SET used_at = ? WHERE user_id = ? AND purpose = ? AND used_at IS NULL",
        (now.isoformat(), user_id, purpose),
    )
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO user_tokens (user_id, purpose, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, purpose, _hash(token), (now + lifetime).isoformat(), now.isoformat()),
    )
    return token


def consume_token(conn: Database, token: str, purpose: str) -> int | None:
    """Use a token once. Returns its user id, or None for unknown, expired or used tokens alike."""
    now = utcnow().isoformat()
    row = conn.execute(
        """SELECT id, user_id FROM user_tokens
           WHERE token_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?""",
        (_hash(token or ""), purpose, now),
    ).fetchone()
    if row is None:
        return None
    used = conn.execute(
        "UPDATE user_tokens SET used_at = ? WHERE id = ? AND used_at IS NULL", (now, row["id"])
    ).rowcount
    return row["user_id"] if used == 1 else None


def _within_limits(conn: Database, kind: str, ip: str, address: str | None) -> bool:
    ok = allow(conn, f"{kind}_ip", ip, PER_IP_LIMIT, LIMIT_WINDOW)
    if ok and address:
        ok = allow(conn, f"{kind}_email", address, PER_ADDRESS_LIMIT, LIMIT_WINDOW)
    if not ok:
        security_log.warning("rate_limited kind=%s ip=%s email=%s", kind, ip, address or "-")
    return ok


def _check_password_pair(username: str, password: str, confirm: str) -> list[str]:
    problems = password_problems(username, password)
    if password != confirm:
        problems.append("The two passwords do not match.")
    return problems


# --- Registration and confirmation (FR89, FR90) ---------------------------------------


def register(conn: Database, *, username: str, email: str, display_name: str, password: str,
             password_confirm: str, ip: str) -> None:
    username, email, display_name = username.strip(), normalise_email(email), display_name.strip()
    problems = []
    if not USERNAME_PATTERN.match(username):
        problems.append("Username must be 3-32 characters: letters, digits, '.', '_' or '-'.")
    problems += email_problems(email) + display_name_problems(display_name)
    problems += _check_password_pair(username, password, password_confirm)
    if not problems and conn.execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone():
        problems.append("This username is already taken. Please choose another one.")
    if problems:
        raise ValidationProblem(problems)
    if not _within_limits(conn, "register", ip, None):
        raise ValidationProblem(
            ["Too many registrations from your network. Please try again later."], status.HTTP_429_TOO_MANY_REQUESTS
        )

    password_hash = hash_password(password)  # also when the address is taken, so timing reveals nothing
    if _notify_existing_owner(conn, email, ip):
        return
    try:
        with write_transaction(conn):
            user_id = conn.insert(
                """INSERT INTO users (username, password_hash, role, display_name, email)
                   VALUES (?, ?, 'customer', ?, ?)""",
                (username, password_hash, display_name, email),
            )
            token = issue_token(conn, user_id, "verify_email", VERIFY_LIFETIME)
            subject, body = templates.verify_email(display_name, token)
            queue_email(conn, email, subject, body, "verify_email")
    except conn.IntegrityError:
        # A simultaneous registration took the username or the address first.
        if _notify_existing_owner(conn, email, ip):
            return
        raise ValidationProblem(["This username is already taken. Please choose another one."]) from None
    security_log.info("registered user=%s email=%s ip=%s", username, email, ip)


def _notify_existing_owner(conn: Database, email: str, ip: str) -> bool:
    """If the address has an account, tell its owner and look successful (FR89). Returns True then."""
    existing = conn.execute("SELECT display_name FROM users WHERE email = ?", (email,)).fetchone()
    if existing is None:
        return False
    if allow(conn, "register_email", email, PER_ADDRESS_LIMIT, LIMIT_WINDOW):
        subject, body = templates.registration_attempt(existing["display_name"])
        queue_email(conn, email, subject, body, "registration_attempt")
        conn.commit()
    security_log.info("registration_existing_email email=%s ip=%s", email, ip)
    return True


def verify_email(conn: Database, token: str) -> None:
    with write_transaction(conn):
        user_id = consume_token(conn, token, "verify_email")
        if user_id is None:
            raise ValidationProblem([INVALID_LINK], status.HTTP_400_BAD_REQUEST, extra={"code": "invalid_token"})
        conn.execute(
            "UPDATE users SET email_verified_at = ? WHERE id = ? AND email_verified_at IS NULL",
            (utcnow().isoformat(), user_id),
        )
    security_log.info("email_verified user_id=%s", user_id)


def resend_verification(conn: Database, email: str, ip: str) -> None:
    """Always answered the same way (FR90, FR94)."""
    email = normalise_email(email)
    if email_problems(email) or not _within_limits(conn, "verify", ip, email):
        return
    with write_transaction(conn):
        user = conn.execute(
            "SELECT id, display_name FROM users WHERE email = ? AND email_verified_at IS NULL", (email,)
        ).fetchone()
        if user:
            token = issue_token(conn, user["id"], "verify_email", VERIFY_LIFETIME)
            subject, body = templates.verify_email(user["display_name"], token)
            queue_email(conn, email, subject, body, "verify_email")


# --- Password reset (FR91) -------------------------------------------------------------


def request_password_reset(conn: Database, email: str, ip: str) -> None:
    """Always answered the same way (FR91, FR94)."""
    email = normalise_email(email)
    security_log.info("password_reset_requested email=%s ip=%s", email, ip)
    if email_problems(email) or not _within_limits(conn, "reset", ip, email):
        return
    with write_transaction(conn):
        user = conn.execute("SELECT id, display_name FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = issue_token(conn, user["id"], "reset_password", RESET_LIFETIME)
            subject, body = templates.reset_password(user["display_name"], token)
            queue_email(conn, email, subject, body, "reset_password")


def reset_password(conn: Database, token: str, password: str, password_confirm: str) -> None:
    with write_transaction(conn):
        row = conn.execute(
            """SELECT u.id, u.username FROM user_tokens t JOIN users u ON u.id = t.user_id
               WHERE t.token_hash = ? AND t.purpose = 'reset_password' AND t.used_at IS NULL AND t.expires_at > ?""",
            (_hash(token or ""), utcnow().isoformat()),
        ).fetchone()
        if row is None:
            raise ValidationProblem([INVALID_LINK], status.HTTP_400_BAD_REQUEST, extra={"code": "invalid_token"})
        problems = _check_password_pair(row["username"], password, password_confirm)
        if problems:
            raise ValidationProblem(problems)
        if consume_token(conn, token, "reset_password") is None:
            raise ValidationProblem([INVALID_LINK], status.HTTP_400_BAD_REQUEST, extra={"code": "invalid_token"})
        now = utcnow().isoformat()
        # The link proves the address, so it counts as confirmed (FR91).
        conn.execute(
            "UPDATE users SET password_hash = ?, email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
            (hash_password(password), now, row["id"]),
        )
        conn.execute(
            "UPDATE user_tokens SET used_at = ? WHERE user_id = ? AND purpose = 'reset_password' AND used_at IS NULL",
            (now, row["id"]),
        )
        _queue_password_changed(conn, row["id"])
    end_all_sessions(conn, row["id"])
    security_log.info("password_changed user=%s via=reset", row["username"])


def _queue_password_changed(conn: Database, user_id: int) -> None:
    user = conn.execute("SELECT email, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user["email"]:
        subject, body = templates.password_changed(user["display_name"])
        queue_email(conn, user["email"], subject, body, "password_changed")


# --- Account page (FR92) ---------------------------------------------------------------


def account_view(conn: Database, user: Row) -> dict:
    row = conn.execute(
        "SELECT username, email, display_name, email_verified_at, role FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    return {
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "email_verified": bool(row["email_verified_at"]),
        "role": row["role"],
    }


def update_display_name(conn: Database, user: Row, display_name: str) -> None:
    display_name = display_name.strip()
    problems = display_name_problems(display_name)
    if problems:
        raise ValidationProblem(problems)
    conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user["id"]))
    conn.commit()


def change_password(conn: Database, user: Row, current: str, new: str, confirm: str, ip: str) -> None:
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not verify_password(current, row["password_hash"]):
        security_log.warning("password_change_refused user=%s ip=%s", user["username"], ip)
        raise ValidationProblem(["The current password is not correct."])
    problems = _check_password_pair(user["username"], new, confirm)
    if new == current:
        problems.append("The new password must be different from the current one.")
    if problems:
        raise ValidationProblem(problems)
    with write_transaction(conn):
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
        # Other sessions end; the one in use stays (FR54).
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?", (user["id"], user["token_hash"]))
        _queue_password_changed(conn, user["id"])
    security_log.info("password_changed user=%s via=account ip=%s", user["username"], ip)
