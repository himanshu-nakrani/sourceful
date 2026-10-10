"""Unit tests for MMR diversification (backend.services.mmr)."""

from __future__ import annotations

import pytest

from backend.services.mmr import _cosine, _jaccard, _tokens, mmr
from backend.services.vectorstore import RetrievedChunk


def _c(cid: str, score: float, text: str) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=cid, document_id="d", excerpt=text, score=score)


DUP_POOL = [
    _c("a", 0.95, "pgvector hnsw index build parameters m ef_construction"),
    _c("a2", 0.94, "pgvector hnsw index build parameters m ef_construction tuning"),
    _c("b", 0.80, "billing invoices are sent monthly to the account owner"),
    _c("c", 0.70, "kubernetes pods restart policy and liveness probes"),
]


def test_empty_and_nonpositive_k():
    assert mmr([], top_k=3) == []
    assert mmr(DUP_POOL, top_k=0) == []
    assert mmr(DUP_POOL, top_k=-1) == []


def test_lambda_one_is_plain_top_k_and_single_candidate_shortcut():
    assert [c.chunk_id for c in mmr(DUP_POOL, top_k=2, lambda_=1.0)] == ["a", "a2"]
    assert [c.chunk_id for c in mmr(DUP_POOL[:1], top_k=5, lambda_=0.3)] == ["a"]


def test_near_duplicate_is_demoted_and_seed_is_kept():
    # Relevance is min-max normalised, so the lowest-scored candidate has
    # relevance 0; at lambda=0.3 diversity outweighs a 0.89-Jaccard duplicate.
    picked = [c.chunk_id for c in mmr(DUP_POOL, top_k=3, lambda_=0.3)]
    assert picked[0] == "a"  # top hit is never dropped
    assert "a2" not in picked  # near-duplicate loses to diverse chunks
    assert set(picked) == {"a", "b", "c"}


def test_high_lambda_still_prefers_relevance_over_diversity():
    picked = [c.chunk_id for c in mmr(DUP_POOL, top_k=3, lambda_=0.5)]
    assert picked == ["a", "b", "a2"]


def test_returns_at_most_pool_size_without_duplicates():
    picked = mmr(DUP_POOL, top_k=10, lambda_=0.5)
    ids = [c.chunk_id for c in picked]
    assert len(ids) == len(DUP_POOL) == len(set(ids))


def test_lambda_is_clamped_below_zero():
    # lambda < 0 behaves like 0 (pure diversity) rather than inverting relevance.
    assert [c.chunk_id for c in mmr(DUP_POOL, top_k=3, lambda_=-5)] == [
        c.chunk_id for c in mmr(DUP_POOL, top_k=3, lambda_=0.0)
    ]


def test_cosine_path_with_embeddings_and_fallback_for_missing_vectors():
    pool = [_c("x", 0.9, "alpha"), _c("y", 0.85, "beta"), _c("z", 0.5, "gamma")]
    # y is a vector duplicate of x; z is orthogonal -> z wins second slot.
    emb = {"x": [1.0, 0.0], "y": [1.0, 0.0], "z": [0.0, 1.0]}
    assert [c.chunk_id for c in mmr(pool, top_k=2, lambda_=0.5, chunk_embeddings=emb)] == ["x", "z"]
    # Missing vectors fall back to lexical Jaccard instead of crashing.
    partial = {"x": [1.0, 0.0]}
    assert len(mmr(pool, top_k=3, lambda_=0.5, chunk_embeddings=partial)) == 3


def test_equal_scores_do_not_divide_by_zero():
    pool = [_c(str(i), 0.5, f"text {i}") for i in range(4)]
    assert len(mmr(pool, top_k=3, lambda_=0.5)) == 3


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [([1, 0], [1, 0], 1.0), ([1, 0], [0, 1], 0.0), ([0, 0], [1, 1], 0.0), ([1, 2], [1], 0.0), ([], [], 0.0)],
)
def test_cosine_edge_cases(a, b, expected):
    assert _cosine(a, b) == pytest.approx(expected)


def test_tokens_and_jaccard():
    assert _tokens("Hello, HELLO world-42!") == {"hello", "world", "42"}
    assert _tokens("") == set()
    assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert _jaccard(set(), {"a"}) == 0.0
    assert _jaccard({"a"}, {"b"}) == 0.0
