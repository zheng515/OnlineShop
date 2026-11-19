"""Schema migrations (FR69).

    python -m app.migrations upgrade    # bring the database to the current structure
    python -m app.migrations check      # exit 1 if migrations are pending
    python -m app.migrations current    # print the database's revision

The database comes from SHOP_DATABASE_URL (or SHOP_DB_PATH for SQLite), like the server.
"""

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: local development only, a single process
    fcntl = None

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

from .config import BACKEND_DIR, Settings, load_settings
from .database import is_sqlite, sqlite_path
from .legacy_schema import upgrade_to_rev5

# Arbitrary constant identifying the migration lock (pg_advisory_xact_lock).
MIGRATION_LOCK_KEY = 4_812_009_271
LEGACY_REVISION = "0001"


class SchemaOutOfDate(RuntimeError):
    pass


def sqlalchemy_url(database_url: str) -> str:
    """Our URLs use plain postgresql://; SQLAlchemy needs the driver named."""
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def head_revision() -> str:
    return ScriptDirectory.from_config(_config("")).get_current_head()


def current_revision(database_url: str) -> str | None:
    engine = create_engine(sqlalchemy_url(database_url), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _adopt_legacy_sqlite(database_url: str) -> bool:
    """Bring a SQLite database made before migrations existed under migration control."""
    path = sqlite_path(database_url)
    if not path.exists():
        return False
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    try:
        tables = {row["name"] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "alembic_version" in tables or "products" not in tables:
            return False
        upgrade_to_rev5(raw)
    finally:
        raw.close()
    command.stamp(_config(database_url), LEGACY_REVISION)
    return True


@contextmanager
def _sqlite_migration_lock(path: Path):
    """Serialise migrations of one SQLite file across processes. (PostgreSQL uses an advisory
    lock in migrations/env.py instead.)"""
    if fcntl is None:
        yield
        return
    with open(path.with_name(path.name + ".migrate-lock"), "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def upgrade(database_url: str) -> None:
    if not is_sqlite(database_url):
        command.upgrade(_config(database_url), "head")
        return
    path = sqlite_path(database_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _sqlite_migration_lock(path):
        _adopt_legacy_sqlite(database_url)
        command.upgrade(_config(database_url), "head")


def ensure_current(database_url: str) -> None:
    current, head = current_revision(database_url), head_revision()
    if current != head:
        raise SchemaOutOfDate(
            f"The database schema is at revision {current or 'none'} but this version needs {head}. "
            "Run `python -m app.migrations upgrade` (from the backend directory) and start the server again."
        )


def prepare_database(settings: Settings) -> None:
    """Apply migrations, or with auto-migration off, refuse to run on an outdated schema."""
    if settings.auto_migrate:
        upgrade(settings.database_url)
    else:
        ensure_current(settings.database_url)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    action = args[0] if args else "upgrade"
    url = load_settings().database_url
    if action == "upgrade":
        upgrade(url)
        print(f"Database is at revision {current_revision(url)}.")
    elif action == "check":
        try:
            ensure_current(url)
        except SchemaOutOfDate as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Database schema is up to date.")
    elif action == "current":
        print(current_revision(url) or "none")
    else:
        print("Usage: python -m app.migrations [upgrade|check|current]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
