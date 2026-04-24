"""Document management endpoints with owner scoping and chunk previews."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.models import (
    ChunkPreviewResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    IngestResponse,
    StructuredExtractRequest,
    StructuredExtractResponse,
)
from backend.routers.deps import RequestContext, get_request_context
from backend.services.provider_auth import MissingProviderApiKeyError
from backend.services.jobs import enqueue_reprocess_job
from backend.services.vectorstore import preview_chunks

router = APIRouter()


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(context: RequestContext = Depends(get_request_context)):
    rows = await fetch_all(
        """
        SELECT id, filename, provider, embedding_model, mime_type, checksum, chunk_count,
               file_size, page_count, status, current_job_id, created_at, processed_at, last_error,
               workspace_id,
               (SELECT stage FROM document_jobs WHERE id = documents.current_job_id) AS current_stage,
               (SELECT id FROM document_jobs WHERE document_id = documents.id AND owner_id = documents.owner_id ORDER BY created_at DESC LIMIT 1) AS last_job_id
        FROM documents
        WHERE owner_id = ?
        ORDER BY created_at DESC
        LIMIT 200
        """,
        (context.owner_id,),
    )
    return DocumentListResponse(documents=[DocumentResponse(**row) for row in rows])


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one(
        """
        SELECT id, filename, provider, embedding_model, mime_type, checksum, chunk_count,
               file_size, page_count, status, current_job_id, created_at, processed_at, last_error,
               workspace_id,
               (SELECT stage FROM document_jobs WHERE id = documents.current_job_id) AS current_stage,
               (SELECT id FROM document_jobs WHERE document_id = documents.id AND owner_id = documents.owner_id ORDER BY created_at DESC LIMIT 1) AS last_job_id
        FROM documents WHERE id = ? AND owner_id = ?
        """,
        (document_id, context.owner_id),
    )
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document not found.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    return DocumentResponse(**row)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one(
        """
        SELECT status, chunk_count, current_job_id, last_error,
               (SELECT stage FROM document_jobs WHERE id = documents.current_job_id) AS current_stage,
               (SELECT id FROM document_jobs WHERE document_id = documents.id AND owner_id = documents.owner_id ORDER BY created_at DESC LIMIT 1) AS last_job_id
        FROM documents
        WHERE id = ? AND owner_id = ?
        """,
        (document_id, context.owner_id),
    )
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document not found.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    return DocumentStatusResponse(**row)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkPreviewResponse])
async def get_document_chunks(document_id: str, context: RequestContext = Depends(get_request_context)):
    rows = await preview_chunks(document_id, context.owner_id)
    return [ChunkPreviewResponse(**row) for row in rows]


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one(
        """
        SELECT id, filename, mime_type, file_bytes
        FROM documents
        WHERE id = ? AND owner_id = ?
        """,
        (document_id, context.owner_id),
    )
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document not found.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )

    raw = row.get("file_bytes")
    if raw is None:
        latest_job = await fetch_one(
            """
            SELECT payload_bytes
            FROM document_jobs
            WHERE document_id = ? AND owner_id = ? AND payload_bytes IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id, context.owner_id),
        )
        raw = latest_job.get("payload_bytes") if latest_job else None
    if raw is None:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document content is unavailable. Re-upload the document to make notebook viewing available.",
            code="DOCUMENT_CONTENT_UNAVAILABLE",
            details={"document_id": document_id},
        )

    filename = str(row.get("filename") or "document")
    content_disposition = f"inline; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=bytes(raw),
        media_type=str(row.get("mime_type") or "application/octet-stream"),
        headers={"Content-Disposition": content_disposition},
    )


@router.post("/documents/{document_id}/reprocess", response_model=IngestResponse, status_code=202)
async def reprocess_document(
    document_id: str,
    request: Request,
    embedding_model: str | None = None,
    x_provider_api_key: str | None = Header(default=None),
    context: RequestContext = Depends(get_request_context),
):
    try:
        document, job = await enqueue_reprocess_job(
            owner_id=context.owner_id,
            document_id=document_id,
            provider_api_key=(x_provider_api_key or "").strip(),
            embedding_model=embedding_model,
        )
    except MissingProviderApiKeyError:
        return api_error_response(
            request=request,
            status_code=401,
            error="Missing X-Provider-Api-Key header.",
            code="MISSING_PROVIDER_API_KEY",
            details={"document_id": document_id},
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=404,
            error=str(exc),
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )

    return IngestResponse(
        document_id=document["id"],
        job_id=job["id"],
        status="queued",
        embedding_model=job["embedding_model"],
    )


@router.post("/documents/{document_id}/extract", response_model=StructuredExtractResponse)
async def extract_document_fields(
    document_id: str,
    body: StructuredExtractRequest,
    request: Request,
    x_provider_api_key: str | None = Header(default=None),
    context: RequestContext = Depends(get_request_context),
):
    """Phase 2.6: Extract structured fields from a document via LLM.

    Requires the document to be in ``ready`` state. Assembles the document
    text from stored chunks and passes it through the structured extraction
    service with the user-provided schema.
    """
    doc = await fetch_one(
        "SELECT id, status, provider FROM documents WHERE id = ? AND owner_id = ?",
        (document_id, context.owner_id),
    )
    if not doc:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document not found.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    if doc["status"] != "ready":
        return api_error_response(
            request=request,
            status_code=400,
            error=f"Document is not ready (status: {doc['status']}). Wait for processing to complete.",
            code="DOCUMENT_NOT_READY",
            details={"document_id": document_id, "status": doc["status"]},
        )

    api_key = (x_provider_api_key or "").strip()
    if not api_key:
        return api_error_response(
            request=request,
            status_code=401,
            error="Missing X-Provider-Api-Key header.",
            code="MISSING_PROVIDER_API_KEY",
            details={"document_id": document_id},
        )

    # Assemble document text from chunks
    chunk_rows = await fetch_all(
        "SELECT content FROM document_chunks WHERE document_id = ? AND owner_id = ? ORDER BY chunk_index ASC",
        (document_id, context.owner_id),
    )
    if not chunk_rows:
        return api_error_response(
            request=request,
            status_code=400,
            error="Document has no chunks.",
            code="NO_CHUNKS",
            details={"document_id": document_id},
        )

    document_text = "\n\n".join(row["content"] for row in chunk_rows)

    from backend.services.structured_extract import extract_fields

    result = await extract_fields(
        document_text=document_text,
        schema=body.schema_fields,
        provider=body.provider,
        api_key=api_key,
        model=body.model,
    )

    # Persist extracted fields on the document for downstream use
    import json
    await execute(
        "UPDATE documents SET last_error = NULL WHERE id = ? AND owner_id = ?",
        (document_id, context.owner_id),
    )

    return StructuredExtractResponse(
        document_id=document_id,
        fields=result.fields,
        model=result.model,
        token_usage=result.token_usage,
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one("SELECT id FROM documents WHERE id = ? AND owner_id = ?", (document_id, context.owner_id))
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Document not found.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    await execute("DELETE FROM documents WHERE id = ? AND owner_id = ?", (document_id, context.owner_id))
    return {"status": "deleted", "document_id": document_id}
