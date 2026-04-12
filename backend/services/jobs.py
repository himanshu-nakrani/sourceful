"""Durable document job helpers and worker processing."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import uuid

from backend.database import execute, execute_returning, fetch_all, fetch_one
from backend.metrics import metrics
from backend.services.chunking import chunk_sections
from backend.services.embeddings import embed_texts
from backend.services.extract import extract_document
from backend.services.provider_auth import require_provider_api_key
from backend.services.vectorstore import replace_chunks
from backend.settings import settings

logger = logging.getLogger("ragapp.jobs")
TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"


async def enqueue_ingest_job(
    *,
    owner_id: str,
    provider: str,
    embedding_model: str,
    provider_api_key: str,
    filename: str,
    mime_type: str,
    checksum: str,
    raw: bytes,
) -> tuple[dict, dict | None, bool]:
    existing = await fetch_one(
        """
        SELECT * FROM documents
        WHERE owner_id = ? AND checksum = ? AND provider = ? AND embedding_model = ?
        """,
        (owner_id, checksum, provider, embedding_model),
    )
    if existing and existing["status"] in {"ready", "queued", "processing"}:
        job = None
        if existing.get("current_job_id"):
            job = await fetch_one(
                "SELECT * FROM document_jobs WHERE id = ? AND owner_id = ?",
                (existing["current_job_id"], owner_id),
            )
        return existing, job, True

    if existing:
        document_id = existing["id"]
        await execute(
            "UPDATE documents SET status = 'queued', current_job_id = NULL, last_error = NULL WHERE id = ? AND owner_id = ?",
            (document_id, owner_id),
        )
    else:
        document_id = str(uuid.uuid4())
        await execute(
            """
            INSERT INTO documents (
                id, owner_id, filename, provider, embedding_model, mime_type, checksum, file_size, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
            """,
            (document_id, owner_id, filename, provider, embedding_model, mime_type, checksum, len(raw)),
        )

    job_id = str(uuid.uuid4())
    await execute(
        f"""
        INSERT INTO document_jobs (
            id, document_id, owner_id, provider, embedding_model, status, stage, progress,
            payload_filename, payload_mime_type, payload_bytes, provider_api_key, updated_at, next_retry_at, terminal
        ) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?, ?, ?, {TIMESTAMP_SQL}, NULL, FALSE)
        """,
        (job_id, document_id, owner_id, provider, embedding_model, filename, mime_type, raw, provider_api_key),
    )
    await execute(
        "UPDATE documents SET current_job_id = ?, status = 'queued' WHERE id = ? AND owner_id = ?",
        (job_id, document_id, owner_id),
    )
    document = await fetch_one("SELECT * FROM documents WHERE id = ? AND owner_id = ?", (document_id, owner_id))
    job = await fetch_one("SELECT * FROM document_jobs WHERE id = ? AND owner_id = ?", (job_id, owner_id))
    metrics.inc("ingest_jobs_total", status="queued")
    return document or {}, job, False


async def enqueue_reprocess_job(
    *,
    owner_id: str,
    document_id: str,
    provider_api_key: str | None,
    embedding_model: str | None = None,
) -> tuple[dict, dict]:
    document = await fetch_one(
        "SELECT * FROM documents WHERE id = ? AND owner_id = ?",
        (document_id, owner_id),
    )
    if not document:
        raise ValueError("Document not found.")

    latest_job = await fetch_one(
        "SELECT * FROM document_jobs WHERE document_id = ? AND owner_id = ? ORDER BY created_at DESC LIMIT 1",
        (document_id, owner_id),
    )
    payload_filename = document["filename"]
    payload_mime_type = document["mime_type"]
    payload_bytes = latest_job.get("payload_bytes") if latest_job else None
    model_name = embedding_model or document["embedding_model"]
    provider_key = require_provider_api_key(document["provider"], provider_api_key)

    job_id = str(uuid.uuid4())
    await execute(
        f"""
        INSERT INTO document_jobs (
            id, document_id, owner_id, provider, embedding_model, status, stage, progress,
            payload_filename, payload_mime_type, payload_bytes, provider_api_key, updated_at, next_retry_at, terminal
        ) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?, ?, ?, {TIMESTAMP_SQL}, NULL, FALSE)
        """,
        (
            job_id,
            document_id,
            owner_id,
            document["provider"],
            model_name,
            payload_filename,
            payload_mime_type,
            payload_bytes,
            provider_key,
        ),
    )
    await execute(
        "UPDATE documents SET current_job_id = ?, status = 'queued', embedding_model = ?, last_error = NULL WHERE id = ? AND owner_id = ?",
        (job_id, model_name, document_id, owner_id),
    )
    job = await fetch_one("SELECT * FROM document_jobs WHERE id = ? AND owner_id = ?", (job_id, owner_id))
    metrics.inc("ingest_jobs_total", status="queued")
    return document, job or {}


async def claim_next_job() -> dict | None:
    retry_due_sql = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"
    row = await fetch_one(
        f"""
        SELECT * FROM document_jobs
        WHERE status = 'queued'
          AND (next_retry_at IS NULL OR next_retry_at <= {retry_due_sql})
        ORDER BY created_at ASC
        LIMIT 1
        """
    )
    if not row:
        metrics.set_gauge("ingest_queue_depth", 0)
        return None

    updated = await execute_returning(
        f"""
        UPDATE document_jobs
        SET status = 'processing',
            stage = 'extracting',
            progress = 0.05,
            attempt_count = attempt_count + 1,
            started_at = COALESCE(started_at, {TIMESTAMP_SQL}),
            updated_at = {TIMESTAMP_SQL},
            next_retry_at = NULL
        WHERE id = ? AND status = 'queued'
        RETURNING *
        """,
        (row["id"],),
    )
    if updated:
        await execute(
            "UPDATE documents SET status = 'processing' WHERE id = ? AND owner_id = ?",
            (updated["document_id"], updated["owner_id"]),
        )
    remaining = await fetch_one("SELECT COUNT(*) AS count FROM document_jobs WHERE status = 'queued'")
    metrics.set_gauge("ingest_queue_depth", float((remaining or {}).get("count", 0)))
    return updated


async def get_job(owner_id: str, job_id: str) -> dict | None:
    return await fetch_one(
        "SELECT * FROM document_jobs WHERE id = ? AND owner_id = ?",
        (job_id, owner_id),
    )


async def process_job(job: dict) -> None:
    job_id = job["id"]
    document_id = job["document_id"]
    owner_id = job["owner_id"]
    started = datetime.now(timezone.utc)
    try:
        if job["provider"] == "vertex_search":
            await _process_vertex_search_job(job, job_id, document_id, owner_id, started)
            return

        chunks = await _build_chunks(job)
        await execute(
            f"UPDATE document_jobs SET stage = 'embedding', progress = 0.45, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
            (job_id,),
        )
        embeddings = await embed_texts(
            job["provider"],
            job["provider_api_key"],
            job["embedding_model"],
            [chunk.content for chunk in chunks],
        )
        await execute(
            f"UPDATE document_jobs SET stage = 'storing', progress = 0.8, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
            (job_id,),
        )
        await replace_chunks(document_id, owner_id, chunks, embeddings)

        page_count = await _resolve_page_count(job, chunks)
        await execute(
            f"""
            UPDATE documents
            SET status = 'ready',
                embedding_model = ?,
                chunk_count = ?,
                page_count = ?,
                processed_at = {TIMESTAMP_SQL},
                last_error = NULL
            WHERE id = ? AND owner_id = ?
            """,
            (job["embedding_model"], len(chunks), page_count, document_id, owner_id),
        )
        await execute(
            f"""
            UPDATE document_jobs
            SET status = 'ready',
                stage = 'complete',
                progress = 1,
                error_message = NULL,
                finished_at = {TIMESTAMP_SQL},
                updated_at = {TIMESTAMP_SQL},
                payload_bytes = NULL,
                provider_api_key = NULL,
                next_retry_at = NULL,
                terminal = FALSE
            WHERE id = ?
            """,
            (job_id,),
        )
        metrics.inc("ingest_jobs_total", status="ready")
        metrics.observe(
            "ingest_job_duration_ms",
            (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
            status="ready",
        )
    except Exception as exc:
        logger.exception("job_failed", extra={"job_id": job_id})
        error_message = str(exc)[:500]
        attempt_count = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        can_retry = attempt_count < max_attempts
        if can_retry:
            next_retry_at = _next_retry_timestamp(attempt_count)
            await execute(
                "UPDATE documents SET status = 'queued', last_error = ? WHERE id = ? AND owner_id = ?",
                (error_message, document_id, owner_id),
            )
            await execute(
                f"""
                UPDATE document_jobs
                SET status = 'queued',
                    stage = 'retry_scheduled',
                    error_message = ?,
                    progress = 0,
                    updated_at = {TIMESTAMP_SQL},
                    next_retry_at = ?,
                    terminal = FALSE
                WHERE id = ?
                """,
                (error_message, next_retry_at, job_id),
            )
            metrics.inc("ingest_jobs_total", status="retry_scheduled")
            metrics.inc("ingest_job_retries_total")
            metrics.observe(
                "ingest_job_duration_ms",
                (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
                status="retry_scheduled",
            )
            return

        await execute(
            "UPDATE documents SET status = 'error', last_error = ? WHERE id = ? AND owner_id = ?",
            (error_message, document_id, owner_id),
        )
        await execute(
            f"""
            UPDATE document_jobs
            SET status = 'error',
                stage = 'failed',
                error_message = ?,
                finished_at = {TIMESTAMP_SQL},
                updated_at = {TIMESTAMP_SQL},
                next_retry_at = NULL,
                terminal = TRUE,
                payload_bytes = NULL,
                provider_api_key = NULL
            WHERE id = ?
            """,
            (error_message, job_id),
        )
        metrics.inc("ingest_jobs_total", status="error")
        metrics.observe(
            "ingest_job_duration_ms",
            (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
            status="error",
        )


async def _process_vertex_search_job(
    job: dict, job_id: str, document_id: str, owner_id: str, started: datetime
) -> None:
    from backend.services.vertex_search import upload_document

    if not settings.vertex_search_configured:
        raise ValueError("Vertex AI Search is not configured. Set VERTEX_SEARCH_PROJECT and VERTEX_SEARCH_DATASTORE_ID.")

    payload_bytes = job.get("payload_bytes")
    if not payload_bytes:
        raise ValueError("No document payload available for Vertex AI Search upload.")

    await execute(
        f"UPDATE document_jobs SET stage = 'uploading', progress = 0.3, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
        (job_id,),
    )

    await asyncio.to_thread(
        upload_document,
        document_id,
        job["payload_filename"],
        bytes(payload_bytes),
        job["payload_mime_type"],
    )

    await execute(
        f"UPDATE document_jobs SET stage = 'storing', progress = 0.9, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
        (job_id,),
    )

    page_count = None
    try:
        extracted = extract_document(filename=job["payload_filename"], raw=bytes(payload_bytes))
        page_count = extracted.page_count
    except Exception:
        pass

    await execute(
        f"""
        UPDATE documents
        SET status = 'ready',
            embedding_model = ?,
            chunk_count = 0,
            page_count = ?,
            processed_at = {TIMESTAMP_SQL},
            last_error = NULL
        WHERE id = ? AND owner_id = ?
        """,
        (job["embedding_model"], page_count, document_id, owner_id),
    )
    await execute(
        f"""
        UPDATE document_jobs
        SET status = 'ready',
            stage = 'complete',
            progress = 1,
            error_message = NULL,
            finished_at = {TIMESTAMP_SQL},
            updated_at = {TIMESTAMP_SQL},
            payload_bytes = NULL,
            provider_api_key = NULL,
            next_retry_at = NULL,
            terminal = FALSE
        WHERE id = ?
        """,
        (job_id,),
    )
    metrics.inc("ingest_jobs_total", status="ready")
    metrics.observe(
        "ingest_job_duration_ms",
        (datetime.now(timezone.utc) - started).total_seconds() * 1000.0,
        status="ready",
    )


async def _build_chunks(job: dict):
    payload_bytes = job.get("payload_bytes")
    if payload_bytes:
        extracted = extract_document(filename=job["payload_filename"], raw=bytes(payload_bytes))
        chunks = chunk_sections(extracted.sections, settings.chunk_size, settings.chunk_overlap)
    else:
        existing_rows = await fetch_all(
            "SELECT chunk_index, content, page_number FROM document_chunks WHERE document_id = ? AND owner_id = ? ORDER BY chunk_index ASC",
            (job["document_id"], job["owner_id"]),
        )
        if not existing_rows:
            raise ValueError("No source payload or existing chunks are available for reprocessing.")
        from backend.services.chunking import ChunkPayload

        chunks = [
            ChunkPayload(
                chunk_index=int(row["chunk_index"]),
                content=row["content"],
                page_number=row.get("page_number"),
            )
            for row in existing_rows
        ]

    if not chunks:
        raise ValueError("No text content was extracted from the document.")
    if len(chunks) > settings.max_chunks:
        raise ValueError(
            f"Document splits into too many chunks ({len(chunks)}). Maximum is {settings.max_chunks}."
        )
    return chunks


async def _resolve_page_count(job: dict, chunks) -> int | None:
    if job.get("payload_bytes"):
        extracted = extract_document(filename=job["payload_filename"], raw=bytes(job["payload_bytes"]))
        return extracted.page_count
    pages = [chunk.page_number for chunk in chunks if chunk.page_number is not None]
    return max(pages) if pages else None


async def worker_forever(stop_event: asyncio.Event | None = None) -> None:
    while True:
        if stop_event and stop_event.is_set():
            return
        job = await claim_next_job()
        if job is None:
            await asyncio.sleep(settings.worker_poll_interval_seconds)
            continue
        await process_job(job)


def _next_retry_timestamp(attempt_count: int):
    # Exponential backoff in seconds: 5, 10, 20 ... capped at 120s.
    delay = min(120, 5 * (2 ** max(0, attempt_count - 1)))
    due = datetime.now(timezone.utc) + timedelta(seconds=delay)
    if settings.using_postgres:
        return due
    return due.strftime("%Y-%m-%d %H:%M:%S")
