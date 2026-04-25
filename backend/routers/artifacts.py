"""Phase 2: workspace artifacts endpoints (notes + saved answers + briefs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.errors import api_error_response
from backend.models import (
    ArtifactListResponse,
    ArtifactResponse,
    CreateArtifactRequest,
    SaveAssistantMessageRequest,
    UpdateArtifactRequest,
)
from backend.routers.deps import RequestContext, get_request_context
from backend.services import artifacts as artifact_service
from backend.services.workspace_rbac import check_workspace_role

router = APIRouter()


@router.get(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactListResponse,
)
async def list_workspace_artifacts(
    workspace_id: str,
    request: Request,
    artifact_type: str | None = None,
    context: RequestContext = Depends(get_request_context),
):
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="viewer"
    )
    if err:
        return err
    try:
        items = await artifact_service.list_artifacts(
            workspace_id, artifact_type=artifact_type
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="ARTIFACT_INVALID",
        )
    return ArtifactListResponse(artifacts=[ArtifactResponse(**a) for a in items])


@router.post(
    "/workspaces/{workspace_id}/artifacts",
    response_model=ArtifactResponse,
    status_code=201,
)
async def create_workspace_artifact(
    workspace_id: str,
    body: CreateArtifactRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err
    try:
        created = await artifact_service.create_artifact(
            workspace_id,
            artifact_type=body.artifact_type,
            title=body.title,
            content=body.content,
            metadata=body.metadata,
            source_message_id=body.source_message_id,
            created_by=context.user_id or context.owner_id,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="ARTIFACT_INVALID",
        )
    return ArtifactResponse(**created)


@router.get(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def get_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="viewer"
    )
    if err:
        return err
    item = await artifact_service.get_artifact(artifact_id, workspace_id)
    if not item:
        return api_error_response(
            request=request,
            status_code=404,
            error="Artifact not found.",
            code="ARTIFACT_NOT_FOUND",
            details={"artifact_id": artifact_id},
        )
    return ArtifactResponse(**item)


@router.patch(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
)
async def update_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    body: UpdateArtifactRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err
    try:
        updated = await artifact_service.update_artifact(
            artifact_id,
            workspace_id,
            title=body.title,
            content=body.content,
            metadata=body.metadata,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="ARTIFACT_INVALID",
        )
    if not updated:
        return api_error_response(
            request=request,
            status_code=404,
            error="Artifact not found.",
            code="ARTIFACT_NOT_FOUND",
            details={"artifact_id": artifact_id},
        )
    return ArtifactResponse(**updated)


@router.delete(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}",
    status_code=204,
)
async def delete_workspace_artifact(
    workspace_id: str,
    artifact_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err
    deleted = await artifact_service.delete_artifact(artifact_id, workspace_id)
    if not deleted:
        return api_error_response(
            request=request,
            status_code=404,
            error="Artifact not found.",
            code="ARTIFACT_NOT_FOUND",
            details={"artifact_id": artifact_id},
        )
    return None


@router.post(
    "/workspaces/{workspace_id}/artifacts/from-message",
    response_model=ArtifactResponse,
    status_code=201,
)
async def save_assistant_message_as_artifact(
    workspace_id: str,
    body: SaveAssistantMessageRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    """Convert a stored assistant message into a saved-answer artifact.

    The assistant content is loaded from ``messages`` (verifying it belongs to
    a conversation in this workspace), then persisted as a ``saved_answer``
    artifact. The original ``message_id`` is captured for traceability.
    """
    from backend.database import fetch_one as _fetch_one

    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="editor"
    )
    if err:
        return err

    row = await _fetch_one(
        """
        SELECT m.id, m.role, m.content, m.conversation_id, c.workspace_id
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE m.id = ? AND m.owner_id = ?
        """,
        (body.message_id, context.owner_id),
    )
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Message not found.",
            code="MESSAGE_NOT_FOUND",
            details={"message_id": body.message_id},
        )
    if row.get("role") != "assistant":
        return api_error_response(
            request=request,
            status_code=400,
            error="Only assistant messages can be saved as artifacts.",
            code="MESSAGE_NOT_ASSISTANT",
        )
    if row.get("workspace_id") and row["workspace_id"] != workspace_id:
        return api_error_response(
            request=request,
            status_code=400,
            error="Message does not belong to this workspace.",
            code="MESSAGE_WORKSPACE_MISMATCH",
        )

    artifact_type = body.artifact_type or "saved_answer"
    title = body.title or (row["content"][:80] + ("..." if len(row["content"]) > 80 else ""))
    try:
        created = await artifact_service.create_artifact(
            workspace_id,
            artifact_type=artifact_type,
            title=title,
            content=row["content"],
            metadata={"conversation_id": row["conversation_id"]},
            source_message_id=row["id"],
            created_by=context.user_id or context.owner_id,
        )
    except ValueError as exc:
        return api_error_response(
            request=request,
            status_code=400,
            error=str(exc),
            code="ARTIFACT_INVALID",
        )
    return ArtifactResponse(**created)
