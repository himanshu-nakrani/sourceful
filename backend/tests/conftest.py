import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEST_DATA_DIR = BASE_DIR / "data"

os.environ["DATABASE_PATH"] = str(TEST_DATA_DIR / "test_ragapp.db")
os.environ["VECTOR_STORE_DIRECTORY"] = str(TEST_DATA_DIR / "test_vectors")
os.environ["DOCUMENT_REGISTRY_PATH"] = str(TEST_DATA_DIR / "test_documents.json")
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["RATE_LIMIT_RPM"] = "1000"
os.environ["WORKER_HEARTBEAT_TTL_SECONDS"] = "600"
os.environ["DEFAULT_SUPERUSER_EMAIL"] = "admin@example.com"
os.environ["DEFAULT_SUPERUSER_PASSWORD"] = "admin123"

from backend.database import close_db, init_db, record_heartbeat
from backend.main import app
from backend.settings import settings


def cleanup_test_data() -> None:
    if os.path.exists(settings.database_path):
        try:
            os.remove(settings.database_path)
        except OSError:
            pass
    if os.path.exists(settings.vector_store_directory):
        try:
            shutil.rmtree(settings.vector_store_directory)
        except OSError:
            pass
    if os.path.exists(settings.document_registry_path):
        try:
            os.remove(settings.document_registry_path)
        except OSError:
            pass


def _assert_disposable_postgres() -> None:
    """Refuse to wipe a database that is not explicitly a test database.

    Settings may pick DATABASE_URL up from a local .env, so a plain test run
    could otherwise TRUNCATE a real application database. Allowed when the
    database name contains "test" or ALLOW_TEST_DB_TRUNCATE=1 is set.
    """
    from psycopg.conninfo import conninfo_to_dict

    dbname = conninfo_to_dict(settings.database_url).get("dbname") or ""
    if "test" in dbname.lower() or os.environ.get("ALLOW_TEST_DB_TRUNCATE") == "1":
        return
    pytest.exit(
        f"Refusing to run the test suite against Postgres database {dbname!r}: every test "
        "truncates all tables. Use a database whose name contains 'test', or set "
        "ALLOW_TEST_DB_TRUNCATE=1 if this database is disposable.",
        returncode=2,
    )


def pytest_sessionstart(session):
    if settings.using_postgres:
        _assert_disposable_postgres()


async def _truncate_postgres_tables() -> None:
    """Postgres isolation: empty every app table (schema stays migrated).

    SQLite isolation is the per-test database file removed by
    cleanup_test_data(); Postgres is one shared database, so without this,
    rows from earlier tests leak into later ones.
    """
    from backend.database import fetch_all, execute

    rows = await fetch_all(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
        "AND tablename <> 'schema_migrations'"
    )
    if rows:
        names = ", ".join('"' + r["tablename"] + '"' for r in rows)
        await execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")


@pytest.fixture(autouse=True)
def db_setup():
    cleanup_test_data()
    import asyncio

    async def _prepare() -> None:
        # Initialize schema + heartbeat, then close again inside the same event
        # loop. On Postgres, init_db() creates an AsyncConnectionPool whose
        # background tasks are bound to the running loop; leaving it open after
        # asyncio.run() returns made TestClient reuse a pool from a dead loop
        # and fail with CancelledError on lifespan shutdown. Callers re-init
        # lazily (fetch_*/execute call init_db()).
        await init_db()
        if settings.using_postgres:
            await _truncate_postgres_tables()
        await record_heartbeat("worker")
        await close_db()

    asyncio.run(_prepare())
    yield
    asyncio.run(close_db())
    cleanup_test_data()


@pytest.fixture(autouse=True)
def _close_pool_with_each_event_loop(monkeypatch):
    """Close the DB pool before any ``asyncio.run()`` inside a test returns.

    Tests call ``asyncio.run(...)`` directly (dozens of times) and never
    ``close_db()``. On Postgres the psycopg pool may still be growing when that
    loop shuts down; the cancelled connect is retried with backoff and the
    run hangs. App entry points (worker, scripts) already close the pool; this
    gives every test-owned loop the same lifecycle.
    """
    import asyncio

    real_run = asyncio.run

    def run(main, *args, **kwargs):
        async def _wrapped():
            try:
                return await main
            finally:
                await close_db()

        return real_run(_wrapped(), *args, **kwargs)

    monkeypatch.setattr(asyncio, "run", run)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
