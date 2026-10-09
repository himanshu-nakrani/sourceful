"""Postgres + pgvector: schema v16 pins embeddings to vector(1536) with HNSW.

Skipped unless DATABASE_URL points at Postgres. Run locally with e.g.::

    DATABASE_URL=postgresql://postgres@/test?host=/tmp&port=55432 \
    ANON_SESSION_SECRET=x pytest -q backend/tests/test_embedding_dims_postgres.py

The nightly eval workflow runs it against pgvector/pgvector:pg16.
"""

from __future__ import annotations

import asyncio
import random
import uuid

import pytest

from backend.settings import settings

pytestmark = pytest.mark.skipif(not settings.using_postgres, reason="requires Postgres + pgvector")


def _vec(dims: int, seed: int) -> str:
    rng = random.Random(seed)
    return "[" + ",".join(f"{rng.uniform(-1, 1):.6f}" for _ in range(dims)) + "]"


async def _rewind_to_pre_v16(execute) -> None:
    """Recreate the pre-v16 shape: undimensioned column, no vector index, no flag."""
    await execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_hnsw")
    await execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_ivfflat")
    await execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector")
    await execute("DROP TABLE IF EXISTS document_chunk_embeddings_legacy")
    await execute("ALTER TABLE documents DROP COLUMN IF EXISTS reembed_required")
    await execute("DELETE FROM schema_migrations WHERE version = 16")


def test_v16_migrates_legacy_rows_and_builds_hnsw():
    from backend.database import close_db, execute, fetch_all, fetch_one, init_db

    tag = uuid.uuid4().hex[:8]
    legacy, current = f"legacy-{tag}", f"current-{tag}"
    legacy_vec = _vec(3072, 1)

    async def scenario() -> None:
        await init_db()
        try:
            await _rewind_to_pre_v16(execute)
            for doc_id, model in ((legacy, "models/gemini-embedding-001"), (current, "text-embedding-3-small")):
                await execute(
                    "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status) "
                    "VALUES (?, 'o', 'f.txt', ?, ?, 'text/plain', ?, 'ready')",
                    (doc_id, "gemini" if "gemini" in model else "openai", model, doc_id),
                )
            await execute(
                "INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding) "
                "VALUES (?, ?, 'o', 0, 'legacy text', ?::vector)",
                (f"{legacy}:0", legacy, legacy_vec),
            )
            for i in range(40):
                await execute(
                    "INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding) "
                    "VALUES (?, ?, 'o', ?, 'current text', ?::vector)",
                    (f"{current}:{i}", current, i, _vec(1536, 100 + i)),
                )
        finally:
            await close_db()

        # Upgrade twice: the second run must be a no-op.
        for _ in range(2):
            await init_db()
            await close_db()

        await init_db()
        try:
            col = await fetch_one(
                "SELECT format_type(atttypid, atttypmod) AS t FROM pg_attribute "
                "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
            )
            assert col["t"] == "vector(1536)"
            idx = await fetch_one(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'idx_document_chunks_embedding_hnsw'"
            )
            assert idx and "USING hnsw (embedding vector_cosine_ops)" in idx["indexdef"]
            assert (await fetch_one("SELECT MAX(version) AS v FROM schema_migrations"))["v"] == 16

            # Legacy 3072-dim row: archived verbatim, cleared, document flagged, text kept.
            flagged = await fetch_one("SELECT reembed_required, last_error, status FROM documents WHERE id = ?", (legacy,))
            assert flagged["reembed_required"] is True and flagged["status"] == "ready"
            assert "python -m backend.scripts.reembed" in flagged["last_error"]
            chunk = await fetch_one("SELECT embedding, content FROM document_chunks WHERE id = ?", (f"{legacy}:0",))
            assert chunk["embedding"] is None and chunk["content"] == "legacy text"
            archived = await fetch_all(
                "SELECT dims, embedding::text = ?::vector::text AS same FROM document_chunk_embeddings_legacy WHERE document_id = ?",
                (legacy_vec, legacy),
            )
            assert [(r["dims"], r["same"]) for r in archived] == [(3072, True)]

            # Compatible 1536-dim rows are untouched.
            clean = await fetch_one("SELECT reembed_required FROM documents WHERE id = ?", (current,))
            assert clean["reembed_required"] is False
            kept = await fetch_one(
                "SELECT count(*) AS n FROM document_chunks WHERE document_id = ? AND vector_dims(embedding) = 1536",
                (current,),
            )
            assert kept["n"] == 40

            # Wrong-size writes are now rejected by the column type itself.
            with pytest.raises(Exception, match="expected 1536 dimensions"):
                await execute(
                    "INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding) "
                    "VALUES (?, ?, 'o', 99, 'x', ?::vector)",
                    (f"{current}:bad", current, _vec(3072, 9)),
                )

            # Pooled connections enable pgvector iterative scans (filtered HNSW recall).
            setting = await fetch_one("SELECT current_setting('hnsw.iterative_scan', true) AS v")
            assert setting["v"] == "strict_order"
        finally:
            await close_db()

    asyncio.run(scenario())

    async def explain_and_cleanup() -> None:
        import backend.database as database

        await init_db()
        try:
            async with database._pg_pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Force index paths so the plan proves the index *can* serve the
                    # query's operator (on 20k+ rows the planner picks it unaided).
                    await cur.execute("SET enable_seqscan = off")
                    await cur.execute("SET enable_bitmapscan = off")
                    query = _vec(1536, 7)
                    await cur.execute(
                        "EXPLAIN (COSTS OFF) SELECT id FROM document_chunks "
                        "WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT 5",
                        (query,),
                    )
                    plan = "\n".join(row["QUERY PLAN"] for row in await cur.fetchall())
                    assert "idx_document_chunks_embedding_hnsw" in plan, plan
                    assert "Order By: (embedding <=>" in plan, plan
                    await cur.execute("RESET enable_seqscan")
                    await cur.execute("RESET enable_bitmapscan")
            # The app's own retrieval returns correct results through the new column.
            from backend.services.vectorstore import query_similar

            hits = await query_similar(current, "o", [float(x) for x in _vec(1536, 100)[1:-1].split(",")], top_k=3)
            assert hits and hits[0].chunk_id == f"{current}:0" and hits[0].score == pytest.approx(1.0, abs=1e-4)
            assert await query_similar(legacy, "o", [0.1] * 1536, top_k=3) == []  # nulled rows are skipped
        finally:
            await execute("DELETE FROM documents WHERE id IN (?, ?)", (legacy, current))
            await close_db()

    asyncio.run(explain_and_cleanup())


