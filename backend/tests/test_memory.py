"""Unit tests for Phase 3.7 conversation memory.

These tests deliberately avoid hitting a real LLM — the summarization
call is monkey-patched. The goal is to verify the memory context
contract the chat router relies on:

1. When the flag is off we return plain last-N history and no summary.
2. When history fits in the recent-turn window we short-circuit without
   calling the LLM.
3. When history exceeds the window we invoke the summarizer and
   persist the result.
4. When the LLM call fails we fall back gracefully to the prior summary.
5. ``inject_summary_into_messages`` slots the memory system message in
   the right position.
"""

from __future__ import annotations

import pytest

from backend.services import memory


def _turn(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


def _long_history(n_pairs: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i in range(n_pairs):
        out.append(_turn("user", f"q{i}"))
        out.append(_turn("assistant", f"a{i}"))
    return out


@pytest.mark.asyncio
async def test_memory_disabled_returns_history_verbatim(monkeypatch):
    monkeypatch.setattr(memory.settings, "memory_enabled", False)
    monkeypatch.setattr(memory.settings, "memory_recent_turns", 4)

    called = {"llm": 0}

    async def fail_llm(*_a, **_kw):
        called["llm"] += 1
        raise AssertionError("should not hit LLM when memory disabled")

    monkeypatch.setattr(memory, "_call_llm", fail_llm)

    history = _long_history(5)
    ctx = await memory.build_context(
        conversation_id="conv-1",
        owner_id="owner-1",
        history=history,
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert ctx.summary is None
    # Fallback path uses max_conversation_history, not memory_recent_turns.
    assert ctx.recent == history[-memory.settings.max_conversation_history :]
    assert ctx.stages["memory_enabled"] is False
    assert called["llm"] == 0


@pytest.mark.asyncio
async def test_memory_short_history_skips_llm(monkeypatch):
    monkeypatch.setattr(memory.settings, "memory_enabled", True)
    monkeypatch.setattr(memory.settings, "memory_recent_turns", 6)

    async def fake_load_summary(_cid, _owner):
        return None, 0

    monkeypatch.setattr(memory, "load_summary", fake_load_summary)

    async def fail_llm(*_a, **_kw):
        raise AssertionError("should not summarize when history fits")

    monkeypatch.setattr(memory, "_call_llm", fail_llm)

    history = _long_history(2)  # 4 messages, under 6-turn window
    ctx = await memory.build_context(
        conversation_id="conv-1",
        owner_id="owner-1",
        history=history,
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert ctx.summary is None
    assert ctx.recent == history
    assert ctx.stages["memory_state"] == "cold"


@pytest.mark.asyncio
async def test_memory_long_history_summarizes_and_persists(monkeypatch):
    monkeypatch.setattr(memory.settings, "memory_enabled", True)
    monkeypatch.setattr(memory.settings, "memory_recent_turns", 2)
    monkeypatch.setattr(memory.settings, "memory_summary_max_chars", 400)

    async def fake_load_summary(_cid, _owner):
        return None, 0

    monkeypatch.setattr(memory, "load_summary", fake_load_summary)

    captured: dict = {}

    async def fake_llm(provider, api_key, model, messages):
        captured["messages"] = messages
        return "Rolling summary: user asked about invoices; assistant cited page 2."

    monkeypatch.setattr(memory, "_call_llm", fake_llm)

    persisted: dict = {}

    async def fake_upsert(*, conversation_id, owner_id, summary, turn_count):
        persisted.update(
            conversation_id=conversation_id,
            owner_id=owner_id,
            summary=summary,
            turn_count=turn_count,
        )

    monkeypatch.setattr(memory, "_upsert_summary", fake_upsert)

    history = _long_history(5)  # 10 messages — well past the 2-turn window
    ctx = await memory.build_context(
        conversation_id="conv-1",
        owner_id="owner-1",
        history=history,
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert ctx.summary is not None
    assert "invoices" in ctx.summary
    assert ctx.recent == history[-2:]
    assert persisted["conversation_id"] == "conv-1"
    assert persisted["turn_count"] == 5  # 5 user messages
    assert ctx.stages["memory_state"] == "refreshed"
    # Prompt should reference the older slice (not the recent window).
    user_prompt = captured["messages"][1]["content"]
    assert "OLDER TURNS TO INCORPORATE" in user_prompt
    assert "q0" in user_prompt and "q2" in user_prompt


@pytest.mark.asyncio
async def test_memory_llm_failure_falls_back_to_prior_summary(monkeypatch):
    monkeypatch.setattr(memory.settings, "memory_enabled", True)
    monkeypatch.setattr(memory.settings, "memory_recent_turns", 2)

    async def fake_load_summary(_cid, _owner):
        return "existing summary blob", 3

    monkeypatch.setattr(memory, "load_summary", fake_load_summary)

    async def blowup(*_a, **_kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(memory, "_call_llm", blowup)

    history = _long_history(5)
    ctx = await memory.build_context(
        conversation_id="conv-1",
        owner_id="owner-1",
        history=history,
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert ctx.summary == "existing summary blob"
    assert ctx.stages["memory_state"] == "llm_failed"


def test_memory_skips_resummarize_when_no_new_turns(monkeypatch):
    """Integration-style: a conversation re-opened with no new user turn
    should reuse the stored summary without calling the LLM."""
    import asyncio

    monkeypatch.setattr(memory.settings, "memory_enabled", True)
    monkeypatch.setattr(memory.settings, "memory_recent_turns", 2)

    async def fake_load_summary(_cid, _owner):
        # Prior summary captured 5 paired turns, same as current history.
        return "cached summary", 5

    monkeypatch.setattr(memory, "load_summary", fake_load_summary)

    async def fail_llm(*_a, **_kw):
        raise AssertionError("should not resummarize when no new turns")

    monkeypatch.setattr(memory, "_call_llm", fail_llm)

    history = _long_history(5)
    ctx = asyncio.run(
        memory.build_context(
            conversation_id="conv-1",
            owner_id="owner-1",
            history=history,
            provider="openai",
            api_key="sk-test",
            model="gpt-4o-mini",
        )
    )
    assert ctx.summary == "cached summary"
    assert ctx.stages["memory_state"] == "reused"


def test_inject_summary_places_memory_after_first_system_message():
    messages = [
        {"role": "system", "content": "primary system"},
        {"role": "user", "content": "context"},
        {"role": "user", "content": "question"},
    ]
    injected = memory.inject_summary_into_messages(messages, "mem blob")
    assert injected[0]["role"] == "system" and injected[0]["content"] == "primary system"
    assert injected[1]["role"] == "system"
    assert "mem blob" in injected[1]["content"]
    assert injected[2:] == messages[1:]


def test_inject_summary_noop_on_empty_summary():
    messages = [{"role": "system", "content": "sys"}]
    assert memory.inject_summary_into_messages(messages, None) == messages
    assert memory.inject_summary_into_messages(messages, "") == messages
