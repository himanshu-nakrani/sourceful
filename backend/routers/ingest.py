"""Document ingestion endpoint with background processing."""

import asyncio
import logging
import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse

from backend.database import execute
from backend.services.chunking import chunk_text
from backend.services.embeddings import embed_texts_gemini_sync, embed_texts_openai
from backend.services.extract import extract_text
from backend.services import vectorstore
from backend.settings import settings

logger = logging.getLogger("ragapp")
router = APIRouter()

MAX_MODEL_LEN = 128


def _parse_provider(raw: str) -> str | None:
    if raw in ("openai", "gemini"):
        return raw
    return None


async def _process_document(
    document_id: str,
    provider: str,
    api_key: str,
    emb_model: str,
    filename: str,
    raw: bytes,
) -> None:
    """Background task: extract, chunk, embed, store."""
    try:
        text = await asyncio.to_thread(extract_text, filename=filename, raw=raw)

        chunks = await asyncio.to_thread(
            chunk_text,
            text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        if not chunks:
            await execute(
                "UPDATE documents SET status = 'error', error_message = ? WHERE id = ?",
                ("No text content to index after processing.", document_id),
            )
            return

        if len(chunks) > settings.max_chunks:
            await execute(
                "UPDATE documents SET status = 'error', error_message = ? WHERE id = ?",
                (
                    f"Document splits into too many chunks ({len(chunks)}). "
                    f"Maximum is {settings.max_chunks}. Try a smaller file or increase CHUNK_SIZE.",
                    document_id,
                ),
            )
            return

        # Embed
        if provider == "openai":
            embeddings = await embed_texts_openai(api_key, emb_model, chunks)
        else:
            embeddings = await asyncio.to_thread(
                embed_texts_gemini_sync,
                api_key,
                emb_model,
                chunks,
            )

        # Store vectors
        await vectorstore.add_chunks(document_id, chunks, embeddings)

        # Mark ready
        await execute(
            "UPDATE documents SET status = 'ready', chunk_count = ? WHERE id = ?",
            (len(chunks), document_id),
        )
        logger.info("Document %s indexed: %d chunks", document_id, len(chunks))

    except Exception as e:
        logger.exception("Background indexing failed for %s", document_id)
        await execute(
            "UPDATE documents SET status = 'error', error_message = ? WHERE id = ?",
            (str(e)[:500], document_id),
        )


@router.post("/ingest", response_model=None)
async def ingest(
    provider: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    embedding_model: str = Form(""),
    authorization: Annotated[str | None, Header()] = None,
):
    # ---- Auth ----
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Missing or invalid Authorization header (use Bearer token)."
            },
        )
    api_key = authorization.removeprefix("Bearer ").strip()
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "Missing API key."})

    # ---- Validate provider ----
    p = _parse_provider(provider)
    if not p:
        return JSONResponse(
            status_code=400,
            content={
                "error": 'Invalid or missing provider (use "openai" or "gemini").'
            },
        )

    # ---- Validate file ----
    if not file.filename:
        return JSONResponse(
            status_code=400, content={"error": "A document file is required."}
        )

    suffix = PurePath(file.filename.lower()).suffix
    if suffix not in settings.allowed_extensions:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unsupported file type: {suffix}. Allowed: {settings.allowed_file_types}"
            },
        )

    # ---- Validate embedding model ----
    emb = embedding_model.strip()
    if len(emb) > MAX_MODEL_LEN:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Embedding model id is too long (max {MAX_MODEL_LEN} characters)."
            },
        )
    if not emb:
        emb = (
            settings.default_embedding_model_openai
            if p == "openai"
            else settings.default_embedding_model_gemini
        )

    # ---- Read file ----
    max_bytes = settings.max_document_bytes
    raw = await file.read()
    if len(raw) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={"error": f"File too large (max {max_bytes // 1024 // 1024} MB)."},
        )

    # ---- Create document record ----
    document_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO documents (id, filename, provider, embedding_model, file_size, status) "
        "VALUES (?, ?, ?, ?, ?, 'processing')",
        (document_id, file.filename, p, emb, len(raw)),
    )

    # ---- Launch background processing ----
    asyncio.create_task(
        _process_document(document_id, p, api_key, emb, file.filename, raw)
    )

    return JSONResponse(
        status_code=202,
        content={
            "document_id": document_id,
            "status": "processing",
            "embedding_model": emb,
        },
    )
