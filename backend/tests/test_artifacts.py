"""Phase 2 tests: workspace artifacts CRUD + save-from-message + chat modes."""

from __future__ import annotations

import asyncio
import uuid

from backend.database import execute
from backend.routers.deps import anon_owner_id


HEADERS = {"X-Client-Session": "ph2-tester"}
PROVIDER_HEADERS = {**HEADERS, "X-Provider-Api-Key": "test-provider-key"}
OWNER = anon_owner_id(HEADERS["X-Client-Session"])


def _ws(client) -> str:
    return client.get("/api/workspaces", headers=HEADERS).json()["workspaces"][0]["id"]


def test_artifact_crud_roundtrip(client):
    workspace_id = _ws(client)

    create = client.post(
        f"/api/workspaces/{workspace_id}/artifacts",
        json={
            "artifact_type": "user_note",
            "title": "Lit review notes",
            "content": "Key insight: pgvector HNSW > IVFFlat for our scale.",
        },
        headers=HEADERS,
    )
    assert create.status_code == 201, create.text
    body = create.json()
    artifact_id = body["id"]
    assert body["artifact_type"] == "user_note"
    assert body["workspace_id"] == workspace_id

    listed = client.get(f"/api/workspaces/{workspace_id}/artifacts", headers=HEADERS)
    assert listed.status_code == 200
    assert any(a["id"] == artifact_id for a in listed.json()["artifacts"])

    fetched = client.get(
        f"/api/workspaces/{workspace_id}/artifacts/{artifact_id}", headers=HEADERS
    )
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Lit review notes"

    patched = client.patch(
        f"/api/workspaces/{workspace_id}/artifacts/{artifact_id}",
        json={"title": "Updated"},
        headers=HEADERS,
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Updated"

    deleted = client.delete(
        f"/api/workspaces/{workspace_id}/artifacts/{artifact_id}", headers=HEADERS
    )
    assert deleted.status_code == 204

    gone = client.get(
        f"/api/workspaces/{workspace_id}/artifacts/{artifact_id}", headers=HEADERS
    )
    assert gone.status_code == 404


def test_artifact_filter_by_type(client):
    workspace_id = _ws(client)
    for artifact_type, title in [
        ("user_note", "n1"),
        ("saved_answer", "a1"),
        ("saved_brief", "b1"),
    ]:
        client.post(
            f"/api/workspaces/{workspace_id}/artifacts",
            json={"artifact_type": artifact_type, "title": title, "content": "x"},
            headers=HEADERS,
        )
    only_notes = client.get(
        f"/api/workspaces/{workspace_id}/artifacts?artifact_type=user_note",
        headers=HEADERS,
    )
    assert only_notes.status_code == 200
    titles = [a["title"] for a in only_notes.json()["artifacts"]]
    assert titles == ["n1"]


def test_artifact_isolation_between_workspaces(client):
    workspace_id = _ws(client)
    other = client.post(
        "/api/workspaces", json={"name": "Other"}, headers=HEADERS
    ).json()
    other_id = other["id"]
    create = client.post(
        f"/api/workspaces/{workspace_id}/artifacts",
        json={"artifact_type": "user_note", "title": "scoped", "content": "x"},
        headers=HEADERS,
    )
    assert create.status_code == 201
    listed_other = client.get(
        f"/api/workspaces/{other_id}/artifacts", headers=HEADERS
    )
    assert listed_other.status_code == 200
    assert listed_other.json()["artifacts"] == []


def test_save_assistant_message_as_artifact(client):
    workspace_id = _ws(client)
    document_id = "doc-art-1"
    conversation_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    async def _seed():
        await execute(
            """
            INSERT INTO documents
                (id, owner_id, filename, provider, embedding_model, mime_type,
                 checksum, chunk_count, file_size, status, workspace_id)
            VALUES (?, ?, 'seed.txt', 'openai', 'text-embedding-3-small',
                    'text/plain', ?, 0, 0, 'ready', ?)
            """,
            (document_id, OWNER, f"chk-{document_id}", workspace_id),
        )
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title, workspace_id) VALUES (?, ?, ?, 'seeded', ?)",
            (conversation_id, OWNER, document_id, workspace_id),
        )
        await execute(
            "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'assistant', 'this is the saved answer')",
            (message_id, OWNER, conversation_id),
        )

    asyncio.run(_seed())

    res = client.post(
        f"/api/workspaces/{workspace_id}/artifacts/from-message",
        json={"message_id": message_id},
        headers=HEADERS,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["artifact_type"] == "saved_answer"
    assert body["source_message_id"] == message_id
    assert "saved answer" in body["content"]


def test_save_user_message_returns_400(client):
    workspace_id = _ws(client)
    document_id = "doc-art-2"
    conversation_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    async def _seed():
        await execute(
            """
            INSERT INTO documents
                (id, owner_id, filename, provider, embedding_model, mime_type,
                 checksum, chunk_count, file_size, status, workspace_id)
            VALUES (?, ?, 'seed.txt', 'openai', 'text-embedding-3-small',
                    'text/plain', ?, 0, 0, 'ready', ?)
            """,
            (document_id, OWNER, f"chk-{document_id}", workspace_id),
        )
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title, workspace_id) VALUES (?, ?, ?, 'seeded', ?)",
            (conversation_id, OWNER, document_id, workspace_id),
        )
        await execute(
            "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', 'a question')",
            (message_id, OWNER, conversation_id),
        )

    asyncio.run(_seed())

    res = client.post(
        f"/api/workspaces/{workspace_id}/artifacts/from-message",
        json={"message_id": message_id},
        headers=HEADERS,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "MESSAGE_NOT_ASSISTANT"


def test_chat_request_accepts_mode():
    """Pydantic request validation accepts the new mode field."""
    from backend.models import ChatRequest

    body = ChatRequest(
        provider="openai",
        model="gpt-4o-mini",
        document_id="doc",
        question="hi",
        mode="compare",
    )
    assert body.mode == "compare"


def test_system_prompt_for_mode_appends_instruction():
    from backend.services.llm import SYSTEM_PROMPT, system_prompt_for_mode

    base = system_prompt_for_mode("ask")
    assert base == SYSTEM_PROMPT
    cmp_prompt = system_prompt_for_mode("compare")
    assert cmp_prompt.startswith(SYSTEM_PROMPT)
    assert "COMPARE" in cmp_prompt
    extract_prompt = system_prompt_for_mode("extract")
    assert "EXTRACT" in extract_prompt
    brief_prompt = system_prompt_for_mode("brief")
    assert "BRIEF" in brief_prompt
    # Unknown mode falls back to base prompt.
    fallback = system_prompt_for_mode("nonsense")
    assert fallback == SYSTEM_PROMPT
