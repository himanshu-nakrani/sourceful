"""Database helpers with PostgreSQL-first support and SQLite fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from backend.migrations import migration_statements, schema_version
from backend.settings import settings

_pg_pool: AsyncConnectionPool | None = None
_sqlite: aiosqlite.Connection | None = None


def _sql(query: str) -> str:
    if settings.using_postgres:
        return query.replace("?", "%s")
    return query


async def init_db() -> None:
    global _pg_pool, _sqlite
    if settings.using_postgres:
        if _pg_pool is not None:
            return
        _pg_pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        await _pg_pool.open()
        await _pg_pool.wait()
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                for statement in migration_statements():
                    await cur.execute(statement)
                await _apply_postgres_v2_migration(cur)
        return

    if _sqlite is not None:
        return

    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _sqlite = await aiosqlite.connect(str(path))
    _sqlite.row_factory = aiosqlite.Row
    await _sqlite.execute("PRAGMA journal_mode=WAL")
    await _sqlite.execute("PRAGMA foreign_keys=ON")
    for statement in migration_statements():
        await _sqlite.execute(statement)
    await _apply_sqlite_v2_migration(_sqlite)
    await _sqlite.commit()


async def _apply_postgres_v2_migration(cur) -> None:
    await cur.execute(
        """
        ALTER TABLE document_jobs
        ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ
        """
    )
    await cur.execute(
        """
        ALTER TABLE document_jobs
        ADD COLUMN IF NOT EXISTS terminal BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (2)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v2_migration(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(document_jobs)")
    rows = await cursor.fetchall()
    await cursor.close()
    columns = {row[1] for row in rows}

    if "next_retry_at" not in columns:
        await conn.execute("ALTER TABLE document_jobs ADD COLUMN next_retry_at TEXT")
    if "terminal" not in columns:
        await conn.execute(
            "ALTER TABLE document_jobs ADD COLUMN terminal INTEGER NOT NULL DEFAULT 0"
        )
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (2)")


async def close_db() -> None:
    global _pg_pool, _sqlite
    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
    if _sqlite is not None:
        await _sqlite.close()
        _sqlite = None


async def fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    await init_db()
    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_sql(query), params)
                row = await cur.fetchone()
                return dict(row) if row else None

    assert _sqlite is not None
    cursor = await _sqlite.execute(query, params)
    row = await cursor.fetchone()
    await cursor.close()
    return dict(row) if row else None


async def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    await init_db()
    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_sql(query), params)
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    assert _sqlite is not None
    cursor = await _sqlite.execute(query, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return [dict(row) for row in rows]


async def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    await init_db()
    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_sql(query), params)
        return

    assert _sqlite is not None
    await _sqlite.execute(query, params)
    await _sqlite.commit()


async def execute_returning(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    await init_db()
    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_sql(query), params)
                row = await cur.fetchone()
                return dict(row) if row else None

    assert _sqlite is not None
    cursor = await _sqlite.execute(query, params)
    row = await cursor.fetchone()
    await cursor.close()
    await _sqlite.commit()
    return dict(row) if row else None


async def execute_script(statements: list[str]) -> None:
    await init_db()
    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                for statement in statements:
                    await cur.execute(statement)
        return

    assert _sqlite is not None
    for statement in statements:
        await _sqlite.execute(statement)
    await _sqlite.commit()


async def current_schema_version() -> int:
    row = await fetch_one("SELECT MAX(version) AS version FROM schema_migrations")
    if not row or row["version"] is None:
        return 0
    return int(row["version"])


async def require_current_schema() -> None:
    version = await current_schema_version()
    expected = schema_version()
    if version < expected:
        raise RuntimeError(f"Database schema is outdated: found {version}, expected {expected}")


async def upsert_rate_limit(bucket_id: str, window_start: int) -> int:
    row = await execute_returning(
        """
        INSERT INTO rate_limit_windows (bucket_id, window_start, request_count)
        VALUES (?, ?, 1)
        ON CONFLICT(bucket_id, window_start)
        DO UPDATE SET request_count = rate_limit_windows.request_count + 1
        RETURNING request_count
        """,
        (bucket_id, window_start),
    )
    return int((row or {}).get("request_count", 1))


async def cleanup_rate_limits(before_window_start: int) -> None:
    await execute(
        "DELETE FROM rate_limit_windows WHERE window_start < ?",
        (before_window_start,),
    )


async def record_heartbeat(service_name: str) -> None:
    if settings.using_postgres:
        await execute(
            """
            INSERT INTO service_heartbeats (service_name, updated_at)
            VALUES (?, NOW())
            ON CONFLICT(service_name)
            DO UPDATE SET updated_at = EXCLUDED.updated_at
            """,
            (service_name,),
        )
        return

    await execute(
        """
        INSERT INTO service_heartbeats (service_name, updated_at)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(service_name)
        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
        (service_name,),
    )
