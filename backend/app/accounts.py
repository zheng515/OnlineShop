"""Account administration command (FR3, FR54). Accounts cannot be managed from the web interface.

Run from the backend directory:

    python -m app.accounts create USERNAME --role customer [--name "Display Name"]
    python -m app.accounts set-password USERNAME
    python -m app.accounts list

The password is prompted for; pass --password-stdin to read it from standard input instead.
"""

import argparse
import getpass
import logging
import re
import sqlite3
import sys

from .config import load_settings
from .database import connect, init_schema
from .security import end_all_sessions, hash_password

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

security_log = logging.getLogger("onlineshop.security")


class AccountError(Exception):
    pass


def password_problems(username: str, password: str) -> list[str]:
    problems = []
    if not 8 <= len(password) <= 128:
        problems.append("Password must be 8 to 128 characters long.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("Password must contain at least one letter and one digit.")
    if password.casefold() == username.casefold():
        problems.append("Password must be different from the username.")
    return problems


def _check_password(username: str, password: str) -> None:
    problems = password_problems(username, password)
    if problems:
        raise AccountError(" ".join(problems))


def create_user(conn: sqlite3.Connection, username: str, password: str, role: str, display_name: str = "") -> int:
    if not USERNAME_PATTERN.match(username):
        raise AccountError("Username must be 3-32 characters: letters, digits, '.', '_' or '-'.")
    if role not in ("admin", "customer"):
        raise AccountError("Role must be 'admin' or 'customer'.")
    _check_password(username, password)
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise AccountError(f"User '{username}' already exists.")
    user_id = conn.execute(
        "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, display_name.strip() or username),
    ).lastrowid
    conn.commit()
    return user_id


def set_password(conn: sqlite3.Connection, username: str, password: str) -> None:
    user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        raise AccountError(f"User '{username}' does not exist.")
    _check_password(username, password)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user["id"]))
    conn.commit()
    # Anyone still logged in with the old password is logged out (FR54).
    end_all_sessions(conn, user["id"])
    security_log.info("password_changed user=%s", username)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise AccountError("The passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.accounts", description="Manage OnlineShop accounts.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create an account")
    create.add_argument("username")
    create.add_argument("--role", choices=["admin", "customer"], required=True)
    create.add_argument("--name", default="", help="display name (defaults to the username)")
    create.add_argument("--password-stdin", action="store_true")
    change = commands.add_parser("set-password", help="set a new password and end the account's sessions")
    change.add_argument("username")
    change.add_argument("--password-stdin", action="store_true")
    commands.add_parser("list", help="list accounts")
    args = parser.parse_args(argv)

    settings = load_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    try:
        init_schema(conn)
        if args.command == "list":
            for row in conn.execute("SELECT username, role, display_name FROM users ORDER BY role, username"):
                print(f"{row['username']:<20} {row['role']:<9} {row['display_name']}")
        elif args.command == "create":
            create_user(conn, args.username, _read_password(args.password_stdin), args.role, args.name)
            print(f"Created {args.role} account '{args.username}'.")
        else:
            set_password(conn, args.username, _read_password(args.password_stdin))
            print(f"Password updated for '{args.username}'. Existing sessions have been ended.")
    except AccountError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
