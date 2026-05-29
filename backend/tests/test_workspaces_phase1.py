"""Phase 1 backend tests: multi-source retrieval, source_ids filtering,
URL ingest validation, and reprocess endpoint.

Real LLM calls are avoided; these tests focus on the routing / resolution
layer that decides which documents/chunks the chat pipeline will consult.
"""

from __future__ import annotations

import asyncio
import uuid

from backend.database import execute, fetch_all
from backend.routers.deps import anon_owner_id


HEADERS = {"X-Client-Session": "ph1-tester"}
PROVIDER_HEADERS = {**HEADERS, "X-Provider-Api-Key": "test-provider-key"}
OWNER = anon_owner_id(HEADERS["X-Client-Session"])


def _bootstrap_workspace(client) -> str:
    res = client.get("/api/workspaces", headers=HEADERS)
    assert res.status_code == 200
    return res.json()["workspaces"][0]["id"]


async def _seed_ready_doc(
    workspace_id: str,
    *,
    title: str,
    content: str,
    chunk_count: int = 1,
) -> tuple[str, str]:
    """Insert a `ready` document + a single chunk + a workspace_sources row.

    Returns ``(document_id, source_id)``.
    """
    document_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status, workspace_id)
        VALUES (?, ?, ?, 'openai', 'text-embedding-3-small',
                'text/plain', ?, ?, ?, 'ready', ?)
        """,
        (document_id, OWNER, title, f"chk-{document_id}", chunk_count, len(content), workspace_id),
    )
    await execute(
        """
        INSERT INTO document_chunks
            (id, document_id, owner_id, chunk_index, content, page_number, embedding_json)
        VALUES (?, ?, ?, 0, ?, NULL, '[]')
        """,
        (chunk_id, document_id, OWNER, content),
    )
    await execute(
        """
        INSERT INTO workspace_sources
            (id, workspace_id, source_type, document_id, source_title, mime_type, status)
        VALUES (?, ?, 'file', ?, ?, 'text/plain', 'ready')
        """,
        (source_id, workspace_id, document_id, title),
    )
    return document_id, source_id


def test_resolve_workspace_documents_spans_all_ready_sources(client):
    workspace_id = _bootstrap_workspace(client)

    async def _setup_and_resolve():
        await _seed_ready_doc(workspace_id, title="A.txt", content="alpha")
        await _seed_ready_doc(workspace_id, title="B.txt", content="beta")
        # Decoy: another workspace with a ready doc that must NOT be returned.
        decoy_ws_id = str(uuid.uuid4())
        await execute(
            "INSERT INTO workspaces (id, name, slug, owner_scope, visibility, archived, is_default)"
            " VALUES (?, 'Decoy', ?, ?, 'private', 0, 0)",
            (decoy_ws_id, f"decoy-{decoy_ws_id[:6]}", OWNER),
        )
        await _seed_ready_doc(decoy_ws_id, title="DECOY.txt", content="decoy")

        from backend.routers.chat import _resolve_workspace_documents

        rows = await _resolve_workspace_documents(
            owner_id=OWNER,
            workspace_id=workspace_id,
            source_ids=None,
            provider="openai",
        )
        return rows

    rows = asyncio.run(_setup_and_resolve())
    titles = [r["filename"] for r in rows]
    assert "A.txt" in titles and "B.txt" in titles
    assert "DECOY.txt" not in titles
    assert len(rows) == 2


def test_resolve_workspace_documents_respects_source_ids(client):
    workspace_id = _bootstrap_workspace(client)

    async def _setup_and_resolve():
        _, src_a = await _seed_ready_doc(workspace_id, title="X.txt", content="x")
        _, _src_b = await _seed_ready_doc(workspace_id, title="Y.txt", content="y")

        from backend.routers.chat import _resolve_workspace_documents

        rows = await _resolve_workspace_documents(
            owner_id=OWNER,
            workspace_id=workspace_id,
            source_ids=[src_a],
            provider="openai",
        )
        return rows

    rows = asyncio.run(_setup_and_resolve())
    assert len(rows) == 1
    assert rows[0]["filename"] == "X.txt"


def test_chat_workspace_no_ready_sources_returns_400(client):
    workspace_id = _bootstrap_workspace(client)
    res = client.post(
        "/api/chat",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "question": "hello",
            "workspace_id": workspace_id,
        },
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "WORKSPACE_NO_READY_SOURCES"


def test_chat_unknown_workspace_returns_404(client):
    res = client.post(
        "/api/chat",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "question": "hi",
            "workspace_id": str(uuid.uuid4()),
        },
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 404
    assert res.json()["code"] == "WORKSPACE_NOT_FOUND"


def test_url_source_invalid_scheme_returns_400(client):
    workspace_id = _bootstrap_workspace(client)
    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/url",
        json={"url": "ftp://example.com/file.txt", "provider": "openai"},
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "URL_SCHEME_UNSUPPORTED"


def test_url_source_missing_host_returns_400(client):
    workspace_id = _bootstrap_workspace(client)
    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/url",
        json={"url": "https://", "provider": "openai"},
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 400
    assert res.json()["code"] in {"URL_HOST_MISSING", "URL_SCHEME_UNSUPPORTED"}


def test_url_source_missing_provider_key_returns_401(client):
    workspace_id = _bootstrap_workspace(client)
    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/url",
        json={"url": "https://example.com", "provider": "openai"},
        headers=HEADERS,  # no provider key
    )
    assert res.status_code == 401
    assert res.json()["code"] == "MISSING_PROVIDER_API_KEY"


def test_reprocess_unknown_source_returns_404(client):
    workspace_id = _bootstrap_workspace(client)
    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/{uuid.uuid4()}/reprocess",
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 404
    assert res.json()["code"] == "SOURCE_NOT_FOUND"


def test_reprocess_file_source_enqueues_job(client):
    workspace_id = _bootstrap_workspace(client)

    async def _seed():
        return await _seed_ready_doc(
            workspace_id, title="reproc.txt", content="reproc"
        )

    document_id, source_id = asyncio.run(_seed())
    # Seed payload bytes onto the latest job so reprocess can replay them.
    job_id = str(uuid.uuid4())

    async def _seed_job():
        await execute(
            """
            INSERT INTO document_jobs
                (id, document_id, owner_id, provider, embedding_model, status, stage,
                 progress, payload_filename, payload_mime_type, payload_bytes,
                 provider_api_key, terminal)
            VALUES (?, ?, ?, 'openai', 'text-embedding-3-small', 'succeeded',
                    'completed', 1.0, 'reproc.txt', 'text/plain', ?, '', TRUE)
            """,
            (job_id, document_id, OWNER, b"reproc"),
        )

    asyncio.run(_seed_job())

    res = client.post(
        f"/api/workspaces/{workspace_id}/sources/{source_id}/reprocess",
        headers=PROVIDER_HEADERS,
    )
    assert res.status_code == 202, res.text

    # A new queued job should now exist for the underlying document.
    async def _count():
        rows = await fetch_all(
            "SELECT COUNT(*) AS ct FROM document_jobs WHERE document_id = ? AND status = 'queued'",
            (document_id,),
        )
        return rows[0]["ct"]

    queued = asyncio.run(_count())
    assert queued >= 1