def test_filtered_hnsw_returns_top_k_with_iterative_scan():
    """A document filter must not starve an HNSW scan of results.

    400 distractor chunks sit right next to the query; the 10 target chunks are
    far away. With HNSW forced and ``hnsw.iterative_scan = off`` the first
    ``ef_search`` (40) candidates are all distractors, so the filter leaves too
    few rows. Pooled connections use ``strict_order`` and must return ``top_k``.
    """
    import backend.database as database
    from backend.database import close_db, execute, init_db

    tag = uuid.uuid4().hex[:8]
    target, distractor = f"target-{tag}", f"distractor-{tag}"
    near = "(SELECT array_agg(CASE WHEN g = 1 THEN 1.0 ELSE random() * 0.01 END)::real[]::vector(1536) FROM generate_series(1, 1536) g WHERE i >= 0)"
    far = "(SELECT array_agg(CASE WHEN g = 2 THEN 1.0 WHEN g = 1 THEN 0.05 ELSE random() * 0.01 END)::real[]::vector(1536) FROM generate_series(1, 1536) g WHERE i >= 0)"
    query = "[" + ",".join(["1"] + ["0"] * 1535) + "]"
    sql = (
        "SELECT c.id FROM document_chunks c JOIN documents d ON c.document_id = d.id "
        "WHERE (c.owner_id = %s OR d.workspace_id = %s) AND c.document_id IN (%s) AND c.embedding IS NOT NULL "
        "ORDER BY c.embedding <=> %s::vector LIMIT 8"
    )

    async def scenario() -> dict[str, int]:
        await init_db()
        try:
            for doc_id in (target, distractor):
                await execute(
                    "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status) "
                    "VALUES (?, 'o', 'f.txt', 'openai', 'text-embedding-3-small', 'text/plain', ?, 'ready')",
                    (doc_id, doc_id),
                )
            await execute(
                f"INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding) "
                f"SELECT ? || ':' || i, ?, 'o', i, 'd', {near} FROM generate_series(0, 399) i",
                (distractor, distractor),
            )
            await execute(
                f"INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding) "
                f"SELECT ? || ':' || i, ?, 'o', i, 't', {far} FROM generate_series(0, 9) i",
                (target, target),
            )
            counts: dict[str, int] = {}
            async with database._pg_pool.connection() as conn:
                # DDL is transactional: hide the document_id btree inside a
                # rolled-back transaction so the planner must use HNSW for the
                # app's exact query shape (as it does on large corpora).
                async with conn.transaction(force_rollback=True), conn.cursor() as cur:
                    await cur.execute("DROP INDEX idx_document_chunks_document")
                    await cur.execute("SET LOCAL enable_seqscan = off")
                    await cur.execute("SET LOCAL enable_bitmapscan = off")
                    for mode in ("off", "strict_order"):
                        await cur.execute(f"SET LOCAL hnsw.iterative_scan = {mode}")
                        await cur.execute("EXPLAIN (COSTS OFF) " + sql, ("o", "", target, query))
                        plan = "\n".join(r["QUERY PLAN"] for r in await cur.fetchall())
                        assert "idx_document_chunks_embedding_hnsw" in plan, plan
                        await cur.execute(sql, ("o", "", target, query))
                        counts[mode] = len(await cur.fetchall())
            return counts
        finally:
            await execute("DELETE FROM documents WHERE id IN (?, ?)", (target, distractor))
            await close_db()

    counts = asyncio.run(scenario())
    assert counts["off"] < 8, counts  # proves the scenario reproduces the starvation
    assert counts["strict_order"] == 8, counts
