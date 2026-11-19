"""Database access for SQLite and PostgreSQL (FR68).

Application code talks to a `Database`, which wraps a DB-API connection of either kind and
offers one dialect of SQL: `?` placeholders, `RETURNING id` for inserts, and the functions
`casefold(text)` and `instr(text, text)` (SQLite has `instr` built in and gets `casefold` from
Python; PostgreSQL gets both from migration 0001). Rows support both `row["name"]` and `row[0]`.

The schema itself is created by migrations (app/migrations.py).
"""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import Request
from psycopg_pool import ConnectionPool

POOL_MAX_SIZE = 10


class Row:
    """A result row readable by column name or position, like sqlite3.Row."""

    __slots__ = ("_names", "_values")

    def __init__(self, names: Sequence[str], values: Sequence[Any]):
        self._names = names
        self._values = values

    def __getitem__(self, key: int | slice | str) -> Any:
        if isinstance(key, (int, slice)):
            return tuple(self._values[key]) if isinstance(key, slice) else self._values[key]
        try:
            return self._values[self._names.index(key)]
        except ValueError:
            raise IndexError(f"No column named {key!r}") from None

    def keys(self) -> list[str]:
        return list(self._names)

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._names, self._values, strict=True))!r})"


def _pg_row_factory(cursor: psycopg.Cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(names, values)


def _casefold(value: str | None) -> str | None:
    return None if value is None else value.casefold()


def sqlite_path(url: str) -> Path:
    return Path(url.removeprefix("sqlite:///"))


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()


def _pool(url: str) -> ConnectionPool:
    with _pools_lock:
        pool = _pools.get(url)
        if pool is None:
            pool = ConnectionPool(
                url, min_size=1, max_size=POOL_MAX_SIZE, kwargs={"row_factory": _pg_row_factory}, open=True
            )
            _pools[url] = pool
        return pool


def close_pools() -> None:
    with _pools_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


class Database:
    """One database connection. Use `connect()` to get one and `close()` when done."""

    def __init__(self, raw: Any, dialect: str, pool: ConnectionPool | None = None):
        self.raw = raw
        self.dialect = dialect
        self._pool = pool
        self.Error = sqlite3.Error if dialect == "sqlite" else psycopg.Error
        self.IntegrityError = sqlite3.IntegrityError if dialect == "sqlite" else psycopg.IntegrityError

    def _sql(self, sql: str) -> str:
        if self.dialect == "sqlite":
            return sql
        # psycopg uses %s placeholders, so literal percent signs must be doubled.
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql: str, params: Sequence[Any] = ()):
        return self.raw.execute(self._sql(sql), tuple(params))

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> None:
        if self.dialect == "sqlite":
            self.raw.executemany(sql, seq)
        else:
            with self.raw.cursor() as cursor:
                cursor.executemany(self._sql(sql), [tuple(params) for params in seq])

    def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run an INSERT and return the new row's id."""
        return self.execute(f"{sql} RETURNING id", params).fetchone()[0]

    @property
    def in_transaction(self) -> bool:
        if self.dialect == "sqlite":
            return self.raw.in_transaction
        return self.raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        if self._pool is not None:
            if self.in_transaction:
                self.raw.rollback()
            self._pool.putconn(self.raw)
        else:
            self.raw.close()

    def set_trace_callback(self, callback) -> None:
        """SQLite only: call `callback(sql)` for each statement (used by tests)."""
        self.raw.set_trace_callback(callback)


def connect(url: str | Path) -> Database:
    """Connect to `sqlite:///path`, a plain SQLite file path, or a `postgresql://` URL."""
    url = str(url)
    if not url.startswith(("sqlite:", "postgresql:", "postgres:")):
        url = f"sqlite:///{url}"
    if is_sqlite(url):
        raw = sqlite3.connect(sqlite_path(url), check_same_thread=False, timeout=10)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        # SQLite's own LIKE/lower() only fold ASCII; this folds all letters (FR16).
        raw.create_function("casefold", 1, _casefold, deterministic=True)
        return Database(raw, "sqlite")
    pool = _pool(url)
    return Database(pool.getconn(), "postgresql", pool)


@contextmanager
def write_transaction(conn: Database) -> Iterator[None]:
    """Run a block as one atomic write.

    On SQLite, BEGIN IMMEDIATE takes the write lock up front, so stock read inside the block
    cannot change before it commits. On PostgreSQL the block is one transaction; stock
    changes rely on guarded updates (`... WHERE stock >= ?`) and row locks instead.
    """
    if conn.in_transaction:
        conn.commit()
    if conn.dialect == "sqlite":
        conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def get_db(request: Request) -> Iterator[Database]:
    conn = connect(request.app.state.settings.database_url)
    try:
        yield conn
    finally:
        conn.close()
