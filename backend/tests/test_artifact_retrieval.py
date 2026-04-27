"""Phase 2 tests: artifact-aware retrieval + precedence rules."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from backend.database import execute
from backend.services import artifact_retrieval
from backend.services.llm import build_rag_prompt
from backend.services.vectorstore import RetrievedChunk


HEADERS = {"X-Client-Session": "ph2-retrieval"}
OWNER = f"anon:{HEADERS['X-Client-Session']}"


def _ws(client) -> str:
    return client.get("/api/workspaces", headers=HEADERS).json()["workspaces"][0]["id"]


@pytest.mark.asyncio
async def test_retrieve_artifacts_returns_relevance_ranked_chunks():
    workspace_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_id, owner_scope, visibility, archived, is_default)
        VALUES (?, 'art-ws', ?, 'anon:t', 'anon:t', 'private', 0, 0)
        """,
        (workspace_id, f"art-ws-{workspace_id[:8]}"),
    )
    # Two artifacts: one matches the query, one doesn't.
    relevant_id = str(uuid.uuid4())
    irrelevant_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'pgvector tuning', 'HNSW outperforms IVFFlat for our scale.'),
               (?, ?, 'user_note', 'unrelated', 'cooking instructions for pasta.')
        """,
        (relevant_id, workspace_id, irrelevant_id, workspace_id),
    )
    chunks = await artifact_retrieval.retrieve_workspace_artifacts(
        workspace_id=workspace_id,
        question="should we use HNSW or IVFFlat for pgvector?",
        limit=5,
    )
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == "artifact"
    assert chunk.chunk_id == f"artifact:{relevant_id}"
    assert chunk.metadata_json
    meta = json.loads(chunk.metadata_json)
    assert meta["kind"] == "artifact"
    assert meta["artifact_id"] == relevant_id
    assert meta["title"] == "pgvector tuning"


@pytest.mark.asyncio
async def test_retrieve_artifacts_score_floor_filters_weak_matches():
    workspace_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_id, owner_scope, visibility, archived, is_default)
        VALUES (?, 'weak-ws', ?, 'anon:t', 'anon:t', 'private', 0, 0)
        """,
        (workspace_id, f"weak-ws-{workspace_id[:8]}"),
    )
    weak_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'note', 'abc xyz')
        """,
        (weak_id, workspace_id),
    )
    # Long question with many tokens; tiny artifact has at most 1 overlap.
    chunks = await artifact_retrieval.retrieve_workspace_artifacts(
        workspace_id=workspace_id,
        question="explain the entire architecture of distributed transaction systems and consensus algorithms",
        limit=5,
        score_floor=0.5,
    )
    assert chunks == []


@pytest.mark.asyncio
async def test_retrieve_artifacts_dampens_score_below_typical_vector_hits():
    workspace_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_id, owner_scope, visibility, archived, is_default)
        VALUES (?, 'damp-ws', ?, 'anon:t', 'anon:t', 'private', 0, 0)
        """,
        (workspace_id, f"damp-ws-{workspace_id[:8]}"),
    )
    art_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'saved_answer', 'pgvector pgvector pgvector', 'pgvector pgvector pgvector')
        """,
        (art_id, workspace_id),
    )
    # Question is identical to artifact title → max possible token overlap.
    chunks = await artifact_retrieval.retrieve_workspace_artifacts(
        workspace_id=workspace_id, question="pgvector"
    )
    assert chunks
    # Even a perfect lexical match must be dampened to <= 0.25 so it never
    # outranks typical vector-search hits (0.6-0.95 band).
    assert chunks[0].score <= 0.25


def test_build_rag_prompt_segregates_artifact_excerpts():
    primary = RetrievedChunk(
        chunk_id="c1",
        document_id="doc-1",
        excerpt="Primary source content.",
        score=0.9,
        page_number=2,
        chunk_type="text",
    )
    artifact = RetrievedChunk(
        chunk_id="artifact:a1",
        document_id="artifact:a1",
        excerpt="A saved note from a user.",
        score=0.2,
        chunk_type="artifact",
        metadata_json=json.dumps(
            {
                "kind": "artifact",
                "artifact_id": "a1",
                "artifact_type": "user_note",
                "title": "My note",
            }
        ),
    )
    messages = build_rag_prompt([primary, artifact], "What is the answer?")
    system = messages[0]["content"]
    user_evidence = messages[1]["content"]
    user_question = messages[-1]["content"]

    # Primary block exists and uses [1].
    assert "Document excerpts:" in user_evidence
    assert "[1]" in user_evidence
    # Artifact block exists, references [2], and has a "saved" tag.
    assert "Saved knowledge" in user_evidence
    assert "[2]" in user_evidence
    assert "(saved" in user_evidence
    assert "My note" in user_evidence
    # System prompt picks up the precedence rule.
    assert "augmenting context" in system
    assert "primary source" in system
    # Final user message is still the question.
    assert user_question == "What is the answer?"


def test_build_rag_prompt_unchanged_without_artifacts():
    """Backward compatibility: a chunk list without artifacts produces the
    same single-block layout the existing single-document chat tests expect."""
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc-1",
        excerpt="Source content.",
        score=0.9,
        page_number=2,
        chunk_type="text",
    )
    messages = build_rag_prompt([chunk], "What is the answer?")
    system = messages[0]["content"]
    user_evidence = messages[1]["content"]
    assert "Saved knowledge" not in user_evidence
    assert "augmenting context" not in system


def test_chat_workspace_message_includes_artifact_when_relevant(client):
    """End-to-end: workspace chat surfaces a relevant artifact as a citation
    with chunk_type=artifact and the corresponding metadata."""
    workspace_id = _ws(client)

    # Seed a ready document + chunk so the primary retrieval has something
    # to anchor onto, then add a workspace_source row mirroring it.
    document_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    embedding = [0.1] * 1536
    embedding_json = json.dumps(embedding)

    async def _seed():
        await execute(
            """
            INSERT INTO documents
                (id, owner_id, filename, provider, embedding_model, mime_type,
                 checksum, chunk_count, file_size, status, workspace_id)
            VALUES (?, ?, 'pgvector.txt', 'openai', 'text-embedding-3-small',
                    'text/plain', ?, 1, 0, 'ready', ?)
            """,
            (document_id, OWNER, f"chk-{document_id}", workspace_id),
        )
        await execute(
            """
            INSERT INTO document_chunks
                (id, document_id, owner_id, chunk_index, content, embedding_json)
            VALUES (?, ?, ?, 0, 'pgvector HNSW excerpt content', ?)
            """,
            (chunk_id, document_id, OWNER, embedding_json),
        )
        await execute(
            """
            INSERT INTO workspace_sources
                (id, workspace_id, source_type, document_id, source_title, mime_type, status)
            VALUES (?, ?, 'file', ?, 'pgvector.txt', 'text/plain', 'ready')
            """,
            (str(uuid.uuid4()), workspace_id, document_id),
        )
        await execute(
            """
            INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
            VALUES (?, ?, 'saved_answer',
                    'HNSW vs IVFFlat',
                    'For our pgvector workload HNSW outperforms IVFFlat above 100k vectors.')
            """,
            (artifact_id, workspace_id),
        )

    asyncio.run(_seed())
    # Sanity: artifact retrieval returns this artifact for a matching question.
    art_chunks = asyncio.run(
        artifact_retrieval.retrieve_workspace_artifacts(
            workspace_id=workspace_id,
            question="should we use HNSW or IVFFlat for pgvector?",
        )
    )
    assert any(c.chunk_id == f"artifact:{artifact_id}" for c in art_chunks)
