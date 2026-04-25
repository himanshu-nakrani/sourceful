"""Workspace CRUD and source endpoints (Phase 0 + Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.errors import api_error_response
from backend.models import (
    CreateUrlSourceRequest,
    CreateWorkspaceInvitationRequest,
    CreateWorkspaceMemberRequest,
    CreateWorkspaceRequest,
    MyRoleResponse,
    SyncRunListResponse,
    SyncRunResponse,
    UpdateWorkspaceMemberRequest,
    UpdateWorkspaceRequest,
    WorkspaceInvitationListResponse,
    WorkspaceInvitationResponse,
    WorkspaceListResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceSourceListResponse,
    WorkspaceSourceResponse,
)
from backend.routers.deps import RequestContext, get_request_context
from backend.services import sync_runs, workspace_members, workspace_service
from backend.services.workspace_rbac import check_workspace_role

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


@router.get("/workspaces/{workspace_id}/my-role", response_model=MyRoleResponse)
async def get_my_workspace_role(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)
    role = await workspace_members.get_effective_role(
        workspace_id=workspace_id,
        workspace_owner_scope=workspace.get("owner_scope") or context.owner_id,
        caller_owner_scope=context.owner_id,
        caller_user_id=context.user_id,
    )
    return MyRoleResponse(role=role)


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
    "/workspaces/{workspace_id}/sources/{source_id}/reprocess",
    response_model=WorkspaceSourceResponse,
    status_code=202,
)
async def reprocess_workspace_source(
    workspace_id: str,
    source_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    """Phase 1 + Phase 3: refresh an indexed source.

    For URL sources we re-fetch the remote content, re-chunk, and re-embed. For
    file sources we replay the existing payload through the embedding pipeline.
    Both paths use the durable worker so progress is observable via document
    job status.
    """
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err
    source = await workspace_service.get_source(source_id, workspace_id)
    if not source:
        return api_error_response(
            request=request,
            status_code=404,
            error="Source not found.",
            code="SOURCE_NOT_FOUND",
            details={"source_id": source_id},
        )

    provider_api_key = (
        request.headers.get("x-provider-api-key", "").strip() or None
    )

    if source["source_type"] == "url":
        from backend.services.url_ingest import (
            UrlIngestError,
            refetch_url_source,
        )

        try:
            refreshed = await refetch_url_source(
                workspace_id=workspace_id,
                owner_scope=context.owner_id,
                source=source,
                provider_api_key=provider_api_key,
            )
        except UrlIngestError as exc:
            return api_error_response(
                request=request,
                status_code=exc.status_code,
                error=str(exc),
                code=exc.code,
                details=exc.details,
            )
        return WorkspaceSourceResponse(**refreshed)

    # File-backed sources: replay the existing payload via the durable worker.
    if not source.get("document_id"):
        return api_error_response(
            request=request,
            status_code=409,
            error="Source has no underlying document to reprocess.",
            code="SOURCE_INVALID",
        )
    from backend.services.jobs import enqueue_reprocess_job

    try:
        await enqueue_reprocess_job(
            owner_id=context.owner_id,
            document_id=source["document_id"],
            provider_api_key=provider_api_key or "",
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=404,
            error=str(exc),
            code="DOCUMENT_NOT_FOUND",
        )
    refreshed = await workspace_service.get_source(source_id, workspace_id)
    return WorkspaceSourceResponse(**(refreshed or source))


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
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err

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


# ---------- Phase 3: members + invitations + sync history ------------------


async def _require_workspace_role(
    *,
    workspace_id: str,
    request: Request,
    context: RequestContext,
    minimum: str,
):
    """Thin wrapper around the shared ``check_workspace_role`` helper.

    Kept under the original name so the existing member/invitation handlers
    don't need to change their call sites; new content routes (artifacts,
    sources, chat) go through the shared helper directly.
    """
    return await check_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum=minimum,
    )


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
)
async def list_workspace_members(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace:
        return _not_found(request, workspace_id)
    members = await workspace_members.list_members(workspace_id)
    return WorkspaceMemberListResponse(
        members=[WorkspaceMemberResponse(**m) for m in members]
    )


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
)
async def add_workspace_member(
    workspace_id: str,
    body: CreateWorkspaceMemberRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    try:
        member = await workspace_members.add_member(
            workspace_id, user_id=body.user_id, role=body.role
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="MEMBER_INVALID",
        )
    return WorkspaceMemberResponse(**member)


@router.patch(
    "/workspaces/{workspace_id}/members/{member_id}",
    response_model=WorkspaceMemberResponse,
)
async def update_workspace_member(
    workspace_id: str,
    member_id: str,
    body: UpdateWorkspaceMemberRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    try:
        member = await workspace_members.update_member_role(
            workspace_id, member_id=member_id, role=body.role
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="MEMBER_INVALID",
        )
    if not member:
        return api_error_response(
            request=request,
            status_code=404,
            error="Member not found.",
            code="MEMBER_NOT_FOUND",
            details={"member_id": member_id},
        )
    return WorkspaceMemberResponse(**member)


@router.delete(
    "/workspaces/{workspace_id}/members/{member_id}",
    status_code=204,
)
async def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    if not await workspace_members.remove_member(workspace_id, member_id):
        return api_error_response(
            request=request,
            status_code=404,
            error="Member not found.",
            code="MEMBER_NOT_FOUND",
            details={"member_id": member_id},
        )
    return None


@router.get(
    "/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationListResponse,
)
async def list_workspace_invitations(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    items = await workspace_members.list_invitations(workspace_id)
    return WorkspaceInvitationListResponse(
        invitations=[WorkspaceInvitationResponse(**i) for i in items]
    )


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationResponse,
    status_code=201,
)
async def create_workspace_invitation(
    workspace_id: str,
    body: CreateWorkspaceInvitationRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    try:
        invitation = await workspace_members.create_invitation(
            workspace_id,
            email=body.email,
            role=body.role,
            invited_by=context.user_id,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="INVITATION_INVALID",
        )
    return WorkspaceInvitationResponse(**invitation)


@router.delete(
    "/workspaces/{workspace_id}/invitations/{invitation_id}",
    status_code=204,
)
async def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    workspace, err = await _require_workspace_role(
        workspace_id=workspace_id,
        request=request,
        context=context,
        minimum="admin",
    )
    if err:
        return err
    if not await workspace_members.revoke_invitation(workspace_id, invitation_id):
        return api_error_response(
            request=request,
            status_code=404,
            error="Invitation not found.",
            code="INVITATION_NOT_FOUND",
            details={"invitation_id": invitation_id},
        )
    return None


@router.get(
    "/workspaces/{workspace_id}/sources/{source_id}/sync-runs",
    response_model=SyncRunListResponse,
)
async def list_source_sync_runs(
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
    runs = await sync_runs.list_runs(workspace_id=workspace_id, source_id=source_id)
    return SyncRunListResponse(runs=[SyncRunResponse(**r) for r in runs])
