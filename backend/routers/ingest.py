"""Document ingestion endpoints backed by durable jobs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile

from backend.errors import api_error_response
from backend.models import IngestResponse
from backend.routers.deps import RequestContext, get_request_context
from backend.services import workspace_service
from backend.services.extract import FileValidationError, validate_upload
from backend.services.jobs import enqueue_ingest_job
from backend.services.provider_auth import normalize_provider_api_key, provider_requires_api_key
from backend.settings import settings

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(
    request: Request,
    provider: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    embedding_model: str = Form(""),
    workspace_id: str = Form(""),
    x_provider_api_key: str | None = Header(default=None),
    context: RequestContext = Depends(get_request_context),
):
    if provider not in {"openai", "gemini", "vertex_search"}:
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
        if provider == "openai":
            model_name = settings.default_embedding_model_openai
        elif provider == "gemini":
            model_name = settings.default_embedding_model_gemini
        else:
            model_name = settings.default_embedding_model_vertex_search
    if len(model_name) > settings.max_model_name_length:
        return api_error_response(
            request=request,
            status_code=400,
            error="Embedding model id is too long.",
            code="INVALID_EMBEDDING_MODEL",
        )
    provider_api_key = normalize_provider_api_key(x_provider_api_key)
    if provider_requires_api_key(provider) and not provider_api_key:
        return api_error_response(
            request=request,
            status_code=401,
            error="Missing X-Provider-Api-Key header.",
            code="MISSING_PROVIDER_API_KEY",
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

    # Resolve the target workspace. If the caller didn't specify one, bind to
    # the owner's default workspace so every document lives in a workspace
    # after Phase 0.
    target_workspace_id = workspace_id.strip() or None
    if target_workspace_id:
        ws = await workspace_service.get_workspace(target_workspace_id, context.owner_id)
        if not ws:
            return api_error_response(
                request=request,
                status_code=404,
                error="Workspace not found.",
                code="WORKSPACE_NOT_FOUND",
                details={"workspace_id": target_workspace_id},
            )
    else:
        default_ws = await workspace_service.ensure_default_workspace(context.owner_id)
        target_workspace_id = default_ws["id"]

    document, job, deduplicated = await enqueue_ingest_job(
        owner_id=context.owner_id,
        provider=provider,
        embedding_model=model_name,
        provider_api_key=provider_api_key,
        filename=file.filename,
        mime_type=validated.mime_type,
        checksum=validated.checksum,
        raw=raw,
        workspace_id=target_workspace_id,
    )
    status = document.get("status", "queued")
    # Mirror the document into workspace_sources for first-class source listing.
    await workspace_service.upsert_source_for_document(
        target_workspace_id,
        document_id=document["id"],
        source_title=document.get("filename") or file.filename,
        mime_type=document.get("mime_type"),
        status=status if status in {"queued", "processing", "ready", "error"} else "queued",
    )
    return IngestResponse(
        document_id=document["id"],
        job_id=job["id"] if job else document.get("current_job_id"),
        status=status,
        embedding_model=model_name,
        deduplicated=deduplicated,
    )
