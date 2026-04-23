"""Unit tests for Phase 3.1 + 3.2 + 3.6 — agentic retrieval loop.

We mock the planner LLM and the retrieval pipeline so the loop's
control flow is exercised in isolation. End-to-end behaviour through
``/api/chat`` is exercised by the existing integration tests once the
``RETRIEVAL_AGENT_ENABLED`` flag is turned on — those live in
``test_api_v2.py`` so the flag-off path stays the default.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services import agent, agent_tools
from backend.services.agent_tools import AgentToolContext, ToolResult
from backend.services.vectorstore import RetrievedChunk


def _chunk(cid: str, doc: str = "doc-a", score: float = 0.8) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        document_id=doc,
        excerpt=f"excerpt for {cid}",
        score=score,
        page_number=None,
    )


def _ctx() -> AgentToolContext:
    return AgentToolContext(
        owner_id="owner-1",
        provider="openai",
        provider_api_key="sk-test",
        primary_document_id="doc-a",
        allowed_document_ids=["doc-a", "doc-b"],
        embedding_model="text-embedding-3-small",
        top_k=5,
    )


# ---------------------------------------------------------------------------
# JSON extraction + argument validation
# ---------------------------------------------------------------------------


def test_extract_json_unfences_and_balances():
    raw = "Thinking…\n```json\n{\"action\":\"answer\"}\n```\ntrailing prose"
    assert agent._extract_json(raw) == {"action": "answer"}


def test_extract_json_returns_none_on_garbage():
    assert agent._extract_json("no braces here") is None
    assert agent._extract_json("{unterminated") is None
    assert agent._extract_json("") is None


def test_coerce_doc_ids_filters_unknown():
    ctx = _ctx()
    assert agent_tools._coerce_doc_ids(["doc-a", "doc-c"], ctx) == ["doc-a"]
    assert agent_tools._coerce_doc_ids("doc-b", ctx) == ["doc-b"]
    assert agent_tools._coerce_doc_ids(None, ctx) == []


def test_require_str_trims_and_validates():
    with pytest.raises(agent_tools.ToolArgumentError):
        agent_tools._require_str({"q": ""}, "q")
    assert agent_tools._require_str({"q": "  hello "}, "q") == "hello"


def test_optional_int_clamps_range():
    assert agent_tools._optional_int({}, "k", default=5, minimum=1, maximum=20) == 5
    assert agent_tools._optional_int({"k": 100}, "k", default=5, minimum=1, maximum=20) == 20
    assert agent_tools._optional_int({"k": 0}, "k", default=5, minimum=1, maximum=20) == 1


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def test_tool_schemas_matches_registry():
    schemas = agent_tools.tool_schemas_for_planner()
    names = [s["function"]["name"] for s in schemas]
    assert set(names) == set(agent_tools.TOOL_DEFINITIONS.keys())
    for schema in schemas:
        assert "parameters" in schema["function"]
        assert schema["type"] == "function"


@pytest.mark.asyncio
async def test_execute_tool_rejects_unknown():
    with pytest.raises(agent_tools.ToolArgumentError):
        await agent_tools.execute_tool(name="nope", args={}, ctx=_ctx())


@pytest.mark.asyncio
async def test_execute_tool_respects_call_budget(monkeypatch):
    monkeypatch.setattr(agent_tools.settings, "retrieval_agent_max_tool_calls", 1)
    ctx = _ctx()
    ctx.trace.append({"tool": "x", "args": {}, "new_chunks": 0, "total_chunks": 0})
    with pytest.raises(agent_tools.ToolArgumentError, match="budget"):
        await agent_tools.execute_tool(name="search_chunks", args={"query": "q"}, ctx=ctx)


@pytest.mark.asyncio
async def test_search_chunks_tool_dedupes_and_caps_chunks(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr(agent_tools.settings, "retrieval_agent_max_chunks", 2)

    async def fake_embed(*_a, **_kw):
        return [0.0, 1.0]

    class FakeResult:
        def __init__(self, chunks):
            self.chunks = chunks
            self.stages = {"dense_hits": len(chunks)}

    async def fake_retrieve(req, **_kw):
        return FakeResult([_chunk("c1"), _chunk("c2"), _chunk("c3")])

    monkeypatch.setattr(agent_tools, "embed_query", fake_embed)
    monkeypatch.setattr(agent_tools, "retrieve", fake_retrieve)

    result = await agent_tools.execute_tool(
        name="search_chunks", args={"query": "what"}, ctx=ctx
    )
    assert len(ctx.collected_chunks) == 2  # capped by MAX_CHUNKS
    assert [c.chunk_id for c in ctx.collected_chunks] == ["c1", "c2"]
    assert result.payload["new_chunks"] == 2

    # Second call with the same chunks must not grow the collected pool
    # (dedupe by chunk_id, even though the cap is already reached).
    result2 = await agent_tools.execute_tool(
        name="search_chunks", args={"query": "what again"}, ctx=ctx
    )
    assert len(ctx.collected_chunks) == 2
    assert result2.payload["new_chunks"] == 0


@pytest.mark.asyncio
async def test_compare_documents_requires_two_ids(monkeypatch):
    ctx = _ctx()

    async def fake_embed(*_a, **_kw):
        return [0.0, 1.0]

    monkeypatch.setattr(agent_tools, "embed_query", fake_embed)
    with pytest.raises(agent_tools.ToolArgumentError):
        await agent_tools.execute_tool(
            name="compare_documents",
            args={"query": "q", "document_ids": ["doc-a"]},
            ctx=ctx,
        )


@pytest.mark.asyncio
async def test_compare_documents_aggregates_per_doc(monkeypatch):
    ctx = _ctx()

    async def fake_embed(*_a, **_kw):
        return [0.0, 1.0]

    class FakeResult:
        def __init__(self, chunks):
            self.chunks = chunks
            self.stages = {}

    async def fake_retrieve(req, **_kw):
        # Each call sees one doc in req.document_ids; return chunks tied to it.
        doc_id = req.document_ids[0]
        return FakeResult([_chunk(f"{doc_id}-1", doc=doc_id, score=0.9 if doc_id == "doc-a" else 0.5)])

    monkeypatch.setattr(agent_tools, "embed_query", fake_embed)
    monkeypatch.setattr(agent_tools, "retrieve", fake_retrieve)

    result = await agent_tools.execute_tool(
        name="compare_documents",
        args={"query": "q", "document_ids": ["doc-a", "doc-b"]},
        ctx=ctx,
    )
    per_doc = result.payload["per_document"]
    assert [d["document_id"] for d in per_doc] == ["doc-a", "doc-b"]
    # Sorted by best_score desc
    assert per_doc[0]["best_score"] >= per_doc[1]["best_score"]
    assert len(ctx.collected_chunks) == 2


# ---------------------------------------------------------------------------
# Agent loop control flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_answers_after_single_tool_call(monkeypatch):
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_iterations", 4)
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_chunks", 8)

    # Planner script: call search_chunks then answer.
    planner_replies = iter([
        '{"action":"call_tool","tool":"search_chunks","args":{"query":"invoices"}}',
        '{"action":"answer","thought":"have enough"}',
    ])

    async def fake_planner(**_kw):
        return next(planner_replies)

    async def fake_search(ctx, args):
        chunks = [_chunk("c1", score=0.7), _chunk("c2", score=0.6)]
        ctx.collected_chunks.extend(chunks)
        return ToolResult(payload={"new_chunks": 2}, new_chunks=chunks)

    monkeypatch.setattr(agent, "_call_planner", fake_planner)
    # Intercept execute_tool so we skip real embedding/retrieval.
    async def fake_exec(name, args, ctx):
        if name != "search_chunks":
            raise agent_tools.ToolArgumentError(f"unexpected {name}")
        return await fake_search(ctx, args)

    with patch.object(agent, "execute_tool", side_effect=fake_exec):
        result = await agent.run_agent(
            question="What invoices are overdue?",
            owner_id="owner-1",
            provider="openai",
            provider_api_key="sk-test",
            chat_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            primary_document_id="doc-a",
            allowed_document_ids=["doc-a"],
            top_k=2,
        )

    assert result.iterations == 2
    assert result.stopped_reason == "planner_answer"
    assert [c.chunk_id for c in result.chunks] == ["c1", "c2"]
    assert result.confidence > 0
    assert result.per_document_confidence.get("doc-a") == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_agent_stops_on_chunk_budget(monkeypatch):
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_iterations", 4)
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_chunks", 2)
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_tool_calls", 8)

    planner_replies = iter([
        '{"action":"call_tool","tool":"search_chunks","args":{"query":"a"}}',
        '{"action":"call_tool","tool":"search_chunks","args":{"query":"b"}}',
        '{"action":"answer"}',
    ])

    async def fake_planner(**_kw):
        return next(planner_replies)

    async def fake_exec(name, args, ctx):
        # Each call returns one new chunk.
        new_chunk = _chunk(f"c{len(ctx.collected_chunks) + 1}")
        ctx.collected_chunks.append(new_chunk)
        return ToolResult(payload={}, new_chunks=[new_chunk])

    monkeypatch.setattr(agent, "_call_planner", fake_planner)
    with patch.object(agent, "execute_tool", side_effect=fake_exec):
        result = await agent.run_agent(
            question="q",
            owner_id="owner-1",
            provider="openai",
            provider_api_key="sk-test",
            chat_model="gpt-4o-mini",
            embedding_model="e",
            primary_document_id="doc-a",
            allowed_document_ids=["doc-a"],
            top_k=5,
        )
    assert result.stopped_reason == "chunk_budget_reached"
    assert len(result.chunks) == 2


@pytest.mark.asyncio
async def test_agent_parse_failures_bail_out(monkeypatch):
    monkeypatch.setattr(agent.settings, "retrieval_agent_max_iterations", 4)

    async def fake_planner(**_kw):
        return "I don't know how to respond in JSON."

    async def fallback_search(name, args, ctx):
        # _fallback_search path gets triggered — return one chunk so
        # we can assert the safety net works. execute_tool is called
        # with keyword args (name=, args=, ctx=) so we mirror that shape.
        new = _chunk("fallback-1", score=0.4)
        ctx.collected_chunks.append(new)
        return ToolResult(payload={}, new_chunks=[new])

    monkeypatch.setattr(agent, "_call_planner", fake_planner)
    with patch.object(agent, "execute_tool", side_effect=fallback_search):
        result = await agent.run_agent(
            question="q",
            owner_id="owner-1",
            provider="openai",
            provider_api_key="sk-test",
            chat_model="gpt-4o-mini",
            embedding_model="e",
            primary_document_id="doc-a",
            allowed_document_ids=["doc-a"],
            top_k=5,
        )
    assert result.stopped_reason == "planner_parse_failed"
    assert len(result.chunks) == 1  # fallback search rescued us


@pytest.mark.asyncio
async def test_agent_abstains_cleanly(monkeypatch):
    async def fake_planner(**_kw):
        return '{"action":"abstain","reason":"chit chat"}'

    async def never(*_a, **_kw):
        raise AssertionError("execute_tool must not be called")

    monkeypatch.setattr(agent, "_call_planner", fake_planner)
    with patch.object(agent, "execute_tool", side_effect=never):
        result = await agent.run_agent(
            question="hi",
            owner_id="owner-1",
            provider="openai",
            provider_api_key="sk-test",
            chat_model="gpt-4o-mini",
            embedding_model="e",
            primary_document_id="doc-a",
            allowed_document_ids=["doc-a"],
            top_k=5,
        )
    assert result.stopped_reason == "planner_abstain"
    assert result.chunks == []
    assert result.stages["agent_chunk_count"] == 0


@pytest.mark.asyncio
async def test_agent_short_circuits_when_no_documents(monkeypatch):
    """If the caller hands the agent an empty doc list we must not even
    try to call the planner LLM — this prevents burning tokens on a
    conversation whose scope has been revoked."""
    calls = {"planner": 0, "tools": 0}

    async def fake_planner(**_kw):
        calls["planner"] += 1
        return "{}"

    async def fake_exec(*_a, **_kw):
        calls["tools"] += 1
        return ToolResult(payload={}, new_chunks=[])

    monkeypatch.setattr(agent, "_call_planner", fake_planner)
    with patch.object(agent, "execute_tool", side_effect=fake_exec):
        result = await agent.run_agent(
            question="q",
            owner_id="owner-1",
            provider="openai",
            provider_api_key="sk-test",
            chat_model="gpt-4o-mini",
            embedding_model="e",
            primary_document_id="",
            allowed_document_ids=[],
            top_k=5,
        )
    assert result.stopped_reason == "no_documents"
    assert calls == {"planner": 0, "tools": 0}


def test_score_confidence_averages_top_three():
    chunks = [
        _chunk("a", score=0.9),
        _chunk("b", score=0.7),
        _chunk("c", score=0.5),
        _chunk("d", score=0.1),
    ]
    conf, per_doc = agent._score_confidence(chunks)
    assert conf == pytest.approx((0.9 + 0.7 + 0.5) / 3)
    assert per_doc == {"doc-a": pytest.approx(0.9)}


def test_score_confidence_handles_empty():
    assert agent._score_confidence([]) == (0.0, {})
