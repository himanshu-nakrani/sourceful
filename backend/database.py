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
                        await _apply_postgres_v5_migration(cur)
                        await _apply_postgres_v6_migration(cur)
                        await _apply_postgres_v7_migration(cur)
                        await _apply_postgres_v8_migration(cur)
                        await _apply_postgres_v9_migration(cur)
                        await _apply_postgres_v11_migration(cur)
                        await _apply_postgres_v12_migration(cur)
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
                try:
                    await _sqlite.execute(statement)
                except Exception as e:
                    # Skip duplicate column errors (column already exists from fresh schema)
                    if "duplicate column name" in str(e).lower():
                        continue
                    raise
            await _apply_sqlite_v2_migration(_sqlite)
            await _apply_sqlite_v3_migration(_sqlite)
            await _apply_sqlite_v4_migration(_sqlite)
            await _apply_sqlite_v5_migration(_sqlite)
            await _apply_sqlite_v6_migration(_sqlite)
            await _apply_sqlite_v7_migration(_sqlite)
            await _apply_sqlite_v8_migration(_sqlite)
            await _apply_sqlite_v9_migration(_sqlite)
            await _apply_sqlite_v11_migration(_sqlite)
            await _apply_sqlite_v12_migration(_sqlite)
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


async def _apply_postgres_v5_migration(cur) -> None:
    """v5: hybrid search FTS column + GIN + HNSW vector index."""
    await cur.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
        """
    )
    await cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_content_tsv
        ON document_chunks USING GIN (content_tsv)
        """
    )
    # HNSW index for dense retrieval. Use vector_cosine_ops since retrieval
    # uses cosine distance (<=>). IF NOT EXISTS so repeat migrations are safe.
    from backend.settings import settings as _settings
    m = max(2, int(_settings.pgvector_hnsw_m))
    ef = max(4, int(_settings.pgvector_hnsw_ef_construction))
    try:
        await cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw
            ON document_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = {m}, ef_construction = {ef})
            """
        )
    except Exception as exc:
        # Older pgvector without HNSW support — fall back to IVFFlat.
        logger.warning("hnsw_index_failed err=%s falling_back_to_ivfflat", exc)
        try:
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_ivfflat
                ON document_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        except Exception:
            logger.exception("ivfflat_index_also_failed")
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (5)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v5_migration(conn: aiosqlite.Connection) -> None:
    """SQLite has no native FTS/HNSW parity; record version for schema check."""
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (5)")


async def _apply_postgres_v6_migration(cur) -> None:
    """v6: parent-document retrieval — store parent window text per chunk."""
    await cur.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS parent_content TEXT
        """
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (6)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v6_migration(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(document_chunks)")
    rows = await cursor.fetchall()
    await cursor.close()
    columns = {row[1] for row in rows}
    if "parent_content" not in columns:
        await conn.execute("ALTER TABLE document_chunks ADD COLUMN parent_content TEXT")
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (6)")


async def _apply_postgres_v7_migration(cur) -> None:
    """v7: table-aware chunking + progress telemetry.

    - chunk_type: 'text' (default) | 'table' | 'image' — allows UI and
      retrieval to handle tables differently.
    - metadata_json: arbitrary JSON per chunk (table headers, slide index, etc.)
    - progress_detail: free-form stage detail surfaced in job status API.
    """
    await cur.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS chunk_type TEXT NOT NULL DEFAULT 'text'
        """
    )
    await cur.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS metadata_json TEXT
        """
    )
    await cur.execute(
        """
        ALTER TABLE document_jobs
        ADD COLUMN IF NOT EXISTS progress_detail TEXT
        """
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (7)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v7_migration(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(document_chunks)")
    rows = await cursor.fetchall()
    await cursor.close()
    columns = {row[1] for row in rows}
    if "chunk_type" not in columns:
        await conn.execute(
            "ALTER TABLE document_chunks ADD COLUMN chunk_type TEXT NOT NULL DEFAULT 'text'"
        )
    if "metadata_json" not in columns:
        await conn.execute("ALTER TABLE document_chunks ADD COLUMN metadata_json TEXT")

    cursor2 = await conn.execute("PRAGMA table_info(document_jobs)")
    job_rows = await cursor2.fetchall()
    await cursor2.close()
    job_columns = {row[1] for row in job_rows}
    if "progress_detail" not in job_columns:
        await conn.execute("ALTER TABLE document_jobs ADD COLUMN progress_detail TEXT")

    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (7)")


async def _apply_postgres_v8_migration(cur) -> None:
    """v8: Phase 3 — feedback table + conversation memory + GraphRAG scaffold.

    - `feedback`: thumbs-up/down per assistant message with optional free-form
      comment. Consumed by the eval harness as an online quality signal (3.8)
      and by the UI to drive rephrase / expand-search hints (3.9).
    - `conversation_memory`: rolling summary per conversation so chat history
      older than ``MEMORY_RECENT_TURNS`` is collapsed instead of truncated
      (3.7).
    - `graph_entities` / `graph_relations`: scaffolding for GraphRAG ingestion
      (3.3). Populated by a follow-up worker job; kept empty and flag-gated
      (`RETRIEVAL_GRAPH_ENABLED`) until then so it's safe to ship the schema
      now.
    """
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id TEXT NOT NULL,
            rating SMALLINT NOT NULL,
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback (message_id)"
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_owner_created ON feedback (owner_id, created_at DESC)"
    )
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_memory (
            conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
            owner_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_entities (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            entity_type TEXT,
            description TEXT,
            metadata_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_entities_name ON graph_entities (owner_id, LOWER(name))"
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_entities_document ON graph_entities (document_id)"
    )
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_relations (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            source_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
            target_entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            description TEXT,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_relations_source ON graph_relations (source_entity_id)"
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_relations_target ON graph_relations (target_entity_id)"
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (8)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v8_migration(conn: aiosqlite.Connection) -> None:
    """SQLite parity for v8 — same tables + indexes, TEXT timestamps."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback (message_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_owner_created ON feedback (owner_id, created_at DESC)"
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_memory (
            conversation_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_entities (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            name TEXT NOT NULL,
            entity_type TEXT,
            description TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_entities_document ON graph_entities (document_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_entities_owner_name ON graph_entities (owner_id, name)"
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_relations (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source_entity_id TEXT NOT NULL,
            target_entity_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            description TEXT,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (source_entity_id) REFERENCES graph_entities(id) ON DELETE CASCADE,
            FOREIGN KEY (target_entity_id) REFERENCES graph_entities(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_relations_source ON graph_relations (source_entity_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_relations_target ON graph_relations (target_entity_id)"
    )
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (8)")


async def _apply_postgres_v9_migration(cur) -> None:
    """v9: GraphRAG community layer (Phase 3.4).

    A ``graph_communities`` row is an owner/document-scoped cluster of
    entities with an LLM-written summary that the graph-traversal
    retrieval lane can dereference as an additional citation. The
    ``community_entities`` junction table is intentionally append-only
    — we drop and re-insert when a document is reprocessed via
    :func:`backend.services.graph.clear_document_graph`.
    """
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_communities (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            summary TEXT,
            entity_count INTEGER NOT NULL DEFAULT 0,
            algorithm TEXT NOT NULL DEFAULT 'connected_components',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_communities_document ON graph_communities (owner_id, document_id)"
    )
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS community_entities (
            community_id TEXT NOT NULL REFERENCES graph_communities(id) ON DELETE CASCADE,
            entity_id TEXT NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
            PRIMARY KEY (community_id, entity_id)
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_community_entities_entity ON community_entities (entity_id)"
    )
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (9)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v9_migration(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_communities (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            label TEXT NOT NULL,
            summary TEXT,
            entity_count INTEGER NOT NULL DEFAULT 0,
            algorithm TEXT NOT NULL DEFAULT 'connected_components',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_communities_document ON graph_communities (owner_id, document_id)"
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS community_entities (
            community_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (community_id, entity_id),
            FOREIGN KEY (community_id) REFERENCES graph_communities(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES graph_entities(id) ON DELETE CASCADE
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_community_entities_entity ON community_entities (entity_id)"
    )
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (9)")


async def _apply_postgres_v11_migration(cur) -> None:
    await cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_bytes BYTEA")
    await cur.execute(
        """
        INSERT INTO schema_migrations (version)
        VALUES (11)
        ON CONFLICT (version) DO NOTHING
        """
    )


async def _apply_sqlite_v11_migration(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute("PRAGMA table_info(documents)")
    rows = await cursor.fetchall()
    await cursor.close()
    columns = {row[1] for row in rows}
    if "file_bytes" not in columns:
        await conn.execute("ALTER TABLE documents ADD COLUMN file_bytes BLOB")
    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (11)")


async def _apply_postgres_v12_migration(cur) -> None:
    """v12: knowledge-workspace Phase 0 (workspace extras, conversations.workspace_id, workspace_sources, backfill)."""
    # Relax legacy ownership: owner_id was NOT NULL + FK to users(id); anonymous
    # owner_scopes cannot satisfy this. We keep the column for historical rows
    # but allow NULL and drop the FK.
    await cur.execute("ALTER TABLE workspaces ALTER COLUMN owner_id DROP NOT NULL")
    await cur.execute("ALTER TABLE workspaces DROP CONSTRAINT IF EXISTS workspaces_owner_id_fkey")
    await cur.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS owner_scope TEXT")
    await cur.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS description TEXT")
    await cur.execute(
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private'"
    )
    await cur.execute(
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await cur.execute(
        "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspaces_owner_scope ON workspaces(owner_scope)"
    )
    await cur.execute(
        """
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id)"
    )
    await cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_sources (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT 'file' CHECK (source_type IN ('file','url','note')),
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            source_title TEXT NOT NULL,
            source_url TEXT,
            mime_type TEXT,
            status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','error')),
            last_fetched_at TIMESTAMPTZ,
            metadata_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_sources_workspace ON workspace_sources(workspace_id)"
    )
    await cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_sources_document ON workspace_sources(document_id)"
    )
    # Backfill owner_scope from legacy owner_id (assumed to be user uuids for historical rows).
    await cur.execute(
        "UPDATE workspaces SET owner_scope = 'user:' || owner_id WHERE owner_scope IS NULL"
    )
    await _backfill_default_workspaces_postgres(cur)
    await cur.execute(
        "INSERT INTO schema_migrations (version) VALUES (12) ON CONFLICT (version) DO NOTHING"
    )


