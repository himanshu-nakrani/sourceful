"""Database helpers with PostgreSQL-first support and SQLite fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite
import logging # Added logging
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from backend.migrations import migration_statements, schema_version
from backend.settings import settings

logger = logging.getLogger("ragapp.database") # Added logger
_pg_pool: AsyncConnectionPool | None = None
_sqlite: aiosqlite.Connection | None = None
_init_lock = asyncio.Lock() # Added lock


def _sql(query: str) -> str:
    if settings.using_postgres:
        return query.replace("?", "%s")
    return query


async def init_db() -> None:
    """
    Initialize the module's database connection(s) and apply schema migrations.
    
    This function serializes initialization to a single concurrent caller, preferring a PostgreSQL connection pool when configured and falling back to a local SQLite connection. It applies legacy repairs and versioned migrations (up through version 4), configures connection-level settings (pool options or SQLite PRAGMAs), and sets module-level connection globals on success. If initialization fails, any partially-created connection is closed, module state is reset, and the original exception is re-raised.
    
    Raises:
        Exception: If database initialization or migration application fails.
    """
    global _pg_pool, _sqlite
    async with _init_lock:
        if settings.using_postgres:
            if _pg_pool is not None:
                return
            try:
                logger.info("Initializing Postgres connection pool...")
                _pg_pool = AsyncConnectionPool(
                    conninfo=settings.database_url,
                    min_size=1,
                    max_size=8,
                    kwargs={
                        "row_factory": dict_row,
                        "autocommit": True,
                        "prepare_threshold": None,  # Compatibility with transaction poolers
                    },
                    open=False,
                )
                await _pg_pool.open()
                await _pg_pool.wait()
                
                async with _pg_pool.connection() as conn:
                    async with conn.cursor() as cur:
                        logger.info("Running database migrations...")
                        await _repair_postgres_legacy_owner_columns(cur)
                        for statement in migration_statements():
                            try:
                                await cur.execute(statement)
                            except Exception as e:
                                logger.error(f"Migration statement failed: {statement[:100]}... Error: {e}")
                                raise
                        await _apply_postgres_v2_migration(cur)
                        await _apply_postgres_v3_migration(cur)
                        await _apply_postgres_v4_migration(cur)
                logger.info("Postgres initialized.")
                return
            except Exception:
                logger.exception("Database initialization failed (Postgres)")
                if _pg_pool:
                    await _pg_pool.close()
                    _pg_pool = None
                raise

        if _sqlite is not None:
            return

        try:
            logger.info("Initializing SQLite database...")
            path = Path(settings.database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            _sqlite = await aiosqlite.connect(str(path))
            _sqlite.row_factory = aiosqlite.Row
            await _sqlite.execute("PRAGMA journal_mode=WAL")
            await _sqlite.execute("PRAGMA foreign_keys=ON")
            for statement in migration_statements():
                await _sqlite.execute(statement)
            await _apply_sqlite_v2_migration(_sqlite)
            await _apply_sqlite_v3_migration(_sqlite)
            await _apply_sqlite_v4_migration(_sqlite)
            await _sqlite.commit()
            logger.info("SQLite initialized.")
        except Exception:
            logger.exception("Database initialization failed (SQLite)")
            if _sqlite:
                await _sqlite.close()
                _sqlite = None
            raise


async def _repair_postgres_legacy_owner_columns(cur) -> None:
    """Backfill legacy PostgreSQL schemas created before owner scoping."""
    owner_targets = [
        "documents",
        "document_jobs",
        "document_chunks",
        "conversations",
        "messages",
    ]
    for table_name in owner_targets:
        await cur.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = %s
                ) AS table_exists,
                EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = 'owner_id'
                ) AS has_owner
            """,
            (table_name, table_name),
        )
        row = await cur.fetchone()
        table_exists = bool(row and row.get("table_exists"))
        has_owner = bool(row and row.get("has_owner"))
        if not table_exists or has_owner:
            continue

        await cur.execute(
            f"""
            ALTER TABLE {table_name} ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'anonymous:legacy';
            ALTER TABLE {table_name} ALTER COLUMN owner_id DROP DEFAULT;
            """
        )
        logger.warning("Applied legacy owner_id repair for table=%s", table_name)

    await _repair_postgres_legacy_document_columns(cur)


