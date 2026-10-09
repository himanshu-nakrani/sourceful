"""Embeddings are standardized on EMBEDDING_DIMENSIONS (1536).

Covers the per-provider request options, Gemini normalization, rejection of
models that cannot emit 1536 dims, the write-path guard, and SQLite handling of
legacy (non-1536) rows.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services import embeddings as emb
from backend.services.chunking import ChunkPayload
from backend.services.embedding_spec import (
    EMBEDDING_DIMENSIONS,
    EmbeddingDimensionError,
    UnsupportedEmbeddingModelError,
    embedding_request_options,
    ensure_dimensions,
    is_supported_embedding_model,
    l2_normalize,
)
from backend.settings import settings


def test_dimension_constant_is_1536():
    assert EMBEDDING_DIMENSIONS == 1536


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("openai", "text-embedding-3-small", {"dimensions": 1536}),
        ("openai", "text-embedding-3-large", {"dimensions": 1536}),
        ("openai", "text-embedding-ada-002", {}),  # fixed 1536; rejects `dimensions`
        ("gemini", "models/gemini-embedding-001", {"output_dimensionality": 1536}),
        ("gemini", "gemini-embedding-001", {"output_dimensionality": 1536}),
    ],
)
def test_request_options_for_supported_models(provider, model, expected):
    assert embedding_request_options(provider, model) == expected
    assert is_supported_embedding_model(provider, model)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("gemini", "models/text-embedding-004"),  # max 768
        ("gemini", "models/embedding-001"),  # max 768, no output_dimensionality
        ("openai", "text-similarity-davinci-001"),
        ("openai", "gemini-embedding-001"),  # right model, wrong provider
        ("vertex_search", "vertex_search_managed"),
    ],
)
def test_unsupported_models_raise_clearly(provider, model):
    with pytest.raises(UnsupportedEmbeddingModelError, match="1536"):
        embedding_request_options(provider, model)
    assert not is_supported_embedding_model(provider, model)


def test_configured_defaults_are_supported():
    assert is_supported_embedding_model("openai", settings.default_embedding_model_openai)
    assert is_supported_embedding_model("gemini", settings.default_embedding_model_gemini)


def test_l2_normalize_and_zero_vector():
    v = l2_normalize([3.0, 4.0])
    assert v == pytest.approx([0.6, 0.8])
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_ensure_dimensions_rejects_wrong_size():
    ensure_dimensions([[0.0] * 1536], model="m")
    with pytest.raises(EmbeddingDimensionError, match="3072"):
        ensure_dimensions([[0.0] * 1536, [0.0] * 3072], model="m")


def _openai_client(dims: int) -> MagicMock:
    client = MagicMock()

    async def create(model, input, **kwargs):  # noqa: A002 - mirrors SDK
        count = len(input) if isinstance(input, list) else 1
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * dims) for _ in range(count)])

    client.embeddings.create = AsyncMock(side_effect=create)
    return client


@pytest.mark.parametrize(
    ("model", "expected_kwargs"),
    [("text-embedding-3-large", {"dimensions": 1536}), ("text-embedding-ada-002", {})],
)
def test_openai_requests_1536_dims(model, expected_kwargs):
    client = _openai_client(1536)
    with patch.object(emb, "AsyncOpenAI", return_value=client):
        vectors = asyncio.run(emb.embed_texts("openai", "k", model, ["a", "b"]))
        query = asyncio.run(emb.embed_query("openai", "k", model, "q"))
    assert [len(v) for v in vectors] == [1536, 1536] and len(query) == 1536
    for call in client.embeddings.create.await_args_list:
        extra = {k: v for k, v in call.kwargs.items() if k not in {"model", "input"}}
        assert extra == expected_kwargs


def test_openai_wrong_size_response_raises():
    with patch.object(emb, "AsyncOpenAI", return_value=_openai_client(3072)):
        with pytest.raises(EmbeddingDimensionError):
            asyncio.run(emb.embed_texts("openai", "k", "text-embedding-3-large", ["a"]))


def test_unsupported_model_fails_before_calling_provider():
    client = _openai_client(1536)
    with patch.object(emb, "AsyncOpenAI", return_value=client):
        with pytest.raises(UnsupportedEmbeddingModelError):
            asyncio.run(emb.embed_query("openai", "k", "text-davinci-003", "q"))
    client.embeddings.create.assert_not_called()


def _fake_genai(embed_content):
    """Install a stand-in ``google.generativeai`` regardless of what other tests
    left in ``sys.modules`` (the code imports it lazily inside the function)."""
    module = SimpleNamespace(configure=lambda **_: None, embed_content=embed_content)
    # `import google.generativeai as genai` resolves via the parent package's
    # attribute, so stub both (test_llm.py replaces `google` with a MagicMock).
    return patch.dict(sys.modules, {"google": SimpleNamespace(generativeai=module), "google.generativeai": module})


def test_gemini_requests_1536_and_normalizes():
    seen = []

    def fake_embed_content(model, content, task_type=None, output_dimensionality=None, **kw):
        seen.append((task_type, output_dimensionality))
        return {"embedding": [2.0] * (output_dimensionality or 3072)}  # not unit length

    with _fake_genai(fake_embed_content):
        docs = asyncio.run(emb.embed_texts("gemini", "k", "models/gemini-embedding-001", ["a", "b"]))
        query = asyncio.run(emb.embed_query("gemini", "k", "models/gemini-embedding-001", "q"))
    assert seen == [("retrieval_document", 1536)] * 2 + [("retrieval_query", 1536)]
    for vector in [*docs, query]:
        assert len(vector) == 1536
        assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0)


def test_gemini_legacy_model_rejected_without_api_call():
    sdk = MagicMock()
    with _fake_genai(sdk):
        with pytest.raises(UnsupportedEmbeddingModelError):
            asyncio.run(emb.embed_query("gemini", "k", "models/text-embedding-004", "q"))
    sdk.assert_not_called()


def test_replace_chunks_rejects_wrong_dims_without_deleting():
    from backend.services import vectorstore

    chunk = ChunkPayload(chunk_index=0, content="x")
    with patch.object(vectorstore, "execute", new=AsyncMock()) as execute:
        with pytest.raises(EmbeddingDimensionError):
            asyncio.run(vectorstore.replace_chunks("d", "o", [chunk], [[0.1] * 3072]))
    execute.assert_not_called()  # existing chunks are not wiped by a bad response


def test_sqlite_similarity_skips_legacy_dimension_rows():
    from backend.services.vectorstore import _compute_similarities_sqlite

    rows = [
        {"id": "new", "document_id": "d", "content": "a", "embedding_json": json.dumps([1.0] + [0.0] * 1535)},
        {"id": "old", "document_id": "d", "content": "b", "embedding_json": json.dumps([1.0] * 3072)},
    ]
    result = _compute_similarities_sqlite(rows, [1.0] + [0.0] * 1535, top_k=5)
    assert [r.chunk_id for r in result] == ["new"]
    assert _compute_similarities_sqlite(rows[1:], [1.0] * 1536, top_k=5) == []


@pytest.mark.skipif(settings.using_postgres, reason="SQLite-specific migration path")
def test_sqlite_v16_flags_legacy_documents():
    from backend.database import _apply_sqlite_v16_migration, close_db, execute, fetch_one, init_db
    import backend.database as database

    async def scenario() -> None:
        await init_db()
        legacy, current = f"legacy-{uuid.uuid4().hex[:8]}", f"current-{uuid.uuid4().hex[:8]}"
        try:
            for doc_id, dims in ((legacy, 3072), (current, 1536)):
                await execute(
                    "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, status) "
                    "VALUES (?, 'o', 'f.txt', 'gemini', 'models/gemini-embedding-001', 'text/plain', ?, 'ready')",
                    (doc_id, doc_id),
                )
                await execute(
                    "INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, embedding_json) "
                    "VALUES (?, ?, 'o', 0, 'c', ?)",
                    (f"{doc_id}:0", doc_id, json.dumps([0.5] * dims)),
                )
            await execute("DELETE FROM schema_migrations WHERE version = 16")
            await _apply_sqlite_v16_migration(database._sqlite)
            await _apply_sqlite_v16_migration(database._sqlite)  # idempotent
            flagged = await fetch_one("SELECT reembed_required, last_error FROM documents WHERE id = ?", (legacy,))
            clean = await fetch_one("SELECT reembed_required FROM documents WHERE id = ?", (current,))
            assert flagged["reembed_required"] == 1 and "reembed" in flagged["last_error"]
            assert clean["reembed_required"] == 0
            kept = await fetch_one("SELECT embedding_json FROM document_chunks WHERE id = ?", (f"{legacy}:0",))
            assert len(json.loads(kept["embedding_json"])) == 3072  # SQLite data is not modified
            assert (await fetch_one("SELECT MAX(version) AS v FROM schema_migrations"))["v"] == 16
        finally:
            await execute("DELETE FROM documents WHERE id IN (?, ?)", (legacy, current))
            await close_db()

    asyncio.run(scenario())


def test_ingest_rejects_unsupported_embedding_model(client):
    response = client.post(
        "/api/ingest",
        data={"provider": "gemini", "embedding_model": "models/text-embedding-004"},
        files={"file": ("a.txt", b"hello world", "text/plain")},
        headers={"X-Client-Session": "dims-test", "X-Provider-Api-Key": "k"},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "UNSUPPORTED_EMBEDDING_MODEL"
    assert "1536" in body["error"]
