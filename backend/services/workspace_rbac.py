"""Phase 3: shared RBAC helper for workspace content routes.

The Phase 0 ownership model — ``workspace.owner_scope`` — always grants the
``owner`` role to the matching caller, including anonymous sessions. On top
of that, authenticated users gain access via rows in ``workspace_members``
(see :mod:`backend.services.workspace_members`).

This module exposes one entry point, :func:`check_workspace_role`, that
mutating routes can call to enforce a minimum role. It returns either the
loaded workspace dict (caller proceeds) or an :class:`fastapi.Response` with
the appropriate 403/404 payload (caller returns it directly).

Why a service module rather than a FastAPI dependency?

- The role threshold varies per endpoint (chat → viewer, artifact write →
  editor, member management → admin), so a parameterized dependency would
  need a factory anyway.
- Several existing routes already follow the "load workspace, return
  ``api_error_response`` on failure" idiom; this helper keeps that shape so
  retrofits are mechanical.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from backend.database import fetch_one
from backend.errors import api_error_response
from backend.routers.deps import RequestContext
from backend.services import workspace_members, workspace_service


async def check_workspace_role(
    *,
    workspace_id: str,
    request: Request,
    context: RequestContext,
    minimum: str,
) -> tuple[dict[str, Any] | None, Any]:
    """Return ``(workspace, None)`` on success or ``(None, error_response)``.

    - 404 ``WORKSPACE_NOT_FOUND`` if the workspace doesn't exist or isn't
      visible to the caller's owner scope.
    - 403 ``WORKSPACE_FORBIDDEN`` if the caller has access but their role is
      below ``minimum``.

    The workspace dict matches what :func:`workspace_service.get_workspace`
    returns, so callers that already use that helper can drop their existing
    ``get_workspace`` + manual 404 block.
    """
    # First-pass: ownership check (the fast path for anonymous owners and
    # workspace owners who are also calling). For authenticated callers who
    # are *members* but not owners, this returns None — we fall through to a
    # second lookup that resolves the workspace by id and consults the
    # ``workspace_members`` table.
    workspace = await workspace_service.get_workspace(workspace_id, context.owner_id)
    if not workspace and context.user_id:
        membership_row = await fetch_one(
            """
            SELECT w.id, w.name, w.slug, w.description, w.visibility,
                   w.archived, w.is_default, w.owner_scope,
                   w.created_at, w.updated_at
            FROM workspaces w
            JOIN workspace_members m ON m.workspace_id = w.id
            WHERE w.id = ? AND m.user_id = ?
            """,
            (workspace_id, context.user_id),
        )
        if membership_row:
            workspace = dict(membership_row)
    if not workspace:
        return None, api_error_response(
            request=request,
            status_code=404,
            error="Workspace not found.",
            code="WORKSPACE_NOT_FOUND",
            details={"workspace_id": workspace_id},
        )
    # Fix #7: refuse to compute roles when owner_scope is missing. Legacy
    # rows with NULL owner_scope could accidentally grant "owner" to any
    # caller because the fallback `or context.owner_id` would match.
    workspace_owner_scope = workspace.get("owner_scope")
    if not workspace_owner_scope:
        return None, api_error_response(
            request=request,
            status_code=500,
            error="Workspace is missing owner_scope. Please contact support.",
            code="WORKSPACE_OWNER_SCOPE_MISSING",
            details={"workspace_id": workspace_id},
        )
    role = await workspace_members.get_effective_role(
        workspace_id=workspace_id,
        workspace_owner_scope=workspace_owner_scope,
        caller_owner_scope=context.owner_id,
        caller_user_id=context.user_id,
    )
    if not workspace_members.role_at_least(role, minimum):
        return None, api_error_response(
            request=request,
            status_code=403,
            error=f"This action requires '{minimum}' role on the workspace.",
            code="WORKSPACE_FORBIDDEN",
            details={"required_role": minimum, "current_role": role},
        )
    return workspace, None