async def _backfill_default_workspaces_postgres(cur) -> None:
    """Create a default workspace per owner_id and backfill documents/conversations."""
    import uuid as _uuid
    # Collect distinct owner_ids from documents and conversations with missing workspace_id.
    await cur.execute(
        """
        SELECT DISTINCT owner_id FROM (
            SELECT owner_id FROM documents WHERE workspace_id IS NULL
            UNION
            SELECT owner_id FROM conversations WHERE workspace_id IS NULL
        ) AS owners
        WHERE owner_id IS NOT NULL AND owner_id <> ''
        """
    )
    owner_rows = await cur.fetchall()
    for row in owner_rows:
        owner_scope = row["owner_id"] if "owner_id" in row else row[0]
        if not owner_scope:
            continue
        # Fetch-or-create default workspace
        await cur.execute(
            "SELECT id FROM workspaces WHERE owner_scope = %s AND is_default = TRUE LIMIT 1",
            (owner_scope,),
        )
        existing = await cur.fetchone()
        if existing:
            workspace_id = existing["id"]
        else:
            workspace_id = str(_uuid.uuid4())
            slug = f"default-{workspace_id[:8]}"
            legacy_owner = owner_scope.split(":", 1)[1] if owner_scope.startswith("user:") else None
            await cur.execute(
                """
                INSERT INTO workspaces (id, name, slug, owner_id, owner_scope, description, visibility, archived, is_default)
                VALUES (%s, %s, %s, %s, %s, %s, 'private', FALSE, TRUE)
                """,
                (workspace_id, "Personal workspace", slug, legacy_owner, owner_scope, "Default workspace"),
            )
        await cur.execute(
            "UPDATE documents SET workspace_id = %s WHERE owner_id = %s AND workspace_id IS NULL",
            (workspace_id, owner_scope),
        )
        await cur.execute(
            "UPDATE conversations SET workspace_id = %s WHERE owner_id = %s AND workspace_id IS NULL",
            (workspace_id, owner_scope),
        )
        # Create workspace_sources rows for pre-existing documents.
        await cur.execute(
            """
            INSERT INTO workspace_sources (id, workspace_id, source_type, document_id, source_title, mime_type, status)
            SELECT
                gen_random_uuid()::text,
                %s,
                'file',
                d.id,
                d.filename,
                d.mime_type,
                CASE WHEN d.status = 'ready' THEN 'ready' ELSE d.status END
            FROM documents d
            WHERE d.owner_id = %s
              AND NOT EXISTS (SELECT 1 FROM workspace_sources ws WHERE ws.document_id = d.id)
            """,
            (workspace_id, owner_scope),
        )


