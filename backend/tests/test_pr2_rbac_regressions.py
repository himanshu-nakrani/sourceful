"""PR-2 regressions for workspace RBAC, invitations, and scoped retrieval."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
import pytest

from backend.auth import _session_token_hash, create_session
from backend.database import execute, fetch_one
from backend.routers.deps import anon_owner_id
from backend.services import workspace_members


PROVIDER_KEY = "test-provider-key"


def _signup(client, email: str) -> dict:
    res = client.post("/api/auth/signup", json={"email": email, "password": "strong-pass-123"})
    assert res.status_code == 201, res.text
    return res.json()


def _auth(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['session_token']}"}


def _workspace(client, user: dict) -> str:
    res = client.get("/api/workspaces", headers=_auth(user))
    assert res.status_code == 200, res.text
    return res.json()["workspaces"][0]["id"]


async def _seed_doc_source(workspace_id: str, owner_scope: str, title: str = "owner.txt") -> tuple[str, str]:
    document_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status, workspace_id, file_bytes)
        VALUES (?, ?, ?, 'openai', 'text-embedding-3-small', 'text/plain', ?, 1, 5, 'ready', ?, ?)
        """,
        (document_id, owner_scope, title, f"chk-{document_id}", workspace_id, b"owner"),
    )
    await execute(
        """
        INSERT INTO workspace_sources
            (id, workspace_id, source_type, document_id, source_title, mime_type, status)
        VALUES (?, ?, 'file', ?, ?, 'text/plain', 'ready')
        """,
        (source_id, workspace_id, document_id, title),
    )
    await execute(
        """
        INSERT INTO document_jobs
            (id, document_id, owner_id, provider, embedding_model, status, stage,
             progress, payload_filename, payload_mime_type, payload_bytes,
             provider_api_key, terminal)
        VALUES (?, ?, ?, 'openai', 'text-embedding-3-small', 'ready', 'complete',
                1.0, ?, 'text/plain', ?, '', TRUE)
        """,
        (str(uuid.uuid4()), document_id, owner_scope, title, b"owner"),
    )
    return document_id, source_id


