import os
import subprocess
import sys

import pytest

from app.config import BACKEND_DIR
from app.database import connect
from app.migrations import SchemaOutOfDate, current_revision, ensure_current, head_revision, upgrade


def test_empty_database_is_brought_to_head(database_url):
    assert current_revision(database_url) is None
    with pytest.raises(SchemaOutOfDate, match="python -m app.migrations upgrade"):
        ensure_current(database_url)
    upgrade(database_url)
    assert current_revision(database_url) == head_revision()
    ensure_current(database_url)
    conn = connect(database_url)
    # The SQL helper functions exist on every database (FR68).
    assert conn.execute("SELECT casefold('ÄRMEL'), instr('abcdef', 'cd')").fetchone()[:] == ("ärmel", 3)
    conn.close()


def test_concurrent_upgrades_from_several_processes_apply_migrations_once(database_url):
    # Separate processes, as with several containers or server workers starting together.
    env = {**os.environ, "SHOP_DATABASE_URL": database_url}
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "app.migrations", "upgrade"],
            cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for _ in range(4)
    ]
    outputs = [process.communicate(timeout=120)[0] for process in processes]
    assert [process.returncode for process in processes] == [0, 0, 0, 0], outputs
    assert current_revision(database_url) == head_revision()


def test_server_refuses_outdated_schema_when_auto_migration_is_off(tmp_path, database_url):
    from fastapi.testclient import TestClient

    from app.config import PROJECT_ROOT, Settings
    from app.main import create_app

    settings = Settings(
        db_path=tmp_path / "db",
        database_url=database_url,
        upload_dir=tmp_path / "up",
        frontend_dir=PROJECT_ROOT / "frontend",
        auto_migrate=False,
    )
    with pytest.raises(SchemaOutOfDate), TestClient(create_app(settings)):
        pass
    upgrade(database_url)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_health_reports_unreachable_database(tmp_path, database_url):
    from fastapi.testclient import TestClient

    from app.config import PROJECT_ROOT, Settings
    from app.main import create_app

    settings = Settings(db_path=tmp_path / "db", database_url=database_url, upload_dir=tmp_path / "up",
                        frontend_dir=PROJECT_ROOT / "frontend", seed_demo_data=False)
    with TestClient(create_app(settings)) as client:
        ok = client.get("/api/health")
        assert ok.status_code == 200 and ok.json() == {"status": "ok"}
        assert "content-security-policy" in ok.headers
        settings.database_url = "postgresql://nobody:wrong@127.0.0.1:1/none?connect_timeout=1"
        down = client.get("/api/health")
    assert down.status_code == 503
    assert down.json() == {"status": "unavailable"}


def test_demo_data_is_seeded_once_by_concurrent_workers(tmp_path, database_url):
    """Several server workers start at the same time with demo data enabled (FR39, FR71)."""
    import threading

    from app.database import connect
    from app.seed import seed

    upgrade(database_url)
    errors = []

    def worker():
        conn = connect(database_url)
        try:
            seed(conn, tmp_path / "uploads", True)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    conn = connect(database_url)
    counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("users", "products", "categories")]
    conn.close()
    assert errors == []
    assert counts == [3, 16, 4]
