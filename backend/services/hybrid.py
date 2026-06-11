"""Hybrid search: BM25-style FTS lane + dense lane, fused with RRF.

Only Postgres has a native FTS lane today (uses `content_tsv` generated
column + GIN index created in migration v5). On SQLite the FTS lane
returns an empty list, so hybrid retrieval transparently degrades to
the dense lane. Fusion is Reciprocal Rank Fusion (Cormack et al. 2009),
the industry default for multi-signal retrieval:

    score(d) = sum_i  weight_i / (k + rank_i(d))
"""

from __future__ import annotations

from collections import defaultdict

from backend.database import fetch_all
from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings


async def fts_search(
    document_ids: list[str],
    owner_id: str,
    query: str,
    top_k: int,
    workspace_id: str | None = None,
) -> list[RetrievedChunk]:
    """Lexical lane using Postgres `tsvector`. Returns [] on SQLite."""
    if not settings.using_postgres or not document_ids or not query.strip():
        return []
    placeholders = ",".join(["?"] * len(document_ids))
    ws_id = workspace_id or ""
    sql = f"""
        SELECT c.id, c.document_id, c.content, c.page_number,
               ts_rank_cd(c.content_tsv, plainto_tsquery('english', ?)) AS score
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE (c.owner_id = ? OR d.workspace_id = ?)
          AND c.document_id IN ({placeholders})
          AND c.content_tsv @@ plainto_tsquery('english', ?)
        ORDER BY score DESC
        LIMIT ?
    """
    params: tuple = (query, owner_id, ws_id, *document_ids, query, top_k)
    rows = await fetch_all(sql, params)
    return [
        RetrievedChunk(
            chunk_id=row["id"],
            document_id=row["document_id"],
            excerpt=row["content"],
            score=float(row.get("score") or 0.0),
            page_number=row.get("page_number"),
        )
        for row in rows
    ]


def reciprocal_rank_fusion(
    lanes: list[tuple[list[RetrievedChunk], float]],
    *,
    top_k: int,
    rrf_k: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse ranked lists via weighted RRF.

    `lanes` is a list of `(ranked_chunks, weight)` pairs. Chunks are
    identified by `chunk_id`; the first occurrence is used as the
    representative payload, and the fused RRF score replaces `.score`.
    """
    k = rrf_k if rrf_k is not None else settings.hybrid_rrf_k
    scores: dict[str, float] = defaultdict(float)
    representatives: dict[str, RetrievedChunk] = {}

    for ranked, weight in lanes:
        for rank_index, chunk in enumerate(ranked):
            scores[chunk.chunk_id] += weight / (k + rank_index + 1)
            representatives.setdefault(chunk.chunk_id, chunk)

    fused = [
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            excerpt=chunk.excerpt,
            score=scores[chunk.chunk_id],
            page_number=chunk.page_number,
        )
        for chunk in representatives.values()
    ]
    fused.sort(key=lambda c: c.score, reverse=True)
    return fused[:top_k]
