"""Tests for the Phase 3.9 active-learning hint helper.

These tests live outside ``test_memory.py`` / ``test_agent.py`` because
the helper sits in ``backend/routers/chat.py`` — testing it via the
full HTTP round-trip would require live provider keys. We import the
private helper directly and exercise its branches in isolation.
"""

from __future__ import annotations

from backend.routers import chat as chat_router
from backend.services.vectorstore import RetrievedChunk


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        excerpt="x",
        score=score,
        page_number=None,
    )


def test_hint_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "active_learning_hint_enabled", False)
    assert chat_router._compute_active_learning_hint({}, [_chunk(0.1)]) is None


def test_hint_fires_on_low_confidence(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "active_learning_hint_enabled", True)
    monkeypatch.setattr(chat_router.settings, "active_learning_score_floor", 0.5)
    hint = chat_router._compute_active_learning_hint({}, [_chunk(0.3)])
    assert hint is not None
    assert hint["action"] == "expand_search"
    assert hint["reason"] == "low_confidence"
    assert hint["best_score"] == 0.3


def test_hint_skipped_on_strong_retrieval(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "active_learning_hint_enabled", True)
    monkeypatch.setattr(chat_router.settings, "active_learning_score_floor", 0.3)
    assert chat_router._compute_active_learning_hint({}, [_chunk(0.9)]) is None


def test_hint_fires_on_planner_abstain(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "active_learning_hint_enabled", True)
    monkeypatch.setattr(chat_router.settings, "active_learning_score_floor", 0.1)
    hint = chat_router._compute_active_learning_hint(
        {"stopped_reason": "planner_abstain"}, [_chunk(0.99)]
    )
    assert hint is not None
    assert hint["reason"] == "planner_abstain"
    assert hint["action"] == "rephrase"


def test_hint_fires_on_empty_chunks(monkeypatch):
    monkeypatch.setattr(chat_router.settings, "active_learning_hint_enabled", True)
    hint = chat_router._compute_active_learning_hint({}, [])
    assert hint is not None
    assert hint["reason"] == "no_chunks"
