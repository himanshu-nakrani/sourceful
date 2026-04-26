"""Phase 2: include workspace artifacts (notes + saved answers) as augmenting
context in workspace-scoped chat.

Precedence rule from the plan (line 278-281):

- Uploaded sources remain the primary evidence (they retrieve via embeddings
  and dominate the citation list).
- Saved artifacts are augmenting context.
- Assistant-authored artifacts must not masquerade as original source
  documents — they are tagged ``chunk_type="artifact"`` and surface in the
  prompt under a separate ``Saved knowledge`` heading.

This module deliberately uses a simple bag-of-words overlap score instead of
embedding the artifacts. Artifacts are short, hand-curated text; lexical
matching gives a useful relevance signal without forcing every save to enqueue
an embedding job. If we later want semantic retrieval over artifacts, this
service becomes the integration seam.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.database import fetch_all
from backend.services.vectorstore import RetrievedChunk


# Stop-words deliberately small: workspace artifacts are short, so dropping
# common terms preserves more signal than aggressive list pruning.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "for", "on",
        "with", "by", "is", "are", "was", "were", "be", "been", "being", "as",
        "at", "from", "this", "that", "these", "those", "it", "its", "i", "we",
        "you", "they", "he", "she", "them", "us", "our", "your", "their",
        "what", "when", "where", "which", "who", "how", "why", "do", "does",
        "did", "can", "could", "should", "would", "may", "might", "will",
        "if", "then", "than", "so", "not", "no", "yes",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {
        tok.lower()
        for tok in _TOKEN_RE.findall(text or "")
        if tok.lower() not in _STOPWORDS and len(tok) > 1
    }


def _score(query_tokens: set[str], artifact_text: str) -> float:
    """Return a score in [0, 1] based on token overlap with the query.

    The score is computed as ``|query ∩ artifact| / |query|`` so it stays
    proportional to how much of the user's question the artifact addresses,
    not how long the artifact is. Empty queries return 0.
    """
    if not query_tokens:
        return 0.0
    artifact_tokens = _tokenize(artifact_text)
    if not artifact_tokens:
        return 0.0
    overlap = query_tokens & artifact_tokens
    return len(overlap) / len(query_tokens)


def _excerpt(content: str, *, limit: int = 600) -> str:
    cleaned = (content or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _serialize_metadata(artifact: dict[str, Any]) -> str:
    payload = {
        "kind": "artifact",
        "artifact_id": artifact["id"],
        "artifact_type": artifact["artifact_type"],
        "title": artifact["title"],
        "source_message_id": artifact.get("source_message_id"),
    }
    return json.dumps(payload)


async def retrieve_workspace_artifacts(
    *,
    workspace_id: str,
    question: str,
    limit: int = 3,
    score_floor: float = 0.05,
    primary_citation_count: int = 0,
) -> list[RetrievedChunk]:
    """Return up to ``limit`` artifact chunks ordered by relevance to ``question``.

    Each returned chunk is tagged with ``chunk_type="artifact"`` and carries a
    JSON metadata blob in ``metadata_json`` so downstream renderers can treat
    them differently from source-document citations.

    The base score is **dampened** so artifact chunks never displace primary
    source citations in the prompt's numbered list — see precedence rule. The
    chunk's `score` is therefore not directly comparable to vector similarity
    scores; UI code that sorts the combined list should rely on the explicit
    grouping (uploaded sources first, then artifacts) rather than the raw
    score.

    Parameters:
        primary_citation_count: number of primary chunks already retrieved;
            used only to short-circuit when there's nothing to augment.
    """
    if limit <= 0:
        return []
    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    rows = await fetch_all(
        """
        SELECT id, workspace_id, artifact_type, title, content,
               source_message_id, created_at, updated_at
        FROM workspace_artifacts
        WHERE workspace_id = ?
          AND artifact_type IN ('user_note', 'saved_answer', 'saved_brief', 'extraction_result')
        """,
        (workspace_id,),
    )
    if not rows:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        text = f"{row['title']}\n{row['content']}"
        score = _score(query_tokens, text)
        if score >= score_floor:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = scored[:limit]
    if not selected:
        return []

    chunks: list[RetrievedChunk] = []
    for raw_score, row in selected:
        # Dampen artifact scores so they never sort above primary citations
        # in any caller that merges the lists by score. We cap at 0.5 and
        # multiply by 0.5 again — both empirical anchors that keep artifacts
        # below typical vector-search hits (which sit in the 0.6-0.95 band).
        dampened = min(raw_score, 0.5) * 0.5
        chunks.append(
            RetrievedChunk(
                chunk_id=f"artifact:{row['id']}",
                # ``document_id`` is reused as the artifact id so the
                # downstream citation contract still has a stable handle.
                # Renderers should branch on chunk_type, not on document_id.
                document_id=f"artifact:{row['id']}",
                excerpt=_excerpt(row["content"]),
                score=dampened,
                page_number=None,
                chunk_type="artifact",
                metadata_json=_serialize_metadata(row),
            )
        )
    _ = primary_citation_count  # currently unused; kept as a hook for tuning
    return chunks
