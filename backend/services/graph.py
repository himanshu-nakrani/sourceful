"""GraphRAG ingestion + graph helpers (Phase 3.3).

Three concerns live in this module:

1. **Extraction.** A Microsoft-GraphRAG-style LLM extractor that, given a
   chunk of text, emits a JSON document of ``entities`` and
   ``relations``. A lexical fallback (proper-noun harvester) ships
   alongside so the graph machinery remains exercisable in test
   environments without a live LLM.
2. **Persistence.** Owner-scoped upserts into ``graph_entities`` /
   ``graph_relations`` with cross-chunk entity deduplication by
   case-folded name.
3. **Graph queries.** An ``entity_neighborhood`` BFS over
   ``graph_relations`` used by the traversal retrieval lane (3.5).

Every public entry point is a no-op when ``RETRIEVAL_GRAPH_ENABLED`` is
false, so callers (the ingestion worker in particular) can invoke them
unconditionally without feature-flag branches.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from backend.database import execute, execute_many, fetch_all, fetch_one
from backend.settings import settings

logger = logging.getLogger("ragapp.graph")


@dataclass(slots=True)
class ExtractedEntity:
    """One entity harvested from a chunk, pre-DB-insert."""

    name: str
    entity_type: str = "generic"
    description: str | None = None


@dataclass(slots=True)
class ExtractedRelation:
    """An ``(A, rel, B)`` triple pre-DB-insert."""

    source: str  # entity name
    target: str
    relation_type: str
    description: str | None = None
    weight: float = 1.0


@dataclass(slots=True)
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)


_PROPER_NOUN_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3})\b")
_STOP_WORDS = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "A",
    "An",
    "And",
    "Or",
    "But",
    "If",
    "When",
    "While",
    "I",
    "You",
    "We",
    "They",
    "It",
}


def extract_from_text(text: str, *, max_entities: int = 25) -> ExtractionResult:
    """Lexical fallback extractor — ships entity nodes with no relations.

    The LLM extractor below is the preferred path when the operator has
    BYOK credentials; this heuristic remains in place so (a) tests
    don't need a live LLM and (b) the downstream graph query paths
    have *some* data to iterate on when the feature flag is first
    toggled on in an environment without background LLM access.
    """
    if not text:
        return ExtractionResult()
    seen: dict[str, ExtractedEntity] = {}
    for match in _PROPER_NOUN_RE.finditer(text):
        candidate = match.group(1).strip()
        if not candidate or candidate in _STOP_WORDS:
            continue
        if len(candidate) < 3:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen[key] = ExtractedEntity(name=candidate, entity_type="noun_phrase")
        if len(seen) >= max_entities:
            break
    return ExtractionResult(entities=list(seen.values()), relations=[])


# ---------------------------------------------------------------------------
# LLM-driven extraction (the Phase-3.3 deliverable)
# ---------------------------------------------------------------------------


_EXTRACTION_SYSTEM_PROMPT = (
    "You are an information-extraction system that builds a knowledge "
    "graph from a text passage. Identify the most salient named "
    "entities and the relations between them. Reply with ONLY a JSON "
    "object matching this schema:\n"
    '{"entities":[{"name":"...","entity_type":"person|organization|'
    'location|product|concept|event|other","description":"short '
    'description (<=120 chars)"}],'
    '"relations":[{"source":"entity name","target":"entity name",'
    '"relation_type":"short verb-phrase","description":"evidence '
    '<=120 chars"}]}\n'
    "Rules:\n"
    "- Use entity names exactly as they appear in the text (canonical "
    "form, no pronouns).\n"
    "- Relation `source` and `target` MUST reference entity names "
    "you list under `entities`.\n"
    "- Drop generic terms, pronouns, and stop words.\n"
    "- At most 12 entities and 12 relations per passage.\n"
    "- Do not include commentary, code fences, or extra keys."
)


def _clean_llm_response(raw: str) -> dict | None:
    """Strip code fences and best-effort-parse the planner's JSON blob.

    GraphRAG prompts are notoriously prone to the model prepending
    "Here's the JSON:" before the actual object. We find the first
    balanced ``{...}`` substring and parse it; everything around is
    discarded.
    """
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _parse_extraction_payload(data: dict) -> ExtractionResult:
    """Validate + normalize the LLM's entity/relation JSON into dataclasses."""
    entities_raw = data.get("entities") or []
    relations_raw = data.get("relations") or []

    entity_names: set[str] = set()
    entities: list[ExtractedEntity] = []
    if isinstance(entities_raw, list):
        for item in entities_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or len(name) < 2:
                continue
            if name.lower() in entity_names:
                continue
            entity_names.add(name.lower())
            entity_type = str(item.get("entity_type") or "other").strip().lower() or "other"
            description = item.get("description")
            if isinstance(description, str):
                description = description.strip()[:240] or None
            else:
                description = None
            entities.append(
                ExtractedEntity(name=name, entity_type=entity_type, description=description)
            )

    relations: list[ExtractedRelation] = []
    if isinstance(relations_raw, list):
        for item in relations_raw:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            rel_type = str(item.get("relation_type") or "").strip().lower()
            if not source or not target or not rel_type or source == target:
                continue
            if source.lower() not in entity_names or target.lower() not in entity_names:
                # The LLM occasionally invents relation endpoints that
                # aren't in its own entity list. Drop them rather than
                # persist dangling names.
                continue
            description = item.get("description")
            if isinstance(description, str):
                description = description.strip()[:240] or None
            else:
                description = None
            weight = item.get("weight")
            try:
                weight_f = float(weight) if weight is not None else 1.0
            except (TypeError, ValueError):
                weight_f = 1.0
            relations.append(
                ExtractedRelation(
                    source=source,
                    target=target,
                    relation_type=rel_type,
                    description=description,
                    weight=max(0.1, min(5.0, weight_f)),
                )
            )

    return ExtractionResult(entities=entities, relations=relations)


