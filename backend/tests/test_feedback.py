"""Integration tests for Phase 3.8 feedback endpoints."""

from __future__ import annotations

import uuid

from backend.database import execute, fetch_one
from backend.routers.deps import anon_owner_id

HEADERS = {"X-Client-Session": "feedback-session"}


def _insert_assistant_message(
    client, *, document_id: str = "doc-f1", conversation_id: str | None = None
) -> tuple[str, str]:
    """Bypass the LLM by inserting a conversation + assistant message directly.

    We need a real DB row for feedback to attach to; going through
    ``/api/chat`` would require a live provider key.
    """
    import asyncio

    conversation_id = conversation_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    # Owner scoping is derived from the session header by
    # backend.routers.deps.get_request_context; we use the same HMAC-signing
    # helper it relies on so the seeded owner_id matches the API's scope.
    owner_id = anon_owner_id(HEADERS["X-Client-Session"])

    async def _seed():
        # Insert a minimal document row to satisfy FK from conversations.
        existing_doc = await fetch_one("SELECT id FROM documents WHERE id = ?", (document_id,))
        if not existing_doc:
            await execute(
                """
                INSERT INTO documents
                    (id, owner_id, filename, provider, embedding_model, mime_type,
                     checksum, chunk_count, file_size, status)
                VALUES (?, ?, 'seed.txt', 'openai', 'text-embedding-3-small',
                        'text/plain', ?, 0, 0, 'ready')
                """,
                (document_id, owner_id, f"chk-{document_id}"),
            )
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, ?, 'seeded')",
            (conversation_id, owner_id, document_id),
        )
        await execute(
            "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'assistant', 'seeded answer')",
            (message_id, owner_id, conversation_id),
        )

    asyncio.run(_seed())
    return conversation_id, message_id


def test_feedback_thumbs_up_roundtrip(client):
    conversation_id, message_id = _insert_assistant_message(client)
    response = client.post(
        "/api/feedback",
        json={
            "conversation_id": conversation_id,
            "message_id": message_id,
            "rating": "up",
            "comment": "Great answer",
        },
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rating"] == "up"
    assert body["message_id"] == message_id
    assert body["comment"] == "Great answer"

    summary = client.get("/api/feedback/summary", headers=HEADERS)
    assert summary.status_code == 200
    data = summary.json()
    assert data["total"] == 1
    assert data["up"] == 1
    assert data["down"] == 0
    assert len(data["recent"]) == 1


def test_feedback_thumbs_down_and_counts(client):
    conversation_id, message_id = _insert_assistant_message(client)
    for rating in ["down", "down", "up"]:
        r = client.post(
            "/api/feedback",
            json={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "rating": rating,
            },
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
    summary = client.get("/api/feedback/summary", headers=HEADERS).json()
    assert summary["total"] == 3
    assert summary["down"] == 2
    assert summary["up"] == 1


def test_feedback_rejects_unknown_message(client):
    conversation_id, _ = _insert_assistant_message(client)
    response = client.post(
        "/api/feedback",
        json={
            "conversation_id": conversation_id,
            "message_id": "does-not-exist",
            "rating": "up",
        },
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "MESSAGE_NOT_FOUND"


def test_feedback_rejects_user_role_message(client):
    """Feedback must target the assistant turn, not the user's question."""
    import asyncio

    conversation_id = str(uuid.uuid4())
    user_message_id = str(uuid.uuid4())
    owner_id = anon_owner_id(HEADERS["X-Client-Session"])

    async def _seed():
        await execute(
            """
            INSERT INTO documents
                (id, owner_id, filename, provider, embedding_model, mime_type,
                 checksum, chunk_count, file_size, status)
            VALUES ('doc-u1', ?, 'seed.txt', 'openai', 'text-embedding-3-small',
                    'text/plain', 'chk-u1', 0, 0, 'ready')
            """,
            (owner_id,),
        )
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, 'doc-u1', 'seed')",
            (conversation_id, owner_id),
        )
        await execute(
            "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', 'question?')",
            (user_message_id, owner_id, conversation_id),
        )

    asyncio.run(_seed())

    response = client.post(
        "/api/feedback",
        json={
            "conversation_id": conversation_id,
            "message_id": user_message_id,
            "rating": "up",
        },
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_FEEDBACK_TARGET"


def test_feedback_scoped_per_owner(client):
    conversation_id, message_id = _insert_assistant_message(client)
    # Submit feedback from owner A
    r = client.post(
        "/api/feedback",
        json={"conversation_id": conversation_id, "message_id": message_id, "rating": "up"},
        headers=HEADERS,
    )
    assert r.status_code == 200

    # Owner B (different session header) cannot see the feedback or attach
    # to owner A's message.
    other_headers = {"X-Client-Session": "other-session"}
    summary = client.get("/api/feedback/summary", headers=other_headers).json()
    assert summary["total"] == 0
    blocked = client.post(
        "/api/feedback",
        json={"conversation_id": conversation_id, "message_id": message_id, "rating": "down"},
        headers=other_headers,
    )
    assert blocked.status_code == 404