def test_viewer_member_can_list_members_sources_and_read_source(client):
    owner = _signup(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    viewer = _signup(client, f"viewer-{uuid.uuid4().hex[:8]}@example.com")
    outsider = _signup(client, f"outsider-{uuid.uuid4().hex[:8]}@example.com")
    workspace_id = _workspace(client, owner)
    owner_scope = f"user:{owner['id']}"
    document_id, source_id = asyncio.run(_seed_doc_source(workspace_id, owner_scope))
    asyncio.run(workspace_members.add_member(workspace_id, user_id=viewer["id"], role="viewer"))

    for path in (
        f"/api/workspaces/{workspace_id}/members",
        f"/api/workspaces/{workspace_id}/sources",
        f"/api/workspaces/{workspace_id}/sources/{source_id}",
    ):
        res = client.get(path, headers=_auth(viewer))
        assert res.status_code == 200, (path, res.text)

    source = client.get(f"/api/workspaces/{workspace_id}/sources/{source_id}", headers=_auth(viewer)).json()
    assert source["document_id"] == document_id

    blocked = client.get(f"/api/workspaces/{workspace_id}/sources", headers=_auth(outsider))
    assert blocked.status_code == 404
    assert blocked.json()["code"] == "WORKSPACE_NOT_FOUND"


def test_editor_member_can_upload_and_reprocess_owner_document(client):
    owner = _signup(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    editor = _signup(client, f"editor-{uuid.uuid4().hex[:8]}@example.com")
    workspace_id = _workspace(client, owner)
    owner_scope = f"user:{owner['id']}"
    document_id, source_id = asyncio.run(_seed_doc_source(workspace_id, owner_scope, "reprocess.txt"))
    asyncio.run(workspace_members.add_member(workspace_id, user_id=editor["id"], role="editor"))

    upload = client.post(
        "/api/ingest",
        data={"provider": "openai", "embedding_model": "text-embedding-3-small", "workspace_id": workspace_id},
        files={"file": ("editor.txt", b"editor upload", "text/plain")},
        headers={**_auth(editor), "X-Provider-Api-Key": PROVIDER_KEY},
    )
    assert upload.status_code == 202, upload.text

    reprocess = client.post(
        f"/api/workspaces/{workspace_id}/sources/{source_id}/reprocess",
        headers={**_auth(editor), "X-Provider-Api-Key": PROVIDER_KEY},
    )
    assert reprocess.status_code == 202, reprocess.text

    row = asyncio.run(
        fetch_one(
            "SELECT COUNT(*) AS count FROM document_jobs WHERE document_id = ? AND status = 'queued'",
            (document_id,),
        )
    )
    assert row and row["count"] >= 1


def test_admin_cannot_assign_owner_role(client):
    owner = _signup(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    admin = _signup(client, f"admin-{uuid.uuid4().hex[:8]}@example.com")
    target = _signup(client, f"target-{uuid.uuid4().hex[:8]}@example.com")
    workspace_id = _workspace(client, owner)
    member = asyncio.run(workspace_members.add_member(workspace_id, user_id=target["id"], role="viewer"))
    asyncio.run(workspace_members.add_member(workspace_id, user_id=admin["id"], role="admin"))

    add_owner = client.post(
        f"/api/workspaces/{workspace_id}/members",
        json={"user_id": target["id"], "role": "owner"},
        headers=_auth(admin),
    )
    assert add_owner.status_code == 422

    update_owner = client.patch(
        f"/api/workspaces/{workspace_id}/members/{member['id']}",
        json={"role": "owner"},
        headers=_auth(admin),
    )
    assert update_owner.status_code == 422

    invite_owner = client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": "no-owner@example.com", "role": "owner"},
        headers=_auth(admin),
    )
    assert invite_owner.status_code == 422


def test_invited_user_accepts_valid_token_and_expired_token_is_rejected(client):
    owner = _signup(client, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    invitee = _signup(client, f"invitee-{uuid.uuid4().hex[:8]}@example.com")
    expired_user = _signup(client, f"expired-{uuid.uuid4().hex[:8]}@example.com")
    workspace_id = _workspace(client, owner)

    created = client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": invitee["email"], "role": "viewer"},
        headers=_auth(owner),
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    listed = client.get(f"/api/workspaces/{workspace_id}/invitations", headers=_auth(owner))
    assert listed.status_code == 200
    listed_token = listed.json()["invitations"][0]["token"]
    assert listed_token != token
    assert listed_token.endswith("…")

    accepted = client.post(
        "/api/workspaces/invitations/accept",
        json={"token": token},
        headers=_auth(invitee),
    )
    assert accepted.status_code == 200, accepted.text

    access = client.get(f"/api/workspaces/{workspace_id}/sources", headers=_auth(invitee))
    assert access.status_code == 200

    expired = asyncio.run(
        workspace_members.create_invitation(
            workspace_id,
            email=expired_user["email"],
            role="viewer",
            invited_by=owner["id"],
            expires_in_days=1,
        )
    )
    asyncio.run(
        execute(
            "UPDATE workspace_invitations SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), expired["id"]),
        )
    )
    rejected = client.post(
        "/api/workspaces/invitations/accept",
        json={"token": expired["token"]},
        headers=_auth(expired_user),
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "INVITATION_EXPIRED"


def test_invalid_bearer_with_client_session_returns_401_not_anonymous(client):
    user = _signup(client, f"expired-bearer-{uuid.uuid4().hex[:8]}@example.com")
    token = asyncio.run(create_session(user["id"], user_agent=None, ip_address=None, ttl_hours=1))
    asyncio.run(
        execute(
            "UPDATE auth_sessions SET expires_at = ? WHERE token_hash = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), _session_token_hash(token)),
        )
    )

    res = client.get(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {token}", "X-Client-Session": "fallback-session"},
    )
    assert res.status_code == 401

    owner = anon_owner_id("fallback-session")
    rows = asyncio.run(fetch_one("SELECT COUNT(*) AS count FROM workspaces WHERE owner_scope = ?", (owner,)))
    assert rows and rows["count"] == 0


@pytest.mark.asyncio
async def test_fts_lane_uses_workspace_scope_for_member(monkeypatch):
    from backend.services import hybrid

    captured: dict[str, object] = {}

    async def fake_fetch_all(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"id": "c1", "document_id": "d1", "content": "alpha", "page_number": None, "score": 0.5}
        ]

    monkeypatch.setattr(hybrid.settings.__class__, "using_postgres", property(lambda self: True))
    monkeypatch.setattr(hybrid, "fetch_all", fake_fetch_all)

    hits = await hybrid.fts_search(["d1"], "user:member", "alpha", 5, "workspace-1")
    assert len(hits) == 1
    assert "d.workspace_id" in str(captured["sql"])
    assert captured["params"] == ("alpha", "user:member", "workspace-1", "d1", "alpha", 5)


@pytest.mark.asyncio
async def test_graph_lane_returns_workspace_docs_for_member(monkeypatch):
    from backend.services import graph_retrieval

    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_traversal_enabled", True)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_enabled", True)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_hops", 0)

    owner_scope = "user:graph-owner"
    member_scope = "user:graph-member"
    workspace_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO workspaces (id, name, slug, owner_scope, visibility, archived, is_default) VALUES (?, 'Graph', ?, ?, 'private', 0, 0)",
        (workspace_id, f"graph-{workspace_id[:8]}", owner_scope),
    )
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status, workspace_id)
        VALUES (?, ?, 'graph.txt', 'openai', 'text-embedding-3-small', 'text/plain', ?, 1, 10, 'ready', ?)
        """,
        (document_id, owner_scope, f"chk-{document_id}", workspace_id),
    )
    await execute(
        "INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding_json) VALUES (?, ?, ?, 0, 'Acme depends on Beta.', '[]')",
        (f"{document_id}:0", document_id, owner_scope),
    )
    await execute(
        "INSERT INTO graph_entities (id, owner_id, document_id, name, entity_type) VALUES (?, ?, ?, 'Acme', 'org')",
        (str(uuid.uuid4()), owner_scope, document_id),
    )

    result = await graph_retrieval.graph_lane_search(
        owner_id=member_scope,
        document_ids=[document_id],
        question="What is Acme?",
        top_k=3,
        workspace_id=workspace_id,
    )
    assert [chunk.document_id for chunk in result.chunks] == [document_id]
