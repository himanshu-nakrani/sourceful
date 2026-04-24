"""Workspace CRUD and source endpoints (Phase 0 + Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.errors import api_error_response
from backend.models import (
    CreateUrlSourceRequest,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceSourceListResponse,
    WorkspaceSourceResponse,
)
from backend.routers.deps import RequestContext, get_request_context
from backend.services import workspace_service

router = APIRouter()


def _not_found(request: Request, workspace_id: str):
    return api_error_response(
        request=request,
        status_code=404,
        error="Workspace not found.",
        code="WORKSPACE_NOT_FOUND",
        details={"workspace_id": workspace_id},
    )


@router.get("/workspaces", response_model=WorkspaceListResponse)
async def list_workspaces(
    include_archived: bool = False,
    context: RequestContext = Depends(get_request_context),
):
    # Ensure the caller always has a default workspace to land in.
    await workspace_service.ensure_default_workspace(context.owner_id)
    items = await workspace_service.list_workspaces(
        context.owner_id, include_archived=include_archived
    )
    return WorkspaceListResponse(
        workspaces=[WorkspaceResponse(**item) for item in items]
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    try:
        created = await workspace_service.create_workspace(
            context.owner_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="WORKSPACE_INVALID",
        )
    return WorkspaceResponse(**created)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)
    return WorkspaceResponse(**workspace)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    try:
        updated = await workspace_service.update_workspace(
            workspace_id,
            context.owner_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            archived=body.archived,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="WORKSPACE_INVALID",
        )
    if not updated:
        return _not_found(request, workspace_id)
    return WorkspaceResponse(**updated)


@router.get(
    "/workspaces/{workspace_id}/sources",
    response_model=WorkspaceSourceListResponse,
)
async def list_workspace_sources(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)
    sources = await workspace_service.list_sources(workspace_id)
    return WorkspaceSourceListResponse(
        sources=[WorkspaceSourceResponse(**s) for s in sources]
    )


@router.get(
    "/workspaces/{workspace_id}/sources/{source_id}",
    response_model=WorkspaceSourceResponse,
)
async def get_workspace_source(
    workspace_id: str,
    source_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)
    source = await workspace_service.get_source(source_id, workspace_id)
    if not source:
        return api_error_response(
            request=request,
            status_code=404,
            error="Source not found.",
            code="SOURCE_NOT_FOUND",
            details={"source_id": source_id},
        )
    return WorkspaceSourceResponse(**source)


@router.post(
    "/workspaces/{workspace_id}/sources/url",
    response_model=WorkspaceSourceResponse,
    status_code=202,
)
async def create_url_source(
    workspace_id: str,
    body: CreateUrlSourceRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    """Phase 1: queue a URL ingestion job and return the created source record.

    The URL is fetched synchronously to validate reachability, then handed off
    to the existing durable ingestion job pipeline (the worker chunks/embeds
    asynchronously). The workspace source row mirrors the document lifecycle.
    """
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)

    from backend.services.url_ingest import (
        UrlIngestError,
        enqueue_url_source,
    )

    try:
        source = await enqueue_url_source(
            workspace_id=workspace_id,
            owner_scope=context.owner_id,
            url=body.url,
            title=body.title,
            provider=body.provider,
            embedding_model=body.embedding_model,
            provider_api_key=(
                request.headers.get("x-provider-api-key", "").strip() or None
            ),
        )
    except UrlIngestError as exc:
        return api_error_response(
            request=request,
            status_code=exc.status_code,
            error=str(exc),
            code=exc.code,
            details=exc.details,
        )
    return WorkspaceSourceResponse(**source)
