"""Unit tests for GraphRAG (Phase 3.3 + 3.4 + 3.5).

Covers:

- the lexical extractor fallback (no LLM)
- the LLM-driven extractor parse path (planner mocked)
- persistence (entity de-dupe, relation weight merging, replace-on-reingest)
- community detection (connected-components fallback + persistence)
- the traversal retrieval lane (seed selection + neighborhood ranking)

Every test monkeypatches the flag so the module's flag-off short
circuits don't hide behavior changes behind a disabled code path.
"""

from __future__ import annotations

import pytest

from backend.database import fetch_all
from backend.services import graph
from backend.services import graph_communities as communities
from backend.services import graph_retrieval


def test_extract_from_text_pulls_proper_nouns():
    text = (
        "Acme Corporation filed a patent with the United States Patent Office in 2021. "
        "The lead engineer was Jane Smith, working from the Boston office."
    )
    extraction = graph.extract_from_text(text)
    names = [e.name for e in extraction.entities]
    assert "Acme Corporation" in names or "Acme" in names
    assert any("Jane" in n for n in names)
    # Stop words must not sneak in
    assert all(n not in {"The", "This"} for n in names)


def test_extract_from_text_empty_input_returns_empty():
    assert graph.extract_from_text("").entities == []
    assert graph.extract_from_text(None).entities == []  # type: ignore[arg-type]


def test_extract_from_text_caps_entities():
    text = " ".join(f"Entity{i}Token" for i in range(100))
    assert len(graph.extract_from_text(text, max_entities=5).entities) <= 5


# ---------------------------------------------------------------------------
# LLM extractor parsing
# ---------------------------------------------------------------------------


def test_clean_llm_response_unfences_and_balances():
    raw = 'Here is the graph:\n```json\n{"entities": [], "relations": []}\n```\ntrailing'
    data = graph._clean_llm_response(raw)
    assert data == {"entities": [], "relations": []}


def test_clean_llm_response_returns_none_on_garbage():
    assert graph._clean_llm_response("no braces") is None
    assert graph._clean_llm_response("") is None
    assert graph._clean_llm_response("{unterminated") is None


def test_parse_extraction_payload_filters_dangling_relations():
    data = {
        "entities": [
            {"name": "Alice", "entity_type": "person"},
            {"name": "Acme", "entity_type": "organization"},
            {"name": "  ", "entity_type": "other"},  # dropped (empty name)
        ],
        "relations": [
            {"source": "Alice", "target": "Acme", "relation_type": "works_at"},
            {"source": "Alice", "target": "Unknown", "relation_type": "knows"},
            {"source": "X", "target": "Y", "relation_type": ""},  # dropped
        ],
    }
    result = graph._parse_extraction_payload(data)
    names = [e.name for e in result.entities]
    assert names == ["Alice", "Acme"]
    # Only the Alice→Acme edge survives because Unknown isn't in entities.
    assert [(r.source, r.target, r.relation_type) for r in result.relations] == [
        ("Alice", "Acme", "works_at"),
    ]


def test_parse_extraction_payload_deduplicates_by_case_folded_name():
    data = {
        "entities": [
            {"name": "acme", "entity_type": "organization"},
            {"name": "Acme", "entity_type": "organization"},  # duplicate
        ],
        "relations": [],
    }
    result = graph._parse_extraction_payload(data)
    assert [e.name for e in result.entities] == ["acme"]


