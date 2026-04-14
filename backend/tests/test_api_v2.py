import asyncio
from unittest.mock import AsyncMock, patch

from backend.database import fetch_one
from backend.services.jobs import claim_next_job, process_job

HEADERS = {"X-Client-Session": "test-session-1234"}
PROVIDER_HEADERS = {
    **HEADERS,
    "X-Provider-Api-Key": "test-provider-key",
}


def login_superuser(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert response.status_code == 200


def test_ingest_document_and_list(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai", "embedding_model": "text-embedding-3-small"},
        files={"file": ("test.txt", b"hello document", "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["job_id"]

    documents = client.get("/api/documents", headers=HEADERS)
    assert documents.status_code == 200
    assert documents.json()["documents"][0]["id"] == payload["document_id"]


# def test_vertex_search_ingest_allows_missing_provider_key(client):
#     login_superuser(client)
#     response = client.post(
#         "/api/ingest",
#         data={"provider": "vertex_search"},
#         files={"file": ("vertex.txt", b"hello vertex", "text/plain")},
#         headers=HEADERS,
#     )
#     assert response.status_code == 202
#     payload = response.json()
#     assert payload["status"] == "queued"
#     assert payload["job_id"]


def test_openai_ingest_requires_provider_key(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": ("openai.txt", b"hello openai", "text/plain")},
        headers=HEADERS,
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "MISSING_PROVIDER_API_KEY"


def test_reprocess_requires_provider_key_for_non_vertex_provider(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": ("reprocess.txt", b"hello reprocess", "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202
    ingest_payload = response.json()

    reprocess = client.post(
        f"/api/documents/{ingest_payload['document_id']}/reprocess",
        headers=HEADERS,
    )
    assert reprocess.status_code == 401
    payload = reprocess.json()
    assert payload["code"] == "MISSING_PROVIDER_API_KEY"


def test_full_ingest_chat_and_conversation_flow(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": ("paris.txt", b"The capital of France is Paris.", "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202
    ingest_payload = response.json()

    with patch("backend.services.jobs.embed_texts", new_callable=AsyncMock) as mock_embed_texts:
        mock_embed_texts.return_value = [[0.1] * 3]
        job = asyncio.run(claim_next_job())
        assert job is not None
        asyncio.run(process_job(job))

    status = client.get(
        f"/api/documents/{ingest_payload['document_id']}/status",
        headers=HEADERS,
    )
    assert status.status_code == 200
    assert status.json()["status"] == "ready"

    with patch("backend.routers.chat.embed_query", new_callable=AsyncMock) as mock_embed_query, patch(
        "backend.routers.chat.create_openai_text", new_callable=AsyncMock
    ) as mock_openai_stream:
        mock_embed_query.return_value = [0.1] * 3

        mock_openai_stream.return_value = "Paris is the capital."

        chat_response = client.post(
            "/api/chat",
            headers=PROVIDER_HEADERS,
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "question": "What is the capital of France?",
                "document_id": ingest_payload["document_id"],
            },
        )
        assert chat_response.status_code == 200
        data = chat_response.json()
        assert "conversation_id" in data
        assert "sources" in data
        assert data["content"] == "Paris is the capital."

    conversations = client.get(
        "/api/conversations",
        headers=HEADERS,
        params={"document_id": ingest_payload["document_id"]},
    )
    assert conversations.status_code == 200
    conversation = conversations.json()["conversations"][0]

    detail = client.get(f"/api/conversations/{conversation['id']}", headers=HEADERS)
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["sources"]

    rename = client.patch(
        f"/api/conversations/{conversation['id']}",
        headers=HEADERS,
        json={"title": "France QA"},
    )
    assert rename.status_code == 200

    exported = client.get(
        f"/api/conversations/{conversation['id']}/export",
        headers=HEADERS,
    )
    assert exported.status_code == 200
    assert "France QA" in exported.text

    delete_conversation = client.delete(
        f"/api/conversations/{conversation['id']}",
        headers=HEADERS,
    )
    assert delete_conversation.status_code == 200

    delete_document = client.delete(
        f"/api/documents/{ingest_payload['document_id']}",
        headers=HEADERS,
    )
    assert delete_document.status_code == 200

    analytics = client.get("/api/analytics/overview")
    assert analytics.status_code == 200
    assert analytics.json()["totals"]["users"] >= 1


def test_job_retries_then_terminal_failure(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": ("retry.txt", b"Retry me", "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202
    ingest_payload = response.json()

    # First processing attempt fails and should schedule retry.
    with patch("backend.services.jobs._build_chunks", new_callable=AsyncMock) as mock_chunks:
        mock_chunks.side_effect = RuntimeError("temporary extractor issue")
        job = asyncio.run(claim_next_job())
        assert job is not None
        asyncio.run(process_job(job))

    scheduled = client.get(f"/api/jobs/{ingest_payload['job_id']}", headers=HEADERS)
    assert scheduled.status_code == 200
    scheduled_payload = scheduled.json()
    assert scheduled_payload["status"] == "queued"
    assert scheduled_payload["stage"] == "retry_scheduled"
    assert scheduled_payload["next_retry_at"] is not None
    assert scheduled_payload["terminal"] is False

    # Force terminal failure by exhausting attempts.
    row = asyncio.run(fetch_one("SELECT * FROM document_jobs WHERE id = ?", (ingest_payload["job_id"],)))
    assert row is not None
    row["attempt_count"] = row["max_attempts"]
    with patch("backend.services.jobs._build_chunks", new_callable=AsyncMock) as mock_chunks:
        mock_chunks.side_effect = RuntimeError("permanent extractor issue")
        asyncio.run(process_job(row))

    terminal = client.get(f"/api/jobs/{ingest_payload['job_id']}", headers=HEADERS)
    assert terminal.status_code == 200
    terminal_payload = terminal.json()
    assert terminal_payload["status"] == "error"
    assert terminal_payload["terminal"] is True


def test_rerun_message_creates_branched_conversation(client):
    login_superuser(client)
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": ("branch.txt", b"The capital of France is Paris.", "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202
    ingest_payload = response.json()

    with patch("backend.services.jobs.embed_texts", new_callable=AsyncMock) as mock_embed_texts:
        mock_embed_texts.return_value = [[0.1] * 3]
        job = asyncio.run(claim_next_job())
        assert job is not None
        asyncio.run(process_job(job))

    with patch("backend.routers.chat.embed_query", new_callable=AsyncMock) as mock_embed_query, patch(
        "backend.routers.chat.create_openai_text", new_callable=AsyncMock
    ) as mock_openai_text:
        mock_embed_query.return_value = [0.1] * 3
        mock_openai_text.side_effect = ["Paris is the capital.", "Paris remains the capital."]

        first_chat = client.post(
            "/api/chat",
            headers=PROVIDER_HEADERS,
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "question": "What is the capital of France?",
                "document_id": ingest_payload["document_id"],
            },
        )
        assert first_chat.status_code == 200
        conversation_id = first_chat.json()["conversation_id"]

        conversation = client.get(f"/api/conversations/{conversation_id}", headers=HEADERS)
        assert conversation.status_code == 200
        user_message = conversation.json()["messages"][0]

        rerun = client.post(
            "/api/chat/rerun",
            headers=PROVIDER_HEADERS,
            json={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "document_id": ingest_payload["document_id"],
                "conversation_id": conversation_id,
                "message_id": user_message["id"],
            },
        )
        assert rerun.status_code == 200
        rerun_payload = rerun.json()
        assert rerun_payload["conversation_id"] != conversation_id
        assert rerun_payload["content"] == "Paris remains the capital."

        rerun_conversation = client.get(
            f"/api/conversations/{rerun_payload['conversation_id']}",
            headers=HEADERS,
        )
        assert rerun_conversation.status_code == 200
        rerun_messages = rerun_conversation.json()["messages"]
        assert len(rerun_messages) == 2
        assert rerun_messages[0]["role"] == "user"
        assert rerun_messages[0]["content"] == "What is the capital of France?"


def test_concurrent_job_claim():
    from backend.database import execute
    job_id = "test-concurrent-claim-job"
    doc_id = "test-concurrent-doc-id"
    owner_id = "test-owner"

    async def run_concurrent():
        await execute(
            "INSERT OR IGNORE INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')",
            (doc_id, owner_id, "test.txt", "openai", "emb-model", "text/plain", "checksum")
        )
        await execute(
            "INSERT OR IGNORE INTO document_jobs (id, document_id, owner_id, provider, embedding_model, status, stage, payload_filename, payload_mime_type) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', 'test.txt', 'text/plain')",
            (job_id, doc_id, owner_id, "openai", "emb-model")
        )
        
        # Test concurrent claims
        tasks = [
            claim_next_job(),
            claim_next_job(),
            claim_next_job(),
        ]
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_concurrent())
    # Only one should succeed
    claimed = [r for r in results if r is not None and r["id"] == job_id]
    assert len(claimed) == 1


def test_ready_worker_heartbeat(client):
    from backend.database import execute
    # Put a stale heartbeat
    asyncio.run(execute("INSERT OR REPLACE INTO service_heartbeats (service_name, updated_at) VALUES ('worker', '2000-01-01 00:00:00')"))
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["worker_heartbeat"] == "stale"
