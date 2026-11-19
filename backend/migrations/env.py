"""Alembic environment: runs migrations against the URL given by app/migrations.py (FR69)."""

from alembic import context
from sqlalchemy import create_engine, pool, text

from app.config import load_settings
from app.migrations import MIGRATION_LOCK_KEY, sqlalchemy_url

config = context.config


def run_migrations_online() -> None:
    # Set by app/migrations.py; when the alembic CLI is used directly, use the server's settings.
    database_url = config.attributes.get("database_url") or load_settings().database_url
    engine = create_engine(sqlalchemy_url(database_url), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                # Only one process applies migrations; the others wait here and then find
                # nothing left to do, because the current revision is read after the lock.
                connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported; run them against a database.")
run_migrations_online()