@pytest.mark.asyncio
async def test_extract_from_chunks_parallelizes_and_merges(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)

    async def fake_call(*, provider, api_key, model, passage):
        # Mimic the LLM: emit one entity with a name derived from the passage prefix.
        tag = passage.split()[0]
        return graph.ExtractionResult(
            entities=[graph.ExtractedEntity(name=tag)],
            relations=[],
        )

    monkeypatch.setattr(graph, "_call_extraction_llm", fake_call)

    result = await graph.extract_from_chunks(
        ["alpha chunk one", "beta chunk two", "alpha duplicate"],
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    names = sorted(e.name for e in result.entities)
    assert names == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_extract_from_chunks_short_circuits_when_flag_off(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", False)

    async def blowup(**_kw):
        raise AssertionError("should not call LLM when flag off")

    monkeypatch.setattr(graph, "_call_extraction_llm", blowup)
    result = await graph.extract_from_chunks(
        ["anything"], provider="openai", api_key="sk", model="gpt-4o-mini"
    )
    assert result.entities == []


@pytest.mark.asyncio
async def test_extract_from_chunks_falls_back_to_lexical_without_creds(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)

    async def blowup(**_kw):
        raise AssertionError("should not call LLM without api_key")

    monkeypatch.setattr(graph, "_call_extraction_llm", blowup)
    result = await graph.extract_from_chunks(
        ["Jane Smith joined Acme Corp in 2020."],
        provider="openai",
        api_key="",
        model="gpt-4o-mini",
    )
    # Lexical fallback pulls proper nouns.
    assert any("Jane" in e.name for e in result.entities)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_extraction_skips_when_flag_off(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", False)
    out = await graph.persist_extraction(
        owner_id="o",
        document_id="d",
        extraction=graph.ExtractionResult(
            entities=[graph.ExtractedEntity(name="Foo")]
        ),
    )
    assert out == {"entities": 0, "relations": 0, "skipped": 1}


async def _seed_document(owner_id: str, document_id: str) -> None:
    """Insert a minimal documents row so FK-bound graph rows can attach."""
    from backend.database import execute, fetch_one

    existing = await fetch_one("SELECT id FROM documents WHERE id = ?", (document_id,))
    if existing:
        return
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status)
        VALUES (?, ?, 'seed.txt', 'openai', 'text-embedding-3-small',
                'text/plain', ?, 0, 0, 'ready')
        """,
        (document_id, owner_id, f"chk-{document_id}"),
    )


@pytest.mark.asyncio
async def test_persist_extraction_inserts_entities_and_merges_relations(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)
    owner_id = "anon:graph-test"
    document_id = "doc-graph-persist"
    await _seed_document(owner_id, document_id)

    extraction = graph.ExtractionResult(
        entities=[
            graph.ExtractedEntity(name="Alice", entity_type="person"),
            graph.ExtractedEntity(name="alice"),  # dedupe
            graph.ExtractedEntity(name="Acme", entity_type="organization"),
        ],
        relations=[
            graph.ExtractedRelation(source="Alice", target="Acme", relation_type="works_at", weight=1.0),
            graph.ExtractedRelation(source="Alice", target="Acme", relation_type="works_at", weight=2.0),
            graph.ExtractedRelation(source="Acme", target="Alice", relation_type="employs", weight=1.0),
        ],
    )
    counts = await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=extraction,
        replace=True,
    )
    assert counts["entities"] == 2
    # Two (src,tgt,rel_type) combos survive; works_at weight summed to 3.0.
    assert counts["relations"] == 2
    rel_rows = await fetch_all(
        "SELECT relation_type, weight FROM graph_relations WHERE document_id = ? ORDER BY relation_type",
        (document_id,),
    )
    rel_map = {row["relation_type"]: float(row["weight"]) for row in rel_rows}
    assert rel_map["works_at"] == pytest.approx(3.0)
    assert rel_map["employs"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_persist_extraction_replace_clears_prior_rows(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)
    owner_id = "anon:graph-replace"
    document_id = "doc-graph-replace"
    await _seed_document(owner_id, document_id)

    await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=graph.ExtractionResult(
            entities=[graph.ExtractedEntity(name="First")],
        ),
        replace=True,
    )
    await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=graph.ExtractionResult(
            entities=[graph.ExtractedEntity(name="Second")],
        ),
        replace=True,
    )
    rows = await fetch_all(
        "SELECT name FROM graph_entities WHERE document_id = ?",
        (document_id,),
    )
    names = [row["name"] for row in rows]
    assert names == ["Second"]


# ---------------------------------------------------------------------------
# entity_neighborhood
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_neighborhood_returns_empty_when_flag_off(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", False)
    assert await graph.entity_neighborhood(owner_id="o", entity_names=["x"]) == []


@pytest.mark.asyncio
async def test_entity_neighborhood_expands_one_hop(monkeypatch):
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)
    owner_id = "anon:graph-bfs"
    document_id = "doc-graph-bfs"
    await _seed_document(owner_id, document_id)

    extraction = graph.ExtractionResult(
        entities=[
            graph.ExtractedEntity(name="Root"),
            graph.ExtractedEntity(name="Child"),
            graph.ExtractedEntity(name="Orphan"),
        ],
        relations=[
            graph.ExtractedRelation(source="Root", target="Child", relation_type="has"),
        ],
    )
    await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=extraction,
        replace=True,
    )

    neighbourhood = await graph.entity_neighborhood(
        owner_id=owner_id, entity_names=["Root"], hops=1, limit=10
    )
    names = {row["name"] for row in neighbourhood}
    assert {"Root", "Child"}.issubset(names)
    assert "Orphan" not in names


# ---------------------------------------------------------------------------
# Community detection
# ---------------------------------------------------------------------------


def test_connected_components_groups_linked_nodes():
    nodes = {"a", "b", "c", "d", "e"}
    edges = [("a", "b"), ("b", "c"), ("d", "e")]
    components = communities._connected_components(nodes, edges)
    assert {frozenset(c) for c in components} == {
        frozenset({"a", "b", "c"}),
        frozenset({"d", "e"}),
    }


@pytest.mark.asyncio
async def test_build_and_persist_uses_fallback_when_leiden_unavailable(monkeypatch):
    monkeypatch.setattr(communities.settings, "retrieval_graph_enabled", True)
    monkeypatch.setattr(communities.settings, "graph_community_min_size", 2)
    monkeypatch.setattr(communities.settings, "graph_community_max_entities", 10)

    owner_id = "anon:graph-community"
    document_id = "doc-graph-community"
    await _seed_document(owner_id, document_id)

    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)
    await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=graph.ExtractionResult(
            entities=[
                graph.ExtractedEntity(name="Node1"),
                graph.ExtractedEntity(name="Node2"),
                graph.ExtractedEntity(name="Node3"),
                graph.ExtractedEntity(name="Loner"),
            ],
            relations=[
                graph.ExtractedRelation(source="Node1", target="Node2", relation_type="rel"),
                graph.ExtractedRelation(source="Node2", target="Node3", relation_type="rel"),
            ],
        ),
        replace=True,
    )

    # Force fallback by disabling leiden even if installed.
    monkeypatch.setattr(communities, "_leiden_partition", lambda *a, **kw: None)

    # No API key → summarizer skipped, but detection still runs.
    result = await communities.build_and_persist(
        owner_id=owner_id,
        document_id=document_id,
        provider="openai",
        api_key="",
        model="gpt-4o-mini",
        summarize=False,
    )
    assert result["communities"] >= 1
    assert result["algorithm"] == "connected_components"
    rows = await fetch_all(
        "SELECT entity_count FROM graph_communities WHERE document_id = ?",
        (document_id,),
    )
    assert any(row["entity_count"] >= 2 for row in rows)


# ---------------------------------------------------------------------------
# Graph-traversal retrieval lane
# ---------------------------------------------------------------------------


def test_tokenize_question_drops_short_tokens():
    tokens = graph_retrieval._tokenize_question("Is the budget over $5,000?")
    assert "is" not in tokens  # too short
    assert "budget" in tokens
    assert "over" in tokens


@pytest.mark.asyncio
async def test_graph_lane_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_traversal_enabled", False)
    result = await graph_retrieval.graph_lane_search(
        owner_id="o", document_ids=["d"], question="anything", top_k=5
    )
    assert result.chunks == []
    assert result.stats == {"enabled": False}


@pytest.mark.asyncio
async def test_graph_lane_returns_chunks_when_seeds_match(monkeypatch):
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_enabled", True)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_traversal_enabled", True)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_hops", 1)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_seed_limit", 6)
    monkeypatch.setattr(graph_retrieval.settings, "retrieval_graph_chunk_limit", 5)
    monkeypatch.setattr(graph.settings, "retrieval_graph_enabled", True)

    owner_id = "anon:graph-lane"
    document_id = "doc-graph-lane"
    await _seed_document(owner_id, document_id)

    # Insert one chunk that mentions a seed entity.
    from backend.database import execute

    await execute(
        """
        INSERT INTO document_chunks (
            id, document_id, owner_id, chunk_index, content, page_number,
            parent_content, chunk_type, metadata_json, embedding_json
        ) VALUES (?, ?, ?, 0, ?, NULL, NULL, 'text', NULL, '[]')
        """,
        (
            "chunk-lane-1",
            document_id,
            owner_id,
            "Acme Corp announced a new partnership with Globex.",
        ),
    )
    await graph.persist_extraction(
        owner_id=owner_id,
        document_id=document_id,
        extraction=graph.ExtractionResult(
            entities=[
                graph.ExtractedEntity(name="Acme"),
                graph.ExtractedEntity(name="Globex"),
            ],
            relations=[
                graph.ExtractedRelation(
                    source="Acme", target="Globex", relation_type="partners_with"
                )
            ],
        ),
        replace=True,
    )

    result = await graph_retrieval.graph_lane_search(
        owner_id=owner_id,
        document_ids=[document_id],
        question="What did Acme announce?",
        top_k=5,
    )
    assert result.chunks, f"expected at least one graph-lane chunk; got stats={result.stats}"
    assert any("Acme" in chunk.excerpt for chunk in result.chunks)
    assert "Acme" in (result.stats.get("seeds") or [])
