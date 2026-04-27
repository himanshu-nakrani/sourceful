"""Phase 3 tests: members + invitations + RBAC + sync runs."""

from __future__ import annotations

import asyncio
import uuid

from backend.database import execute


HEADERS_OWNER = {"X-Client-Session": "ph3-owner"}
HEADERS_OUTSIDER = {"X-Client-Session": "ph3-outsider"}
OWNER = f"anon:{HEADERS_OWNER['X-Client-Session']}"


def _ws(client) -> str:
    return client.get("/api/workspaces", headers=HEADERS_OWNER).json()["workspaces"][0]["id"]


def test_members_initial_empty(client):
    workspace_id = _ws(client)
    res = client.get(f"/api/workspaces/{workspace_id}/members", headers=HEADERS_OWNER)
    assert res.status_code == 200
    assert res.json()["members"] == []


def test_owner_can_add_member(client):
    workspace_id = _ws(client)

    async def _seed_user():
        await execute(
            """
            INSERT INTO users (id, email, password_hash, role, is_active, is_verified)
            VALUES ('user-ph3-1', 'editor@example.com', 'x', 'user', 1, 1)
            """,
        )

    asyncio.run(_seed_user())

    res = client.post(
        f"/api/workspaces/{workspace_id}/members",
        json={"user_id": "user-ph3-1", "role": "editor"},
        headers=HEADERS_OWNER,
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "editor"
    assert res.json()["email"] == "editor@example.com"

    listed = client.get(
        f"/api/workspaces/{workspace_id}/members", headers=HEADERS_OWNER
    ).json()["members"]
    assert any(m["user_id"] == "user-ph3-1" for m in listed)


def test_outsider_cannot_see_workspace(client):
    workspace_id = _ws(client)
    # Workspace was created scoped to HEADERS_OWNER's anon session; an outsider
    # session must get 404 even on members listing.
    res = client.get(
        f"/api/workspaces/{workspace_id}/members", headers=HEADERS_OUTSIDER
    )
    assert res.status_code == 404


def test_invitation_create_and_revoke(client):
    workspace_id = _ws(client)
    res = client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": "invitee@example.com", "role": "editor"},
        headers=HEADERS_OWNER,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    inv_id = body["id"]
    assert body["email"] == "invitee@example.com"
    assert body["role"] == "editor"
    assert body["token"]

    listed = client.get(
        f"/api/workspaces/{workspace_id}/invitations", headers=HEADERS_OWNER
    )
    assert listed.status_code == 200
    assert any(i["id"] == inv_id for i in listed.json()["invitations"])

    revoked = client.delete(
        f"/api/workspaces/{workspace_id}/invitations/{inv_id}",
        headers=HEADERS_OWNER,
    )
    assert revoked.status_code == 204
    assert all(
        i["id"] != inv_id
        for i in client.get(
            f"/api/workspaces/{workspace_id}/invitations", headers=HEADERS_OWNER
        ).json()["invitations"]
    )


def test_sync_runs_recorded_after_refetch_failure(client):
    """A failed URL refetch (URL_FETCH_FAILED) should still record an error sync run."""
    workspace_id = _ws(client)

    # Seed a URL source manually pointing at a guaranteed-unreachable URL.
    document_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    async def _seed():
        await execute(
            """
            INSERT INTO documents
                (id, owner_id, filename, provider, embedding_model, mime_type,
                 checksum, chunk_count, file_size, status, workspace_id)
            VALUES (?, ?, 'page.txt', 'openai', 'text-embedding-3-small',
                    'text/plain', ?, 0, 0, 'ready', ?)
            """,
            (document_id, OWNER, f"chk-{document_id}", workspace_id),
        )
        await execute(
            """
            INSERT INTO workspace_sources
                (id, workspace_id, source_type, document_id, source_title, source_url,
                 mime_type, status)
            VALUES (?, ?, 'url', ?, 'remote page', 'http://127.0.0.1:1/never',
                    'text/plain', 'ready')
            """,
            (source_id, workspace_id, document_id),
        )

    asyncio.run(_seed())

    # Trigger a refetch — it must fail (no server on port 1) and emit a sync run.
    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/{source_id}/reprocess",
        headers={**HEADERS_OWNER, "X-Provider-Api-Key": "test-key"},
    )
    # Status is 400/502 depending on the underlying httpx error.
    assert res.status_code >= 400

    runs = client.get(
        f"/api/workspaces/{workspace_id}/sources/{source_id}/sync-runs",
        headers=HEADERS_OWNER,
    )
    assert runs.status_code == 200
    payload = runs.json()["runs"]
    assert len(payload) == 1
    assert payload[0]["status"] == "error"


def test_role_at_least_helper():
    from backend.services.workspace_members import role_at_least

    assert role_at_least("owner", "viewer")
    assert role_at_least("admin", "editor")
    assert role_at_least("editor", "viewer")
    assert not role_at_least("viewer", "editor")
    assert not role_at_least(None, "viewer")
    assert not role_at_least("editor", "owner")
