"""Refreshing a URL source must index the newly fetched content.

Regression: ``refetch_url_source`` stored the new bytes on the document but
``enqueue_reprocess_job`` took its payload from the latest (completed) job,
whose ``payload_bytes`` had been cleared. The worker then re-embedded the old
stored chunks, so refreshed content was never indexed.

Citation stability: a refresh re-chunks the page. Chunk ids stay deterministic
(``{document_id}:{chunk_index}``), chunks beyond the new count are removed, and
past answers keep their quoted excerpts because ``messages.sources_json``
stores a copy of each citation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.services import url_ingest
from backend.services.embedding_spec import EMBEDDING_DIMENSIONS
from backend.settings import settings

OLD_TEXT = "The old page said the launch is in March."


def _old_chunk_params(doc_id: str, idx: int, owner: str):
    vector_col = "embedding" if settings.using_postgres else "embedding_json"
    vector = (
        "[" + ",".join(["0.1"] * EMBEDDING_DIMENSIONS) + "]"
        if settings.using_postgres
        else json.dumps([0.1] * EMBEDDING_DIMENSIONS)
    )
    cast = "?::vector" if settings.using_postgres else "?"
    sql = (
        f"INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, {vector_col}) "
        f"VALUES (?, ?, ?, ?, ?, {cast})"
    )
    return sql, (f"{doc_id}:{idx}", doc_id, owner, idx, f"{OLD_TEXT} (part {idx})", vector)


async def _process_jobs_for(doc_id: str) -> None:
    """Run only this document's queued jobs (the shared DB may hold others)."""
    from backend.database import fetch_all
    from backend.services.jobs import process_job

    jobs = await fetch_all(
        "SELECT * FROM document_jobs WHERE document_id = ? AND status = 'queued' ORDER BY created_at",
        (doc_id,),
    )
    with patch(
        "backend.services.jobs.embed_texts",
        new=AsyncMock(side_effect=lambda _p, _k, _m, texts: [[0.2] * EMBEDDING_DIMENSIONS for _ in texts]),
    ):
        for job in jobs:
            await process_job(dict(job))


def test_refetch_indexes_new_content_not_old_chunks():
    from backend.database import close_db, execute, fetch_all, fetch_one, init_db
    new_html = (
        b"<html><body><h1>Launch update</h1>"
        b"<p>The new page says the launch moved to September.</p></body></html>"
    )

    async def scenario():
        await init_db()
        owner, doc_id = f"o-{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
        try:
            await execute(
                "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status, chunk_count) "
                "VALUES (?, ?, 'Launch page.txt', 'openai', 'text-embedding-3-small', 'text/plain', 'old', 'ready', 3)",
                (doc_id, owner),
            )
            for idx in range(3):  # old version had 3 chunks
                sql, params = _old_chunk_params(doc_id, idx, owner)
                await execute(sql, params)
            # The completed ingest job's payload was cleared, as in production.
            await execute(
                "INSERT INTO document_jobs (id, document_id, owner_id, provider, embedding_model, status, stage, progress, "
                "payload_filename, payload_mime_type, payload_bytes, provider_api_key, terminal) "
                "VALUES (?, ?, ?, 'openai', 'text-embedding-3-small', 'ready', 'ready', 1, 'Launch page.txt', 'text/plain', NULL, NULL, TRUE)",
                (str(uuid.uuid4()), doc_id, owner),
            )
            source = {"id": "src", "source_type": "url", "source_url": "https://example.com/launch", "document_id": doc_id}
            with patch.object(
                url_ingest, "_fetch_url", new=AsyncMock(return_value=(new_html, "text/html", "https://example.com/launch"))
            ), patch("backend.services.sync_runs.start_run", new=AsyncMock(return_value="run")), patch(
                "backend.services.sync_runs.finish_run", new=AsyncMock()
            ), patch("backend.services.workspace_service.get_source", new=AsyncMock(return_value={})):
                await url_ingest.refetch_url_source(
                    workspace_id="w", owner_scope=owner, source=source, provider_api_key="k"
                )
            await _process_jobs_for(doc_id)
            chunks = await fetch_all(
                "SELECT id, chunk_index, content FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
                (doc_id,),
            )
            doc = await fetch_one("SELECT status, chunk_count, checksum FROM documents WHERE id = ?", (doc_id,))
            return doc_id, chunks, doc
        finally:
            await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            await close_db()

    doc_id, chunks, doc = asyncio.run(scenario())
    text = "\n".join(c["content"] for c in chunks)
    assert "moved to September" in text
    assert "March" not in text  # the old content is gone from the index
    assert doc["status"] == "ready" and doc["chunk_count"] == len(chunks)
    assert doc["checksum"] != "old"
    # Deterministic ids; the stale chunks from the longer old version are removed.
    assert [c["id"] for c in chunks] == [f"{doc_id}:{i}" for i in range(len(chunks))]
    assert len(chunks) < 3


@pytest.mark.parametrize(
    ("filename", "mime", "expected"),
    [
        ("page.txt", "text/plain", "page.txt"),
        ("report.pdf", "application/pdf", "report.pdf"),
        ("report.pdf", "text/plain", "report.txt"),  # URL now serves HTML
        ("page.txt", "application/pdf", "page.pdf"),  # URL now serves a PDF
        ("Launch page", "text/plain", "Launch page.txt"),
    ],
)
def test_refetch_filename_matches_fetched_type(filename, mime, expected):
    assert url_ingest._filename_for_mime(filename, mime) == expected


def test_format_switch_keeps_filename_with_payload():
    """Text URL now serving a PDF: the stored filename and any reprocess that
    copies the queued refresh payload must use the .pdf name."""
    from backend.database import close_db, execute, fetch_one, init_db
    from backend.services.jobs import enqueue_reprocess_job

    async def scenario():
        await init_db()
        owner, doc_id = f"o-{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
        try:
            await execute(
                "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status) "
                "VALUES (?, ?, 'Spec.txt', 'openai', 'text-embedding-3-small', 'text/plain', 'old', 'ready')",
                (doc_id, owner),
            )
            source = {"id": "src", "source_type": "url", "source_url": "https://example.com/spec", "document_id": doc_id}
            with patch.object(
                url_ingest, "_fetch_url", new=AsyncMock(return_value=(b"%PDF-1.4 fake", "application/pdf", "https://example.com/spec"))
            ), patch("backend.services.sync_runs.start_run", new=AsyncMock(return_value="run")), patch(
                "backend.services.sync_runs.finish_run", new=AsyncMock()
            ), patch("backend.services.workspace_service.get_source", new=AsyncMock(return_value={})):
                await url_ingest.refetch_url_source(workspace_id="w", owner_scope=owner, source=source, provider_api_key="k")
            doc = await fetch_one("SELECT filename, mime_type FROM documents WHERE id = ?", (doc_id,))
            # A manual reprocess while the refresh is still queued copies its payload.
            _, job = await enqueue_reprocess_job(owner_id=owner, document_id=doc_id, provider_api_key="k")
            return doc, job
        finally:
            await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            await close_db()

    doc, job = asyncio.run(scenario())
    assert doc["filename"] == "Spec.pdf" and doc["mime_type"] == "application/pdf"
    assert job["payload_filename"] == "Spec.pdf"
    assert job["payload_mime_type"] == "application/pdf"
    assert bytes(job["payload_bytes"]).startswith(b"%PDF")
