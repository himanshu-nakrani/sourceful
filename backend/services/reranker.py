"""Cross-encoder reranker with pluggable providers.

Providers:
  - "noop": returns input order unchanged (used by default).
  - "cohere": Cohere Rerank v3 via REST API.
  - "jina": Jina Reranker v2 via REST API.
  - "bge-local": BAAI/bge-reranker-v2-m3 via sentence-transformers
    (requires the optional `sentence-transformers` dependency).

All providers share the same signature:

    await rerank(query, chunks, top_k) -> list[RetrievedChunk]

The returned chunks are sorted by the reranker's score (highest first)
and the `score` field is overwritten with the rerank score so downstream
callers see a consistent ordering signal. When the reranker fails, the
input order is preserved and the failure is surfaced via the trace span
so pipeline behavior degrades gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

import httpx

from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings

logger = logging.getLogger("ragapp.reranker")


class RerankerError(RuntimeError):
    pass


async def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_k: int,
) -> list[RetrievedChunk]:
    if not chunks or top_k <= 0:
        return chunks[:top_k]

    provider = (settings.reranker_provider or "noop").lower()
    if provider == "noop" or not settings.retrieval_reranker_enabled:
        return chunks[:top_k]

    try:
        if provider == "cohere":
            scores = await _cohere_scores(query, [c.excerpt for c in chunks])
        elif provider == "jina":
            scores = await _jina_scores(query, [c.excerpt for c in chunks])
        elif provider == "bge-local":
            scores = await asyncio.to_thread(_bge_local_scores, query, [c.excerpt for c in chunks])
        else:
            raise RerankerError(f"Unknown reranker provider: {provider}")
    except Exception as exc:
        logger.warning("reranker_failed provider=%s err=%s", provider, exc)
        # Fail-open: keep dense-retrieval order.
        return chunks[:top_k]

    paired = list(zip(chunks, scores, strict=True))
    paired.sort(key=lambda pair: pair[1], reverse=True)
    result: list[RetrievedChunk] = []
    for chunk, score in paired[:top_k]:
        result.append(replace(chunk, score=float(score)))
    return result


async def _cohere_scores(query: str, documents: list[str]) -> list[float]:
    api_key = settings.reranker_api_key
    if not api_key:
        raise RerankerError("RERANKER_API_KEY not set for cohere provider")
    payload = {
        "model": settings.reranker_model or "rerank-english-v3.0",
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    async with httpx.AsyncClient(timeout=settings.reranker_timeout_seconds) as client:
        response = await client.post(
            "https://api.cohere.com/v1/rerank",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    scores = [0.0] * len(documents)
    for item in body.get("results", []):
        idx = int(item["index"])
        scores[idx] = float(item.get("relevance_score", 0.0))
    return scores


async def _jina_scores(query: str, documents: list[str]) -> list[float]:
    api_key = settings.reranker_api_key
    if not api_key:
        raise RerankerError("RERANKER_API_KEY not set for jina provider")
    payload = {
        "model": settings.reranker_model or "jina-reranker-v2-base-multilingual",
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    async with httpx.AsyncClient(timeout=settings.reranker_timeout_seconds) as client:
        response = await client.post(
            "https://api.jina.ai/v1/rerank",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    scores = [0.0] * len(documents)
    for item in body.get("results", []):
        idx = int(item["index"])
        scores[idx] = float(item.get("relevance_score", 0.0))
    return scores


_BGE_MODEL = None


def _bge_local_scores(query: str, documents: list[str]) -> list[float]:
    global _BGE_MODEL
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except ImportError as exc:
        raise RerankerError(
            "sentence-transformers is required for bge-local reranker. "
            "pip install sentence-transformers"
        ) from exc
    if _BGE_MODEL is None:
        _BGE_MODEL = CrossEncoder(settings.reranker_model or "BAAI/bge-reranker-v2-m3")
    pairs = [(query, doc) for doc in documents]
    scores = _BGE_MODEL.predict(pairs)
    return [float(s) for s in scores]
