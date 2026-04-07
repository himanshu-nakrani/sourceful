"""Document ingestion endpoints backed by durable jobs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from backend.errors import api_error_response
from backend.models import IngestResponse
from backend.routers.deps import RequestContext, get_request_context, require_provider_api_key
from backend.services.extract import FileValidationError, validate_upload
from backend.services.jobs import enqueue_ingest_job
from backend.settings import settings

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(
    request: Request,
    provider: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    embedding_model: str = Form(""),
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    if provider not in {"openai", "gemini"}:
        return api_error_response(
            request=request,
            status_code=400,
            error="Invalid provider.",
            code="INVALID_PROVIDER",
            details={"provider": provider},
        )
    if not file.filename:
        return api_error_response(
            request=request,
            status_code=400,
            error="A document file is required.",
            code="MISSING_FILE",
        )

    model_name = embedding_model.strip()
    if not model_name:
        model_name = (
            settings.default_embedding_model_openai
            if provider == "openai"
            else settings.default_embedding_model_gemini
        )
    if len(model_name) > settings.max_model_name_length:
        return api_error_response(
            request=request,
            status_code=400,
            error="Embedding model id is too long.",
            code="INVALID_EMBEDDING_MODEL",
        )

    raw = await file.read()
    if len(raw) > settings.max_document_bytes:
        return api_error_response(
            request=request,
            status_code=413,
            error="File too large.",
            code="FILE_TOO_LARGE",
            details={"max_document_bytes": settings.max_document_bytes},
        )

    try:
        validated = validate_upload(file.filename, raw, file.content_type)
    except FileValidationError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="INVALID_FILE",
        )

    document, job, deduplicated = await enqueue_ingest_job(
        owner_id=context.owner_id,
        provider=provider,
        embedding_model=model_name,
        provider_api_key=provider_api_key,
        filename=file.filename,
        mime_type=validated.mime_type,
        checksum=validated.checksum,
        raw=raw,
    )
    status = document.get("status", "queued")
    return IngestResponse(
        document_id=document["id"],
        job_id=job["id"] if job else document.get("current_job_id"),
        status=status,
        embedding_model=model_name,
        deduplicated=deduplicated,
    )
