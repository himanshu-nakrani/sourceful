"""Unit tests for the retrieval pipeline, reranker, and hybrid fusion."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services import reranker
from backend.services.hybrid import reciprocal_rank_fusion
from backend.services.vectorstore import RetrievedChunk


def _chunk(cid: str, excerpt: str = "", score: float = 0.0, doc: str = "d") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        document_id=doc,
        excerpt=excerpt or f"text-{cid}",
        score=score,
        page_number=None,
    )


def test_rrf_fuses_two_lanes_and_respects_weights():
    dense = [_chunk("a"), _chunk("b"), _chunk("c")]
    fts = [_chunk("b"), _chunk("a"), _chunk("d")]

    fused = reciprocal_rank_fusion(
        [(dense, 1.0), (fts, 1.0)], top_k=4, rrf_k=60
    )
    ids = [c.chunk_id for c in fused]
    # "a" and "b" appear in both lanes so they outrank "c" and "d".
    assert ids[0] in {"a", "b"}
    assert ids[1] in {"a", "b"}
    assert set(ids[:2]) == {"a", "b"}
    assert set(ids[2:]) == {"c", "d"}


def test_rrf_weight_zero_equivalent_to_single_lane():
    dense = [_chunk("a"), _chunk("b"), _chunk("c")]
    fts = [_chunk("z"), _chunk("y"), _chunk("x")]

    fused = reciprocal_rank_fusion(
        [(dense, 1.0), (fts, 0.0)], top_k=3, rrf_k=60
    )
    assert [c.chunk_id for c in fused] == ["a", "b", "c"]


def test_rrf_handles_empty_lane():
    dense = [_chunk("a"), _chunk("b")]
    fused = reciprocal_rank_fusion([(dense, 1.0), ([], 1.0)], top_k=5)
    assert [c.chunk_id for c in fused] == ["a", "b"]


def test_rrf_deduplicates_representative_payload():
    # Same chunk appears in both lanes: returned once with the fused score.
    shared = _chunk("a", excerpt="first-occurrence")
    alt = _chunk("a", excerpt="second-occurrence")
    fused = reciprocal_rank_fusion([( [shared], 1.0), ([alt], 1.0)], top_k=5)
    assert len(fused) == 1
    assert fused[0].chunk_id == "a"
    # First-occurrence representative payload is kept.
    assert fused[0].excerpt == "first-occurrence"


@pytest.mark.asyncio
async def test_reranker_noop_passthrough():
    chunks = [_chunk("a", score=0.1), _chunk("b", score=0.9), _chunk("c", score=0.5)]
    result = await reranker.rerank("irrelevant", chunks, top_k=2)
    # Noop (default) must preserve order and respect top_k.
    assert [c.chunk_id for c in result] == ["a", "b"]


@pytest.mark.asyncio
async def test_reranker_failure_falls_back_to_input_order(monkeypatch):
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]

    async def boom(*_a, **_kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(reranker.settings, "retrieval_reranker_enabled", True)
    monkeypatch.setattr(reranker.settings, "reranker_provider", "cohere")
    monkeypatch.setattr(reranker, "_cohere_scores", boom)

    result = await reranker.rerank("q", chunks, top_k=2)
    # Fail-open: retain dense order on reranker errors.
    assert [c.chunk_id for c in result] == ["a", "b"]


@pytest.mark.asyncio
async def test_reranker_reorders_by_provider_scores(monkeypatch):
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]

    async def fake_scores(_query, documents):
        # Return scores that invert the input order.
        return [0.1, 0.2, 0.9]

    monkeypatch.setattr(reranker.settings, "retrieval_reranker_enabled", True)
    monkeypatch.setattr(reranker.settings, "reranker_provider", "cohere")
    monkeypatch.setattr(reranker.settings, "reranker_api_key", "test-key")
    monkeypatch.setattr(reranker, "_cohere_scores", fake_scores)

    result = await reranker.rerank("q", chunks, top_k=3)
    assert [c.chunk_id for c in result] == ["c", "b", "a"]
    assert result[0].score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_pipeline_dense_only_when_flags_off(monkeypatch):
    from backend.services import retrieval_pipeline

    monkeypatch.setattr(retrieval_pipeline.settings, "retrieval_hybrid_enabled", False)
    monkeypatch.setattr(retrieval_pipeline.settings, "retrieval_reranker_enabled", False)

    dense_hits = [_chunk("a"), _chunk("b"), _chunk("c")]

    async def fake_query_similar(*_a, **_kw):
        return dense_hits

    with patch.object(retrieval_pipeline, "query_similar", side_effect=fake_query_similar):
        result = await retrieval_pipeline.retrieve(
            retrieval_pipeline.RetrievalRequest(
                query="q",
                document_ids=["d"],
                owner_id="owner",
                query_embedding=[0.0, 1.0],
                top_k=2,
            ),
        )

    assert [c.chunk_id for c in result.chunks] == ["a", "b"]
    assert result.stages["hybrid_enabled"] is False
    assert result.stages["reranker_enabled"] is False
    assert result.stages["final_hits"] == 2


@pytest.mark.asyncio
async def test_pipeline_applies_reranker_with_overfetch(monkeypatch):
    from backend.services import retrieval_pipeline

    monkeypatch.setattr(retrieval_pipeline.settings, "retrieval_hybrid_enabled", False)
    monkeypatch.setattr(retrieval_pipeline.settings, "retrieval_reranker_enabled", True)
    monkeypatch.setattr(retrieval_pipeline.settings, "reranker_overfetch_factor", 3)

    dense_hits = [_chunk(f"c{i}") for i in range(6)]

    async def fake_query_similar(*args, **kwargs):
        # Must request 2 * 3 = 6 candidates when reranker is on.
        # args: (doc_id, owner, emb, k, min_score, workspace_id)
        k = args[3] if len(args) > 3 else kwargs.get("k", 0)
        assert k == 6
        return dense_hits

    async def fake_rerank(query, chunks, *, top_k):
        # Return reversed order to prove reranker output is used.
        return list(reversed(chunks))[:top_k]

    with patch.object(retrieval_pipeline, "query_similar", side_effect=fake_query_similar), patch.object(
        retrieval_pipeline.reranker, "rerank", side_effect=fake_rerank
    ):
        result = await retrieval_pipeline.retrieve(
            retrieval_pipeline.RetrievalRequest(
                query="q",
                document_ids=["d"],
                owner_id="owner",
                query_embedding=[0.0, 1.0],
                top_k=2,
            ),
        )

    assert [c.chunk_id for c in result.chunks] == ["c5", "c4"]
    assert result.stages["dense_k"] == 6
    assert result.stages["final_hits"] == 2