async def _call_extraction_llm(
    *,
    provider: str,
    api_key: str,
    model: str,
    passage: str,
) -> ExtractionResult:
    """One LLM round-trip for a single passage; always fail-open to empty result."""
    # Local import so this module stays importable in test environments
    # without OpenAI / Gemini SDKs configured (the lexical extractor
    # and graph queries do not need them).
    from backend.services.llm import create_openai_text, gemini_text

    user_prompt = (
        "Extract the knowledge graph for the following passage.\n\n"
        f"PASSAGE:\n{passage}\n\nReturn JSON only."
    )
    messages = [
        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        if provider == "openai":
            raw = await create_openai_text(api_key, model, messages)
        else:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, gemini_text, api_key, model, messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_extract_llm_failed err=%s", exc)
        return ExtractionResult()

    parsed = _clean_llm_response(raw or "")
    if parsed is None:
        logger.debug("graph_extract_parse_failed raw=%s", (raw or "")[:200])
        return ExtractionResult()
    return _parse_extraction_payload(parsed)


def _merge_extraction(dest: ExtractionResult, src: ExtractionResult) -> None:
    """In-place union of two extractions, deduping entities by case-folded name."""
    existing_names = {ent.name.lower(): ent for ent in dest.entities}
    for ent in src.entities:
        key = ent.name.lower()
        cur = existing_names.get(key)
        if cur is None:
            existing_names[key] = ent
            dest.entities.append(ent)
            continue
        # Prefer a description when the earlier occurrence didn't have one.
        if not cur.description and ent.description:
            cur.description = ent.description
    # Relations are allowed to duplicate across passages — the persist
    # step combines weights into a single edge.
    dest.relations.extend(src.relations)


async def extract_from_chunks(
    chunks: list[str],
    *,
    provider: str,
    api_key: str,
    model: str,
    max_chunks: int = 30,
    max_chunk_chars: int = 3500,
    concurrency: int = 4,
) -> ExtractionResult:
    """Run the LLM extractor across a document's chunks in parallel.

    Invariants:

    - We cap both the number of chunks and each chunk's length so a
      single extraction job can't consume arbitrary tokens.
    - Concurrency is bounded by a semaphore so we don't pile a
      background worker on top of the user's chat traffic.
    - Every failed passage degrades silently to an empty extraction —
      the document still ingests if the LLM is flaky.

    When the flag is off or the caller is missing credentials we
    short-circuit to the lexical extractor on the concatenated text.
    """
    if not settings.retrieval_graph_enabled:
        return ExtractionResult()
    if not chunks:
        return ExtractionResult()
    if not api_key or not model:
        return extract_from_text("\n\n".join(chunks[:max_chunks]))

    selected = [c for c in chunks if c and c.strip()][:max_chunks]
    if not selected:
        return ExtractionResult()

    limit = max(1, concurrency)
    semaphore = asyncio.Semaphore(limit)

    async def _one(passage: str) -> ExtractionResult:
        trimmed = passage.strip()
        if len(trimmed) > max_chunk_chars:
            trimmed = trimmed[:max_chunk_chars]
        async with semaphore:
            return await _call_extraction_llm(
                provider=provider,
                api_key=api_key,
                model=model,
                passage=trimmed,
            )

    results = await asyncio.gather(
        *(_one(passage) for passage in selected), return_exceptions=True
    )
    merged = ExtractionResult()
    for r in results:
        if isinstance(r, Exception):
            logger.warning("graph_extract_chunk_failed err=%s", r)
            continue
        _merge_extraction(merged, r)
    return merged


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def clear_document_graph(owner_id: str, document_id: str) -> None:
    """Remove every entity / relation belonging to a document.

    Called before a fresh ingestion pass so reprocessing jobs don't
    accumulate stale entity rows from previous runs. Community rows
    cascade automatically through the ``graph_communities.document_id``
    foreign key (migration v9).
    """
    # graph_communities may not exist on pre-v9 schemas; best-effort cleanup.
    try:
        await execute(
            "DELETE FROM graph_communities WHERE owner_id = ? AND document_id = ?",
            (owner_id, document_id),
        )
    except Exception:  # noqa: BLE001
        logger.debug("graph_communities_cleanup_skipped")
    await execute(
        "DELETE FROM graph_relations WHERE owner_id = ? AND document_id = ?",
        (owner_id, document_id),
    )
    await execute(
        "DELETE FROM graph_entities WHERE owner_id = ? AND document_id = ?",
        (owner_id, document_id),
    )


async def persist_extraction(
    *,
    owner_id: str,
    document_id: str,
    extraction: ExtractionResult,
    replace: bool = False,
) -> dict[str, int]:
    """Bulk-insert extracted entities/relations for a document.

    Relations are collapsed per ``(source, target, relation_type)`` so
    duplicate extractions across chunks merge into a single edge with
    summed weight. Entities are deduplicated by case-folded name.

    When ``replace=True`` we drop any prior graph rows for the document
    first — use that on reprocessing jobs. Returns counts for
    observability. Skips inserts entirely when the graph flag is off.
    """
    if not settings.retrieval_graph_enabled:
        return {"entities": 0, "relations": 0, "skipped": 1}
    if replace:
        await clear_document_graph(owner_id, document_id)
    if not extraction.entities and not extraction.relations:
        return {"entities": 0, "relations": 0, "skipped": 0}

    # De-dupe entities within a document by lower-case name.
    entity_rows = []
    name_to_id: dict[str, str] = {}
    for ent in extraction.entities:
        key = ent.name.lower()
        if key in name_to_id:
            continue
        entity_id = str(uuid.uuid4())
        name_to_id[key] = entity_id
        entity_rows.append(
            (
                entity_id,
                owner_id,
                document_id,
                ent.name,
                ent.entity_type,
                ent.description,
                None,
            )
        )
    if entity_rows:
        await execute_many(
            """
            INSERT INTO graph_entities
                (id, owner_id, document_id, name, entity_type, description, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            entity_rows,
        )

    # Combine duplicate relations before insert.
    merged_rel: dict[tuple[str, str, str], dict] = {}
    for rel in extraction.relations:
        source_id = name_to_id.get(rel.source.lower())
        target_id = name_to_id.get(rel.target.lower())
        if not source_id or not target_id or source_id == target_id:
            continue
        key = (source_id, target_id, rel.relation_type)
        existing = merged_rel.get(key)
        if existing is None:
            merged_rel[key] = {
                "description": rel.description,
                "weight": float(rel.weight),
            }
        else:
            existing["weight"] = float(existing["weight"]) + float(rel.weight)
            if not existing.get("description") and rel.description:
                existing["description"] = rel.description

    relation_rows = [
        (
            str(uuid.uuid4()),
            owner_id,
            document_id,
            source_id,
            target_id,
            rel_type,
            payload["description"],
            payload["weight"],
        )
        for (source_id, target_id, rel_type), payload in merged_rel.items()
    ]
    if relation_rows:
        await execute_many(
            """
            INSERT INTO graph_relations
                (id, owner_id, document_id, source_entity_id, target_entity_id,
                 relation_type, description, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            relation_rows,
        )
    return {"entities": len(entity_rows), "relations": len(relation_rows), "skipped": 0}


async def entity_neighborhood(
    *,
    owner_id: str,
    entity_names: Iterable[str],
    hops: int = 1,
    limit: int = 30,
) -> list[dict]:
    """Return entities reachable within ``hops`` of any matching seed.

    Stub for Phase 3.5. Uses a simple breadth-first expansion over the
    ``graph_relations`` table. Designed so the future retrieval-lane
    implementation can call this unchanged and layer ranking on top.
    """
    if not settings.retrieval_graph_enabled:
        return []
    needles = [n.lower() for n in entity_names if n and isinstance(n, str)]
    if not needles:
        return []
    placeholders = ",".join(["?"] * len(needles))
    seeds = await fetch_all(
        f"""
        SELECT id, name, entity_type, document_id
        FROM graph_entities
        WHERE owner_id = ? AND LOWER(name) IN ({placeholders})
        LIMIT ?
        """,
        (owner_id, *needles, limit),
    )
    frontier = {row["id"]: row for row in seeds}
    visited = dict(frontier)
    for _ in range(max(0, hops)):
        if not frontier:
            break
        frontier_ids = list(frontier.keys())
        ids_placeholders = ",".join(["?"] * len(frontier_ids))
        rows = await fetch_all(
            f"""
            SELECT ge.id, ge.name, ge.entity_type, ge.document_id
            FROM graph_relations gr
            JOIN graph_entities ge
              ON ge.id = gr.target_entity_id
            WHERE gr.owner_id = ?
              AND gr.source_entity_id IN ({ids_placeholders})
              AND ge.id NOT IN ({ids_placeholders})
            LIMIT ?
            """,
            (owner_id, *frontier_ids, *frontier_ids, limit),
        )
        new_frontier = {}
        for row in rows:
            if row["id"] in visited:
                continue
            visited[row["id"]] = row
            new_frontier[row["id"]] = row
        frontier = new_frontier
    return list(visited.values())[:limit]