async def _repair_postgres_legacy_document_columns(cur) -> None:
    """Backfill required columns for legacy documents table variants."""
    await cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'documents'
        ) AS table_exists
        """
    )
    table_row = await cur.fetchone()
    if not table_row or not table_row.get("table_exists"):
        return

    required_columns: list[tuple[str, str, str | None]] = [
        ("provider", "TEXT", "'openai'"),
        ("embedding_model", "TEXT", "'text-embedding-3-small'"),
        ("mime_type", "TEXT", "'application/octet-stream'"),
        ("checksum", "TEXT", "'legacy-unknown'"),
        ("chunk_count", "INTEGER", "0"),
        ("file_size", "INTEGER", "0"),
        ("status", "TEXT", "'queued'"),
    ]
    for column_name, column_type, default_sql in required_columns:
        await cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'documents'
                  AND column_name = %s
            ) AS has_column
            """,
            (column_name,),
        )
        row = await cur.fetchone()
        has_column = bool(row and row.get("has_column"))
        if has_column:
            continue

        await cur.execute(
            f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
        )
        if default_sql is not None:
            await cur.execute(
                f"UPDATE documents SET {column_name} = {default_sql} WHERE {column_name} IS NULL"
            )
            await cur.execute(
                f"ALTER TABLE documents ALTER COLUMN {column_name} SET NOT NULL"
            )
        logger.warning("Applied legacy documents column repair for column=%s", column_name)


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


async def _apply_postgres_v3_migration(cur) -> None:
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_verified BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            user_agent TEXT,
            ip_address TEXT,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id, revoked)")
    await cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)")
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (3)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v3_migration(conn: aiosqlite.Connection) -> None:
    """
    Apply the version 3 SQLite schema migration.
    
    Creates `users` and `auth_sessions` tables (with appropriate columns and indexes) and records migration version 3 in `schema_migrations`.
    
    Parameters:
        conn (aiosqlite.Connection): An open SQLite connection on which to execute the migration statements.
    """
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            user_agent TEXT,
            ip_address TEXT,
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id, revoked)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)")
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (3)")


async def _apply_postgres_v4_migration(cur) -> None:
    """
    Apply schema migration version 4 to a PostgreSQL database.
    
    Adds a nullable `document_ids_json` TEXT column to the `conversations` table if it does not already exist, and records migration version 4 in `schema_migrations` (no-op if the version is already present).
    
    Parameters:
        cur: An async cursor/connection object capable of executing SQL statements (e.g., a psycopg async cursor).
    """
    await cur.execute(
        """
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS document_ids_json TEXT
        """
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (4)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v4_migration(conn: aiosqlite.Connection) -> None:
    """
    Apply schema migration version 4 to a SQLite database connection.
    
    Adds a nullable `document_ids_json` TEXT column to the `conversations` table if it does not already exist, and records version `4` in the `schema_migrations` table.
    
    Parameters:
        conn (aiosqlite.Connection): Open SQLite connection on which to run the migration.
    """
    cursor = await conn.execute("PRAGMA table_info(conversations)")
    rows = await cursor.fetchall()
    await cursor.close()
    columns = {row[1] for row in rows}
    if "document_ids_json" not in columns:
        await conn.execute("ALTER TABLE conversations ADD COLUMN document_ids_json TEXT")
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (4)")


async def close_db() -> None:
    """
    Close any active database connections and clear the module-level connection state.
    
    Closes the PostgreSQL connection pool and/or the SQLite connection if they exist, and resets the corresponding module globals so the database layer can be reinitialized.
    """
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


async def execute_many(query: str, params_list: list[tuple[Any, ...]]) -> None:
    """Executes a database query for high-performance bulk operations."""
    await init_db()
    if not params_list:
        return

    if settings.using_postgres:
        assert _pg_pool is not None
        async with _pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(_sql(query), params_list)
        return

    assert _sqlite is not None
    await _sqlite.executemany(query, params_list)
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
