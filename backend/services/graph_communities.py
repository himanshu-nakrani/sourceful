"""Community detection + per-community summaries (Phase 3.4).

Runs after :mod:`backend.services.graph` persists entities and relations
for a document. We:

1. Build an in-memory undirected graph from ``graph_relations``.
2. Partition it into communities. If ``leidenalg`` + ``python-igraph``
   are installed we use Leiden clustering (the GraphRAG default); if
   not we fall back to weakly-connected components. Both paths emit
   the same shape so downstream code is agnostic.
3. Ask the LLM to write a short summary per community. The summary is
   later surfaced to the graph-traversal retrieval lane as an
   additional piece of context.

Failure is silent at every step: a flag-off deployment, a missing LLM
key, or an extraction returning zero relations all degrade to "no
communities", and document ingestion completes normally.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

from backend.database import execute, execute_many, fetch_all
from backend.settings import settings

logger = logging.getLogger("ragapp.graph.communities")


@dataclass(slots=True)
class CommunityRecord:
    """In-memory community before we persist it."""

    label: str
    entity_ids: list[str]
    algorithm: str
    summary: str | None = None


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------


def _connected_components(
    nodes: set[str], edges: list[tuple[str, str]]
) -> list[list[str]]:
    """Weakly-connected components on an undirected multigraph.

    Pure Python to avoid a hard dep on networkx. We build adjacency
    lists and BFS-walk. Singleton nodes are included as one-node
    components; callers filter by ``min_size``.
    """
    adjacency: dict[str, set[str]] = defaultdict(set)
    for src, tgt in edges:
        if src == tgt:
            continue
        adjacency[src].add(tgt)
        adjacency[tgt].add(src)
    for node in nodes:
        adjacency.setdefault(node, set())

    visited: set[str] = set()
    components: list[list[str]] = []
    for node in nodes:
        if node in visited:
            continue
        queue = deque([node])
        component: list[str] = []
        visited.add(node)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
        components.append(component)
    return components


def _leiden_partition(
    nodes: list[str], edges: list[tuple[str, str, float]]
) -> list[list[str]] | None:
    """Leiden clustering via ``leidenalg`` + ``python-igraph``.

    Returns ``None`` when either library is unavailable so callers can
    fall back. Weighted edges use the relation weight accumulated
    during extraction.
    """
    try:
        import igraph as ig  # type: ignore
        import leidenalg  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    if not edges:
        return None
    try:
        g = ig.Graph()
        g.add_vertices(nodes)
        g.add_edges([(src, tgt) for src, tgt, _ in edges])
        g.es["weight"] = [w for *_, w in edges]
        partition = leidenalg.find_partition(
            g,
            leidenalg.ModularityVertexPartition,
            weights="weight",
        )
        return [[g.vs[v]["name"] for v in cluster] for cluster in partition]
    except Exception as exc:  # noqa: BLE001
        logger.warning("leiden_failed err=%s falling_back_to_cc", exc)
        return None


async def _load_document_graph(
    owner_id: str, document_id: str
) -> tuple[dict[str, dict], list[tuple[str, str, float]]]:
    """Fetch all entities + relations for a document as adjacency lists."""
    entity_rows = await fetch_all(
        """
        SELECT id, name, entity_type, description
        FROM graph_entities
        WHERE owner_id = ? AND document_id = ?
        """,
        (owner_id, document_id),
    )
    entities = {row["id"]: row for row in entity_rows}

    relation_rows = await fetch_all(
        """
        SELECT source_entity_id, target_entity_id, weight
        FROM graph_relations
        WHERE owner_id = ? AND document_id = ?
        """,
        (owner_id, document_id),
    )
    edges: list[tuple[str, str, float]] = []
    for row in relation_rows:
        src = row["source_entity_id"]
        tgt = row["target_entity_id"]
        if src not in entities or tgt not in entities:
            continue
        try:
            weight = float(row.get("weight") or 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        edges.append((src, tgt, weight))
    return entities, edges


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------


_SUMMARY_SYSTEM_PROMPT = (
    "You write one-paragraph summaries of knowledge-graph communities. "
    "Given a list of entities and relations, describe the theme, the "
    "main actors, and the most salient relationships. Keep it under "
    "350 characters. Reply with plain prose only — no markdown, no "
    "preamble."
)


async def _summarize_community(
    *,
    entities: list[dict],
    relations: list[tuple[str, str, str]],
    provider: str,
    api_key: str,
    model: str,
) -> str | None:
    """One LLM call per community. Fail-open to ``None``."""
    if not api_key or not model:
        return None
    from backend.services.llm import create_openai_text, gemini_text

    lines: list[str] = ["ENTITIES:"]
    for ent in entities:
        desc = ent.get("description") or ""
        if desc and len(desc) > 120:
            desc = desc[:120] + "…"
        lines.append(f"- {ent['name']} ({ent.get('entity_type') or 'other'}): {desc}")
    lines.append("\nRELATIONS:")
    for src, tgt, rel_type in relations[:40]:
        lines.append(f"- {src} --[{rel_type}]--> {tgt}")

    user_prompt = (
        "\n".join(lines)
        + "\n\nWrite the summary of this community now."
    )
    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        if provider == "openai":
            raw = await create_openai_text(api_key, model, messages)
        else:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, gemini_text, api_key, model, messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_community_summary_failed err=%s", exc)
        return None
    summary = (raw or "").strip()
    return summary or None


def _community_label(entities: list[dict]) -> str:
    """Human-readable label: top two entity names joined by '&'."""
    if not entities:
        return "community"
    names = [e["name"] for e in entities[:2] if e.get("name")]
    if not names:
        return "community"
    return " & ".join(names)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def build_and_persist(
    *,
    owner_id: str,
    document_id: str,
    provider: str,
    api_key: str,
    model: str,
    summarize: bool = True,
) -> dict[str, int]:
    """Detect communities and persist them with optional per-community summaries.

    Returns a small observability dict:

    - ``communities``: how many rows we inserted into ``graph_communities``
    - ``entities_assigned``: how many ``community_entities`` rows
    - ``summarized``: how many communities received an LLM summary
    - ``algorithm``: the partition algorithm used this pass
    - ``skipped``: ``1`` when the feature flag short-circuited
    """
    result = {
        "communities": 0,
        "entities_assigned": 0,
        "summarized": 0,
        "algorithm": "none",
        "skipped": 0,
    }
    if not settings.retrieval_graph_enabled:
        result["skipped"] = 1
        return result

    entities_by_id, weighted_edges = await _load_document_graph(owner_id, document_id)
    if not entities_by_id:
        return result
    node_ids = list(entities_by_id.keys())

    clusters = _leiden_partition(node_ids, weighted_edges)
    algorithm = "leiden"
    if clusters is None:
        # Fallback: weakly-connected components.
        edges_cc = [(s, t) for s, t, _ in weighted_edges]
        clusters = _connected_components(set(node_ids), edges_cc)
        algorithm = "connected_components"

    min_size = max(1, settings.graph_community_min_size)
    max_entities = max(min_size, settings.graph_community_max_entities)
    filtered = [c for c in clusters if len(c) >= min_size]
    if not filtered:
        result["algorithm"] = algorithm
        return result

    # Fetch relation types per (src, tgt) so the summarizer can see labels.
    relation_lookup: dict[tuple[str, str], list[str]] = defaultdict(list)
    rel_rows = await fetch_all(
        """
        SELECT source_entity_id, target_entity_id, relation_type
        FROM graph_relations
        WHERE owner_id = ? AND document_id = ?
        """,
        (owner_id, document_id),
    )
    for row in rel_rows:
        relation_lookup[(row["source_entity_id"], row["target_entity_id"])].append(
            row["relation_type"]
        )

    communities: list[CommunityRecord] = []
    summary_tasks: list[asyncio.Task[str | None]] = []

    for cluster in filtered:
        members = cluster[:max_entities]
        entity_dicts = [entities_by_id[eid] for eid in members if eid in entities_by_id]
        if len(entity_dicts) < min_size:
            continue
        member_set = set(members)
        relations_in_cluster: list[tuple[str, str, str]] = []
        for (src, tgt), rel_types in relation_lookup.items():
            if src in member_set and tgt in member_set:
                src_name = entities_by_id[src]["name"]
                tgt_name = entities_by_id[tgt]["name"]
                for rt in rel_types:
                    relations_in_cluster.append((src_name, tgt_name, rt))

        record = CommunityRecord(
            label=_community_label(entity_dicts),
            entity_ids=members,
            algorithm=algorithm,
        )
        communities.append(record)

        if summarize and api_key and model:
            summary_tasks.append(
                asyncio.create_task(
                    _summarize_community(
                        entities=entity_dicts,
                        relations=relations_in_cluster,
                        provider=provider,
                        api_key=api_key,
                        model=model,
                    )
                )
            )
        else:
            summary_tasks.append(asyncio.create_task(_noop_summary()))

    summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)
    summarized = 0
    for record, summary in zip(communities, summaries, strict=True):
        if isinstance(summary, Exception):
            continue
        if summary:
            record.summary = summary
            summarized += 1

    community_rows = []
    entity_rows = []
    for record in communities:
        community_id = str(uuid.uuid4())
        community_rows.append(
            (
                community_id,
                owner_id,
                document_id,
                record.label,
                record.summary,
                len(record.entity_ids),
                record.algorithm,
            )
        )
        for entity_id in record.entity_ids:
            entity_rows.append((community_id, entity_id))

    if community_rows:
        await execute_many(
            """
            INSERT INTO graph_communities
                (id, owner_id, document_id, label, summary, entity_count, algorithm)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            community_rows,
        )
    if entity_rows:
        await execute_many(
            """
            INSERT INTO community_entities (community_id, entity_id) VALUES (?, ?)
            """,
            entity_rows,
        )

    result.update(
        {
            "communities": len(community_rows),
            "entities_assigned": len(entity_rows),
            "summarized": summarized,
            "algorithm": algorithm,
        }
    )
    return result


async def _noop_summary() -> str | None:
    """Placeholder task so the ``gather`` above stays uniform."""
    return None
