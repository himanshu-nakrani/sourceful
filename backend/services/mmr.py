"""Maximal Marginal Relevance (MMR) diversification.

Given a ranked candidate pool and a target_k, iteratively pick the chunk
that maximizes `lambda * relevance - (1 - lambda) * max_similarity_to_selected`.

Relevance uses the pre-computed `score` on each `RetrievedChunk` (we
don't re-embed). Similarity between chunks is approximated with a
lexical Jaccard over word sets -- cheap, has no external deps, and is
good enough to break near-duplicate runs (the main failure mode MMR
exists to solve). Callers that want true semantic diversity can pass
`chunk_embeddings` to use cosine similarity instead.
"""

from __future__ import annotations

import math
import re
from typing import Sequence

from backend.services.vectorstore import RetrievedChunk

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    union = len(a | b)
    return intersection / union


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


def mmr(
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    lambda_: float = 0.7,
    chunk_embeddings: dict[str, list[float]] | None = None,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks diversified via MMR.

    - `lambda_=1.0` is equivalent to taking the top `top_k` by relevance.
    - `lambda_=0.0` maximizes diversity (ignores relevance entirely).

    When `chunk_embeddings` is provided, cosine similarity is used;
    otherwise we fall back to Jaccard over tokenized excerpts.
    """
    if top_k <= 0 or not candidates:
        return []
    if lambda_ >= 1.0 or len(candidates) <= 1:
        return candidates[:top_k]
    lam = max(0.0, min(1.0, lambda_))

    use_vec = bool(chunk_embeddings)
    token_cache: dict[str, set[str]] = {}

    def similarity(a: RetrievedChunk, b: RetrievedChunk) -> float:
        if use_vec:
            va = chunk_embeddings.get(a.chunk_id)
            vb = chunk_embeddings.get(b.chunk_id)
            if va is not None and vb is not None:
                return _cosine(va, vb)
        ta = token_cache.setdefault(a.chunk_id, _tokens(a.excerpt))
        tb = token_cache.setdefault(b.chunk_id, _tokens(b.excerpt))
        return _jaccard(ta, tb)

    # The pool's existing `score` is treated as relevance. Normalize to
    # [0, 1] defensively so lambda trade-offs remain meaningful even if a
    # provider returns raw logits.
    scores = [float(c.score) for c in candidates]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    relevance = {
        c.chunk_id: (s - lo) / span for c, s in zip(candidates, scores)
    }

    selected: list[RetrievedChunk] = []
    remaining = list(candidates)
    # Seed with the highest-relevance chunk so MMR never drops the #1 hit.
    seed = remaining.pop(0)
    selected.append(seed)

    while remaining and len(selected) < top_k:
        best_idx = 0
        best_score = -math.inf
        for idx, cand in enumerate(remaining):
            sim_to_selected = max(
                (similarity(cand, s) for s in selected), default=0.0
            )
            score = lam * relevance[cand.chunk_id] - (1.0 - lam) * sim_to_selected
            if score > best_score:
                best_score = score
                best_idx = idx
        selected.append(remaining.pop(best_idx))

    return selected
