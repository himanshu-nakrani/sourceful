"""Tests for groundedness verifier module."""

from __future__ import annotations

import pytest

from backend.services.grounding import (
    _split_sentences,
    _parse_response,
    _build_prompt,
    verify_groundedness,
)
from backend.models import Citation


def test_split_sentences():
    text = "First sentence. Second one! Third? And the last."
    sents = _split_sentences(text)
    assert len(sents) == 4
    assert sents[0] == "First sentence."


def test_parse_response_valid_json():
    raw = '{"sentences":[{"text":"Answer sentence one.","citations":[0],"supported":true}],"score":0.95}'
    parsed = _parse_response(raw, "Answer sentence one.")
    assert parsed is not None
    assert parsed["score"] == 0.95
    assert len(parsed["sentences"]) == 1
    assert parsed["sentences"][0]["supported"] is True


def test_parse_response_with_code_fences():
    raw = '```json\n{"sentences":[{"text":"Test.","citations":[],"supported":false}],"score":0.5}\n```'
    parsed = _parse_response(raw, "Test.")
    assert parsed is not None
    assert parsed["score"] == 0.5


def test_parse_response_malformed_returns_none():
    raw = "not valid json"
    parsed = _parse_response(raw, "Some answer.")
    assert parsed is None


def test_parse_response_empty_returns_fallback():
    # When response is valid JSON but sentences empty, falls back to lexical split
    raw = '{"sentences":[],"score":null}'
    parsed = _parse_response(raw, "First sentence. Second sentence.")
    assert parsed is not None
    assert len(parsed["sentences"]) == 2


def test_build_prompt_structure():
    sources = [
        Citation(
            chunk_id="c1",
            document_id="d1",
            excerpt="Source one excerpt.",
            score=0.9,
            page_number=1,
        ),
        Citation(
            chunk_id="c2",
            document_id="d1",
            excerpt="Source two excerpt.",
            score=0.8,
            page_number=2,
        ),
    ]
    messages = _build_prompt("The answer is here.", sources)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # Should include source numbering
    assert "[0]" in messages[1]["content"]
    assert "[1]" in messages[1]["content"]


@pytest.mark.asyncio
async def test_verify_groundedness_disabled(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={"groundedness_verifier_enabled": False}))

    result = await verify_groundedness(
        answer="Test answer.",
        sources=[],
        provider="openai",
        api_key="k",
        model="m",
    )
    assert result["enabled"] is False
    assert result["verified"] is None


@pytest.mark.asyncio
async def test_verify_groundedness_no_answer_or_sources(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={"groundedness_verifier_enabled": True}))

    # Empty answer
    result = await verify_groundedness(
        answer="",
        sources=[Citation(chunk_id="c1", document_id="d1", excerpt="Excerpt.", score=0.9)],
        provider="openai",
        api_key="k",
        model="m",
    )
    assert result["enabled"] is True
    assert result["verified"] is None

    # Empty sources
    result = await verify_groundedness(
        answer="Answer.",
        sources=[],
        provider="openai",
        api_key="k",
        model="m",
    )
    assert result["enabled"] is True
    assert result["verified"] is None


@pytest.mark.asyncio
async def test_verify_groundedness_happy_path(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={
        "groundedness_verifier_enabled": True,
        "groundedness_min_score": 0.7,
    }))

    async def fake_call(provider, api_key, model, messages):
        return '{"sentences":[{"text":"Answer.","citations":[0],"supported":true}],"score":0.85}'

    monkeypatch.setattr("backend.services.grounding._call", fake_call)

    result = await verify_groundedness(
        answer="Answer.",
        sources=[Citation(chunk_id="c1", document_id="d1", excerpt="Source.", score=0.9)],
        provider="openai",
        api_key="k",
        model="m",
    )
    assert result["enabled"] is True
    assert result["verified"] is True
    assert result["score"] == 0.85


@pytest.mark.asyncio
async def test_verify_groundedness_below_threshold(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={
        "groundedness_verifier_enabled": True,
        "groundedness_min_score": 0.8,
    }))

    async def fake_call(provider, api_key, model, messages):
        return '{"sentences":[{"text":"Answer.","citations":[0],"supported":true}],"score":0.5}'

    monkeypatch.setattr("backend.services.grounding._call", fake_call)

    result = await verify_groundedness(
        answer="Answer.",
        sources=[Citation(chunk_id="c1", document_id="d1", excerpt="Source.", score=0.9)],
        provider="openai",
        api_key="k",
        model="m",
    )
    assert result["enabled"] is True
    assert result["verified"] is False  # Below threshold
    assert result["score"] == 0.5


@pytest.mark.asyncio
async def test_verify_groundedness_llm_failure_fails_open(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={"groundedness_verifier_enabled": True}))

    async def fake_call(provider, api_key, model, messages):
        raise RuntimeError("LLM error")

    monkeypatch.setattr("backend.services.grounding._call", fake_call)

    result = await verify_groundedness(
        answer="Answer.",
        sources=[Citation(chunk_id="c1", document_id="d1", excerpt="Source.", score=0.9)],
        provider="openai",
        api_key="k",
        model="m",
    )
    # Fails open: enabled but no verification
    assert result["enabled"] is True
    assert result["verified"] is None
    assert result["score"] is None


@pytest.mark.asyncio
async def test_verify_groundedness_no_key_or_model(monkeypatch):
    from backend.settings import settings
    monkeypatch.setattr("backend.services.grounding.settings", settings.model_copy(update={"groundedness_verifier_enabled": True}))

    result = await verify_groundedness(
        answer="Answer.",
        sources=[Citation(chunk_id="c1", document_id="d1", excerpt="Source.", score=0.9)],
        provider="openai",
        api_key="",
        model="",
    )
    assert result["enabled"] is True
    assert result["verified"] is None
