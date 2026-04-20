"""Graph-traversal retrieval lane (Phase 3.5).

The dense and lexical lanes answer questions whose surface form
overlaps with the chunk content. Multi-hop queries like "who reports
to X" or "which products use component Y" can hit documents that
mention the entities but not the question's keywords. The graph lane
solves that by:

1. Extracting seed entity names from the user's question (case-folded
   substring match against ``graph_entities`` for the owner + allowed
   document set — no extra LLM call required).
2. Running :func:`backend.services.graph.entity_neighborhood` to
   expand those seeds N hops.
3. Pulling the highest-signal chunks from the documents that contain
   the discovered entities. We rank chunks by how many distinct
   entities they mention, so chunks that "tie" multiple entities
   together float to the top.

The lane returns a ``list[RetrievedChunk]`` with a pseudo-similarity
score in [0, 1] based on entity overlap so the downstream RRF fusion
treats it like any other lane. When disabled or when no seeds are
found, it returns ``[]`` and the caller proceeds as if only dense +
FTS were available.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.database import fetch_all
from backend.services.graph import entity_neighborhood
from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings

logger = logging.getLogger("ragapp.graph_retrieval")


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


@dataclass(slots=True)
class GraphLaneResult:
    """Chunks + observability produced by one traversal run."""

    chunks: list[RetrievedChunk]
    stats: dict[str, int | str | list[str]]


def _tokenize_question(question: str) -> set[str]:
    """Lower-case token set for seed-name matching.

    We strip function words later via a size filter (<3 chars) and a
    small stop list; the goal is not perfect NER — just enough signal
    to find seed entities inside the user's question.
    """
    tokens = {m.group(0).lower() for m in _WORD_RE.finditer(question or "")}
    return {t for t in tokens if len(t) >= 3}


_QUESTION_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "who",
    "how",
    "why",
    "when",
    "where",
    "which",
    "this",
    "that",
    "about",
    "from",
    "into",
    "have",
    "does",
    "would",
    "could",
    "should",
    "been",
    "there",
    "here",
    "some",
    "any",
    "all",
    "are",
}


async def _candidate_entities(
    owner_id: str, document_ids: list[str], question: str
) -> list[dict]:
    """Return entities from the allowed doc set whose name appears in the question.

    Implementation uses a LIKE-per-token pattern rather than a reverse
    regex on the question so the load stays on the database side.
    """
    tokens = _tokenize_question(question) - _QUESTION_STOP_WORDS
    if not tokens or not document_ids:
        return []
    # We cap the fan-out so we don't send 50 LIKE clauses to Postgres
    # on a chatty question.
    token_list = sorted(tokens, key=len, reverse=True)[:12]

    like_clauses = " OR ".join(["LOWER(name) LIKE ?"] * len(token_list))
    doc_placeholders = ",".join(["?"] * len(document_ids))
    sql = f"""
        SELECT id, name, entity_type, document_id
        FROM graph_entities
        WHERE owner_id = ?
          AND document_id IN ({doc_placeholders})
          AND ({like_clauses})
        LIMIT ?
    """
    like_params = [f"%{tok}%" for tok in token_list]
    params: tuple = (owner_id, *document_ids, *like_params, settings.retrieval_graph_seed_limit)
    try:
        rows = await fetch_all(sql, params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_seed_search_failed err=%s", exc)
        return []

    # Deduplicate by name while preserving the first-seen row.
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        key = (row.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


async def _fetch_chunks_for_entities(
    owner_id: str, entity_rows: list[dict], limit: int
) -> list[tuple[RetrievedChunk, int]]:
    """For each entity's document, fetch a handful of chunks that mention it.

    Returns ``(chunk, mention_count)`` pairs; callers aggregate
    mentions across entities to score chunks by entity overlap.
    """
    if not entity_rows:
        return []

    # Group entities by document so we can batch the chunk lookup per doc.
    by_doc: dict[str, list[dict]] = {}
    for row in entity_rows:
        by_doc.setdefault(row["document_id"], []).append(row)

    results: list[tuple[RetrievedChunk, int]] = []
    for doc_id, ents in by_doc.items():
        names = [e["name"] for e in ents if e.get("name")]
        if not names:
            continue
        like_clauses = " OR ".join(["LOWER(content) LIKE ?"] * len(names))
        sql = f"""
            SELECT id, document_id, content, page_number, parent_content
            FROM document_chunks
            WHERE document_id = ? AND owner_id = ?
              AND ({like_clauses})
            LIMIT ?
        """
        like_params = [f"%{name.lower()}%" for name in names]
        params: tuple = (doc_id, owner_id, *like_params, limit)
        try:
            rows = await fetch_all(sql, params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph_chunk_lookup_failed doc=%s err=%s", doc_id, exc)
            continue

        for row in rows:
            content = (row.get("content") or "").lower()
            mentions = sum(1 for name in names if name.lower() in content)
            if mentions == 0:
                continue
            excerpt = row.get("parent_content") if settings.retrieval_parent_doc_enabled else None
            excerpt = excerpt or row["content"]
            chunk = RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                excerpt=excerpt,
                # Cap at 1.0 so downstream score consumers behave.
                score=min(1.0, mentions / max(1, len(names))),
                page_number=row.get("page_number"),
            )
            results.append((chunk, mentions))
    return results


async def graph_lane_search(
    *,
    owner_id: str,
    document_ids: list[str],
    question: str,
    top_k: int,
) -> GraphLaneResult:
    """Run the traversal lane end-to-end.

    Flag-gated by ``RETRIEVAL_GRAPH_TRAVERSAL_ENABLED`` **and**
    ``RETRIEVAL_GRAPH_ENABLED`` (a traversal makes no sense if the
    underlying graph was never populated).
    """
    empty = GraphLaneResult(chunks=[], stats={"enabled": False})
    if not settings.retrieval_graph_traversal_enabled:
        return empty
    if not settings.retrieval_graph_enabled:
        return empty
    if not document_ids or not (question or "").strip():
        return empty

    stats: dict[str, int | str | list[str]] = {"enabled": True}

    seeds = await _candidate_entities(owner_id, document_ids, question)
    stats["seeds"] = [s["name"] for s in seeds]
    if not seeds:
        stats["hits"] = 0
        return GraphLaneResult(chunks=[], stats=stats)

    # Expand N hops from the seed entities.
    expanded = await entity_neighborhood(
        owner_id=owner_id,
        entity_names=[s["name"] for s in seeds],
        hops=max(0, settings.retrieval_graph_hops),
        limit=max(settings.retrieval_graph_chunk_limit, len(seeds) * 3),
    )
    # Keep only entities whose document is in scope.
    scoped = [row for row in expanded if row.get("document_id") in document_ids]
    stats["expanded_entities"] = len(scoped)
    if not scoped:
        stats["hits"] = 0
        return GraphLaneResult(chunks=[], stats=stats)

    scored = await _fetch_chunks_for_entities(
        owner_id,
        scoped,
        settings.retrieval_graph_chunk_limit,
    )
    # Merge duplicates, summing mention counts.
    merged: dict[str, tuple[RetrievedChunk, int]] = {}
    for chunk, mentions in scored:
        existing = merged.get(chunk.chunk_id)
        if existing is None:
            merged[chunk.chunk_id] = (chunk, mentions)
            continue
        merged_chunk, prev_mentions = existing
        combined = prev_mentions + mentions
        merged_chunk.score = min(1.0, merged_chunk.score + chunk.score)
        merged[chunk.chunk_id] = (merged_chunk, combined)

    ranked = sorted(merged.values(), key=lambda pair: (pair[1], pair[0].score), reverse=True)
    final = [pair[0] for pair in ranked[:top_k]]
    stats["hits"] = len(final)
    return GraphLaneResult(chunks=final, stats=stats)
