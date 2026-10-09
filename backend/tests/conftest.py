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
        await record_heartbeat("worker")
        await close_db()

    asyncio.run(_prepare())
    yield
    asyncio.run(close_db())
    cleanup_test_data()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
