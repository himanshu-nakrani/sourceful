"""Phase 3: RBAC enforcement on workspace content routes.

These tests exercise the shared ``check_workspace_role`` helper directly
because the existing test stack uses anonymous ``X-Client-Session`` access
(which always resolves to the workspace owner). For the role tiers below
``owner``, we drive the helper with a synthesized ``RequestContext`` pointing
at an authenticated user that has been seeded as a workspace member.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from backend.database import execute, fetch_one
from backend.routers.deps import RequestContext
from backend.services import workspace_members, workspace_service
from backend.services.workspace_rbac import check_workspace_role


def _request() -> Request:
    """Build a minimal Request stand-in that satisfies ``api_error_response``."""
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = "rbac-test"
    request.url = MagicMock()
    request.url.path = "/test"
    request.method = "POST"
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


async def _seed_workspace(*, owner_scope: str) -> str:
    workspace = await workspace_service.create_workspace(
        owner_scope,
        name="rbac-ws",
        description=None,
        visibility="private",
    )
    return workspace["id"]


async def _seed_user(user_id: str, email: str) -> None:
    await execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, is_verified)
        VALUES (?, ?, 'x', 'user', 1, 1)
        """,
        (user_id, email),
    )


def _ctx(*, owner_id: str, user_id: str | None = None) -> RequestContext:
    return RequestContext(
        owner_id=owner_id,
        request_id="rbac-test",
        client_ip="127.0.0.1",
        user_id=user_id,
        role="user" if user_id else "anonymous",
        is_authenticated=user_id is not None,
    )


@pytest.mark.asyncio
async def test_anonymous_owner_passes_every_role_check():
    owner_scope = "anon:rbac-anon-owner"
    workspace_id = await _seed_workspace(owner_scope=owner_scope)
    ctx = _ctx(owner_id=owner_scope)
    for minimum in ("viewer", "editor", "admin", "owner"):
        ws, err = await check_workspace_role(
            workspace_id=workspace_id,
            request=_request(),
            context=ctx,
            minimum=minimum,
        )
        assert ws is not None, f"owner should satisfy {minimum}"
        assert err is None


@pytest.mark.asyncio
async def test_outsider_gets_404_from_role_check():
    owner_scope = "anon:rbac-anon-owner-2"
    workspace_id = await _seed_workspace(owner_scope=owner_scope)
    ctx = _ctx(owner_id="anon:outsider")
    ws, err = await check_workspace_role(
        workspace_id=workspace_id,
        request=_request(),
        context=ctx,
        minimum="viewer",
    )
    assert ws is None
    assert err is not None
    # ``api_error_response`` returns a JSONResponse-like with .status_code
    assert err.status_code == 404


@pytest.mark.asyncio
async def test_viewer_member_can_read_but_not_write():
    owner_scope = f"anon:rbac-owner-{uuid.uuid4().hex[:6]}"
    workspace_id = await _seed_workspace(owner_scope=owner_scope)
    user_id = f"user-rbac-{uuid.uuid4().hex[:6]}"
    await _seed_user(user_id, f"{user_id}@example.com")
    await workspace_members.add_member(
        workspace_id, user_id=user_id, role="viewer"
    )
    ctx = _ctx(owner_id=f"user:{user_id}", user_id=user_id)

    # Viewer satisfies viewer-level reads.
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=_request(), context=ctx, minimum="viewer"
    )
    assert err is None

    # Viewer does NOT satisfy editor-level writes.
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=_request(), context=ctx, minimum="editor"
    )
    assert err is not None
    assert err.status_code == 403


@pytest.mark.asyncio
async def test_editor_member_can_write_but_not_admin():
    owner_scope = f"anon:rbac-owner-{uuid.uuid4().hex[:6]}"
    workspace_id = await _seed_workspace(owner_scope=owner_scope)
    user_id = f"user-rbac-{uuid.uuid4().hex[:6]}"
    await _seed_user(user_id, f"{user_id}@example.com")
    await workspace_members.add_member(
        workspace_id, user_id=user_id, role="editor"
    )
    ctx = _ctx(owner_id=f"user:{user_id}", user_id=user_id)

    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=_request(), context=ctx, minimum="editor"
    )
    assert err is None

    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=_request(), context=ctx, minimum="admin"
    )
    assert err is not None
    assert err.status_code == 403


def test_anonymous_owner_artifact_create_still_works(client):
    """Smoke check: legacy anonymous owner workflows aren't broken by RBAC."""
    headers = {"X-Client-Session": "rbac-smoke"}
    workspace_id = client.get("/api/workspaces", headers=headers).json()[
        "workspaces"
    ][0]["id"]
    res = client.post(
        f"/api/workspaces/{workspace_id}/artifacts",
        json={"artifact_type": "user_note", "title": "smoke", "content": "ok"},
        headers=headers,
    )
    assert res.status_code == 201, res.text


def test_outsider_artifact_create_is_forbidden(client):
    """Smoke check: a different anonymous session is treated as an outsider."""
    owner_headers = {"X-Client-Session": "rbac-smoke-owner"}
    other_headers = {"X-Client-Session": "rbac-smoke-other"}
    workspace_id = client.get("/api/workspaces", headers=owner_headers).json()[
        "workspaces"
    ][0]["id"]
    res = client.post(
        f"/api/workspaces/{workspace_id}/artifacts",
        json={"artifact_type": "user_note", "title": "x", "content": "x"},
        headers=other_headers,
    )
    assert res.status_code == 404
    assert res.json()["code"] == "WORKSPACE_NOT_FOUND"