async def _apply_sqlite_v12_migration(conn: aiosqlite.Connection) -> None:
    """v12: knowledge-workspace Phase 0 (SQLite parity with backfill)."""
    import uuid as _uuid

    async def _columns(table: str) -> list[tuple]:
        cursor = await conn.execute("SELECT * FROM pragma_table_info(?)", (table,))
        rows = await cursor.fetchall()
        await cursor.close()
        return list(rows)

    # Relax legacy NOT NULL + FK on workspaces.owner_id. SQLite doesn't support
    # altering column constraints in place, so we recreate the table when the
    # owner_id column is still marked NOT NULL.
    ws_info = await _columns("workspaces")
    owner_id_info = next((r for r in ws_info if r[1] == "owner_id"), None)
    if owner_id_info and owner_id_info[3] == 1:  # notnull
        await conn.execute("PRAGMA foreign_keys=OFF")
        try:
            existing_cols = {r[1] for r in ws_info}
            await conn.execute(
                """
                CREATE TABLE workspaces_v12_new (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    owner_id TEXT,
                    settings TEXT DEFAULT '{}',
                    owner_scope TEXT,
                    description TEXT,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    archived INTEGER NOT NULL DEFAULT 0,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            def _src(col: str, fallback: str) -> str:
                return col if col in existing_cols else fallback

            await conn.execute(
                f"""
                INSERT INTO workspaces_v12_new (
                    id, name, slug, owner_id, settings,
                    owner_scope, description, visibility, archived, is_default,
                    created_at, updated_at
                )
                SELECT
                    id,
                    name,
                    slug,
                    owner_id,
                    {_src('settings', "'{}'")},
                    {_src('owner_scope', 'NULL')},
                    {_src('description', 'NULL')},
                    {_src('visibility', "'private'")},
                    {_src('archived', '0')},
                    {_src('is_default', '0')},
                    {_src('created_at', 'CURRENT_TIMESTAMP')},
                    {_src('updated_at', 'CURRENT_TIMESTAMP')}
                FROM workspaces
                """
            )
            await conn.execute("DROP TABLE workspaces")
            await conn.execute("ALTER TABLE workspaces_v12_new RENAME TO workspaces")
            await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id)")
        finally:
            await conn.execute("PRAGMA foreign_keys=ON")

    ws_cols_info = await _columns("workspaces")
    ws_cols = {r[1] for r in ws_cols_info}
    if "owner_scope" not in ws_cols:
        await conn.execute("ALTER TABLE workspaces ADD COLUMN owner_scope TEXT")
    if "description" not in ws_cols:
        await conn.execute("ALTER TABLE workspaces ADD COLUMN description TEXT")
    if "visibility" not in ws_cols:
        await conn.execute(
            "ALTER TABLE workspaces ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'"
        )
    if "archived" not in ws_cols:
        await conn.execute(
            "ALTER TABLE workspaces ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )
    if "is_default" not in ws_cols:
        await conn.execute(
            "ALTER TABLE workspaces ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
        )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspaces_owner_scope ON workspaces(owner_scope)"
    )

    conv_info = await _columns("conversations")
    conv_cols = {r[1] for r in conv_info}
    if "workspace_id" not in conv_cols:
        await conn.execute(
            "ALTER TABLE conversations ADD COLUMN workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL"
        )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_id)"
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_sources (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT 'file' CHECK (source_type IN ('file','url','note')),
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            source_title TEXT NOT NULL,
            source_url TEXT,
            mime_type TEXT,
            status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','error')),
            last_fetched_at TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_sources_workspace ON workspace_sources(workspace_id)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_sources_document ON workspace_sources(document_id)"
    )

    await conn.execute(
        "UPDATE workspaces SET owner_scope = 'user:' || owner_id WHERE owner_scope IS NULL"
    )

    # Backfill default workspaces for every distinct owner_id that has documents/conversations.
    owner_cursor = await conn.execute(
        """
        SELECT DISTINCT owner_id FROM (
            SELECT owner_id FROM documents WHERE workspace_id IS NULL
            UNION
            SELECT owner_id FROM conversations WHERE workspace_id IS NULL
        )
        WHERE owner_id IS NOT NULL AND owner_id <> ''
        """
    )
    owner_rows = await owner_cursor.fetchall()
    await owner_cursor.close()
    for row in owner_rows:
        owner_scope = row[0]
        if not owner_scope:
            continue
        # Fetch-or-create default workspace
        cursor = await conn.execute(
            "SELECT id FROM workspaces WHERE owner_scope = ? AND is_default = 1 LIMIT 1",
            (owner_scope,),
        )
        existing = await cursor.fetchone()
        await cursor.close()
        if existing:
            workspace_id = existing[0]
        else:
            workspace_id = str(_uuid.uuid4())
            slug = f"default-{workspace_id[:8]}"
            legacy_owner = owner_scope.split(":", 1)[1] if owner_scope.startswith("user:") else owner_scope
            await conn.execute(
                """
                INSERT INTO workspaces (id, name, slug, owner_id, owner_scope, description, visibility, archived, is_default)
                VALUES (?, ?, ?, ?, ?, ?, 'private', 0, 1)
                """,
                (workspace_id, "Personal workspace", slug, legacy_owner, owner_scope, "Default workspace"),
            )
        await conn.execute(
            "UPDATE documents SET workspace_id = ? WHERE owner_id = ? AND workspace_id IS NULL",
            (workspace_id, owner_scope),
        )
        await conn.execute(
            "UPDATE conversations SET workspace_id = ? WHERE owner_id = ? AND workspace_id IS NULL",
            (workspace_id, owner_scope),
        )
        # Create workspace_sources rows for pre-existing documents.
        doc_cursor = await conn.execute(
            """
            SELECT id, filename, mime_type, status FROM documents
            WHERE owner_id = ?
              AND id NOT IN (SELECT document_id FROM workspace_sources WHERE document_id IS NOT NULL)
            """,
            (owner_scope,),
        )
        doc_rows = await doc_cursor.fetchall()
        await doc_cursor.close()
        for drow in doc_rows:
            await conn.execute(
                """
                INSERT INTO workspace_sources (id, workspace_id, source_type, document_id, source_title, mime_type, status)
                VALUES (?, ?, 'file', ?, ?, ?, ?)
                """,
                (
                    str(_uuid.uuid4()),
                    workspace_id,
                    drow[0],
                    drow[1],
                    drow[2],
                    drow[3] if drow[3] in ("queued", "processing", "ready", "error") else "queued",
                ),
            )

    await conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (12)")


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
