"""Tests for query transformation module."""

from __future__ import annotations

import pytest

from backend.services.query_transform import (
    _parse_list,
    multi_query,
    hyde,
    step_back,
    transform,
    TransformedQuery,
)


def test_parse_list_json_array():
    raw = '["What is RAG?", "Explain retrieval augmented generation."]'
    assert _parse_list(raw, 3) == ["What is RAG?", "Explain retrieval augmented generation."]


def test_parse_list_numbered_lines():
    raw = "1. What is RAG?\n2. Explain retrieval augmented generation.\n3. Third item."
    assert _parse_list(raw, 3) == ["What is RAG?", "Explain retrieval augmented generation.", "Third item."]


def test_parse_list_bullets():
    raw = "- What is RAG?\n- Explain retrieval.\n- Final point"
    assert _parse_list(raw, 3) == ["What is RAG?", "Explain retrieval.", "Final point"]


def test_parse_list_dedupe():
    raw = "1. What is RAG?\n2. What is RAG?\n3. Explain retrieval."
    assert _parse_list(raw, 3) == ["What is RAG?", "Explain retrieval."]


@pytest.mark.asyncio
async def test_multi_query_returns_items(monkeypatch):
    called = {}

    async def fake_call(provider, api_key, model, prompt):
        called["provider"] = provider
        called["question"] = prompt
        return '["What is RAG?", "Explain retrieval."]'

    monkeypatch.setattr("backend.services.query_transform._call_llm", fake_call)
    result = await multi_query(
        "What is RAG?", provider="openai", api_key="k", model="m", count=2
    )
    assert len(result) == 2
    assert all(isinstance(tq, TransformedQuery) for tq in result)
    assert called["provider"] == "openai"


@pytest.mark.asyncio
async def test_hyde_returns_single_item(monkeypatch):
    async def fake_call(provider, api_key, model, prompt):
        return "RAG is a technique that enhances LLMs with external knowledge."

    monkeypatch.setattr("backend.services.query_transform._call_llm", fake_call)
    result = await hyde("What is RAG?", provider="openai", api_key="k", model="m")
    assert len(result) == 1
    assert result[0].kind == "hyde"
    assert "technique" in result[0].text.lower()


@pytest.mark.asyncio
async def test_step_back_returns_generalized_question(monkeypatch):
    async def fake_call(provider, api_key, model, prompt):
        return "What are common cloud security best practices?"

    monkeypatch.setattr("backend.services.query_transform._call_llm", fake_call)
    result = await step_back(
        "How do I secure my AWS S3 buckets?", provider="openai", api_key="k", model="m"
    )
    assert len(result) == 1
    assert result[0].kind == "step_back"


@pytest.mark.asyncio
async def test_transform_runs_enabled_kinds(monkeypatch, tmp_path):

    calls = []

    async def fake_call(provider, api_key, model, prompt):
        content = prompt
        calls.append(content[:40])
        if "Generate" in content:
            return '["Alt 1", "Alt 2"]'
        if "ideal answer" in content:
            return "Ideal answer text."
        if "general" in content.lower():
            return "General question."
        return ""

    monkeypatch.setattr("backend.services.query_transform._call_llm", fake_call)

    from backend.settings import settings as original_settings
    mocked_settings = original_settings.model_copy(update={
        "retrieval_query_transforms_enabled": True,
        "retrieval_query_transforms": "multi_query,hyde,step_back",
        "retrieval_multi_query_count": 2,
    })
    monkeypatch.setattr("backend.services.query_transform.settings", mocked_settings)

    result = await transform(
        "What is RAG?", provider="openai", api_key="k", model="m"
    )
    assert len(result) == 4
    kinds = {tq.kind for tq in result}
    assert kinds == {"multi_query", "hyde", "step_back"}


@pytest.mark.asyncio
async def test_transform_empty_when_disabled(monkeypatch):
    from backend.settings import settings as original_settings
    mocked_settings = original_settings.model_copy(update={"retrieval_query_transforms_enabled": False})
    monkeypatch.setattr("backend.services.query_transform.settings", mocked_settings)

    result = await transform("What is RAG?", provider="openai", api_key="k", model="m")
    assert result == []
