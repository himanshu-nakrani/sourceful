"""Gemini/dispatch paths of backend.services.embeddings not covered elsewhere."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from backend.services import embeddings
from backend.services.embedding_spec import EMBEDDING_DIMENSIONS, UnsupportedEmbeddingModelError


def _genai(result):
    mod = types.ModuleType("google.generativeai")
    mod.configure = lambda api_key: None
    mod.embed_content = lambda **kwargs: result(kwargs) if callable(result) else result
    google = types.ModuleType("google")
    google.generativeai = mod
    return {"google": google, "google.generativeai": mod}


def test_gemini_document_embedding_missing_raises():
    with patch.dict(sys.modules, _genai({"embedding": None})), pytest.raises(ValueError, match="no embedding for a chunk"):
        embeddings.embed_texts_gemini_sync("k", "gemini-embedding-001", ["t"])


def test_gemini_query_embedding_missing_raises_and_attr_style_result_works():
    with patch.dict(sys.modules, _genai(NS(embedding=None))), pytest.raises(ValueError, match="for the question"):
        embeddings.embed_query_gemini_sync("k", "gemini-embedding-001", "q")
    seen = {}

    def result(kwargs):
        seen.update(kwargs)
        return NS(embedding=[2.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1))

    with patch.dict(sys.modules, _genai(result)):
        vec = embeddings.embed_query_gemini_sync("k", "gemini-embedding-001", "q")
    assert vec[0] == pytest.approx(1.0) and len(vec) == EMBEDDING_DIMENSIONS
    assert seen["task_type"] == "retrieval_query" and seen["output_dimensionality"] == EMBEDDING_DIMENSIONS


@pytest.mark.parametrize("fn,arg", [(embeddings.embed_texts, ["t"]), (embeddings.embed_query, "t")])
def test_unknown_provider_is_rejected(fn, arg):
    with pytest.raises(UnsupportedEmbeddingModelError):
        asyncio.run(fn("vertex_search", "k", "managed", arg))
