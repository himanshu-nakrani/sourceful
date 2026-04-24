"""Phase 0 + Phase 1 workspace tests.

Covers:
- Default workspace auto-creation on first /api/workspaces list.
- Workspace CRUD (create/list/get/patch/archive).
- Ingest binds the document to the caller's default workspace and creates a
  corresponding ``workspace_sources`` row.
- Cross-workspace isolation: workspace rows are scoped to the owner.
- Conversation documents carry a ``workspace_id`` field.
- Migration idempotency (re-running init_db does not duplicate default
  workspaces).
"""

from __future__ import annotations


HEADERS_A = {"X-Client-Session": "workspace-tester-A"}
HEADERS_B = {"X-Client-Session": "workspace-tester-B"}
PROVIDER_HEADERS_A = {**HEADERS_A, "X-Provider-Api-Key": "test-provider-key"}


def test_list_workspaces_creates_default(client):
    res = client.get("/api/workspaces", headers=HEADERS_A)
    assert res.status_code == 200, res.text
    payload = res.json()
    assert isinstance(payload["workspaces"], list)
    assert len(payload["workspaces"]) == 1
    ws = payload["workspaces"][0]
    assert ws["is_default"] is True
    assert ws["name"] == "Personal workspace"
    assert ws["visibility"] == "private"
    assert ws["archived"] is False

    # Calling again must be idempotent.
    res2 = client.get("/api/workspaces", headers=HEADERS_A)
    assert res2.status_code == 200
    assert len(res2.json()["workspaces"]) == 1


def test_workspace_crud(client):
    create = client.post(
        "/api/workspaces",
        json={"name": "Research", "description": "Lit review"},
        headers=HEADERS_A,
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["name"] == "Research"
    assert created["description"] == "Lit review"
    assert created["is_default"] is False

    ws_id = created["id"]
    fetched = client.get(f"/api/workspaces/{ws_id}", headers=HEADERS_A)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == ws_id

    patch = client.patch(
        f"/api/workspaces/{ws_id}",
        json={"name": "Research v2", "archived": True},
        headers=HEADERS_A,
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Research v2"
    assert patch.json()["archived"] is True

    # Listing default excludes archived.
    listed = client.get("/api/workspaces", headers=HEADERS_A).json()["workspaces"]
    ids = {w["id"] for w in listed}
    assert ws_id not in ids

    # Explicitly include archived.
    listed_all = client.get(
        "/api/workspaces?include_archived=true", headers=HEADERS_A
    ).json()["workspaces"]
    assert ws_id in {w["id"] for w in listed_all}


def test_workspace_owner_isolation(client):
    # Caller A creates an extra workspace.
    res_a = client.post(
        "/api/workspaces", json={"name": "A-space"}, headers=HEADERS_A
    )
    assert res_a.status_code == 201
    a_id = res_a.json()["id"]

    # Caller B cannot see or fetch A's workspace.
    b_list = client.get("/api/workspaces", headers=HEADERS_B).json()["workspaces"]
    assert all(w["id"] != a_id for w in b_list)
    assert client.get(f"/api/workspaces/{a_id}", headers=HEADERS_B).status_code == 404


def test_ingest_binds_document_to_default_workspace(client):
    # Prime default workspace for A.
    client.get("/api/workspaces", headers=HEADERS_A)

    res = client.post(
        "/api/ingest",
        data={"provider": "openai", "embedding_model": "text-embedding-3-small"},
        files={"file": ("ws_doc.txt", b"hello workspace", "text/plain")},
        headers=PROVIDER_HEADERS_A,
    )
    assert res.status_code == 202, res.text
    document_id = res.json()["document_id"]

    # Every document response must include workspace_id.
    doc = client.get(f"/api/documents/{document_id}", headers=HEADERS_A)
    assert doc.status_code == 200
    doc_body = doc.json()
    assert doc_body["workspace_id"]

    ws_id = doc_body["workspace_id"]

    # The document must be surfaced as a workspace source.
    sources = client.get(f"/api/workspaces/{ws_id}/sources", headers=HEADERS_A)
    assert sources.status_code == 200
    rows = sources.json()["sources"]
    assert any(
        src["document_id"] == document_id and src["source_type"] == "file"
        for src in rows
    )


def test_list_documents_includes_workspace_id(client):
    client.get("/api/workspaces", headers=HEADERS_A)
    client.post(
        "/api/ingest",
        data={"provider": "openai", "embedding_model": "text-embedding-3-small"},
        files={"file": ("listed.txt", b"listed content", "text/plain")},
        headers=PROVIDER_HEADERS_A,
    )
    listed = client.get("/api/documents", headers=HEADERS_A)
    assert listed.status_code == 200
    docs = listed.json()["documents"]
    assert docs and all("workspace_id" in d for d in docs)


def test_chat_without_document_or_workspace_returns_400(client):
    res = client.post(
        "/api/chat",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "question": "hello",
        },
        headers=PROVIDER_HEADERS_A,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "DOCUMENT_OR_WORKSPACE_REQUIRED"


def test_migration_default_workspace_is_idempotent(client):
    """Re-running init_db should not create duplicate default workspaces."""
    import asyncio

    from backend.database import fetch_all, init_db

    # Force a baseline: ensure at least one owner exists with a default workspace.
    client.get("/api/workspaces", headers=HEADERS_A)
    client.get("/api/workspaces", headers=HEADERS_B)

    async def _rerun():
        await init_db()
        return await fetch_all(
            "SELECT owner_scope, COUNT(*) AS ct FROM workspaces WHERE is_default = 1 GROUP BY owner_scope"
        )

    rows = asyncio.run(_rerun())
    for row in rows:
        assert row["ct"] == 1, f"duplicate default workspace for {row}"
