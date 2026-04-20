"""Tests for context compression module."""

from __future__ import annotations

import pytest

from backend.services.compression import (
    compress_chunks,
    _approx_tokens,
    _split_sentences,
    _heuristic_compress_chunk,
)
from backend.services.vectorstore import RetrievedChunk


def test_approx_tokens_basic():
    # Roughly 4 chars per token
    assert _approx_tokens("") == 0
    assert _approx_tokens("a") == 1
    assert _approx_tokens("a" * 400) == 100


def test_split_sentences():
    text = "First sentence. Second one! Third? Last."
    sents = _split_sentences(text)
    assert len(sents) == 4
    assert sents[0] == "First sentence."


def test_heuristic_compress_noop_when_small():
    text = "Short."
    assert _heuristic_compress_chunk(text, "question", 100) == text


def test_heuristic_compress_truncates_long():
    text = "This is a sentence. " * 50  # ~500 chars
    compressed = _heuristic_compress_chunk(text, "question", 10)
    # Should be shorter and end with ellipsis or contain fewer sentences
    assert len(compressed) < len(text)


def test_heuristic_compress_keeps_question_relevant():
    # The algorithm prefers sentences with word overlap to the question
    question = "deployment terraform module"
    text = (
        "The staging environment runs on Kubernetes. "
        "The Terraform module is in infra/staging. "
        "Backups run nightly at 02:00 UTC."
    )
    compressed = _heuristic_compress_chunk(text, question, 20)
    # Should prefer the middle sentence
    assert "Terraform" in compressed or "infra" in compressed


def test_compress_chunks_none_mode_returns_original():
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            excerpt="This is a test excerpt for compression.",
            score=0.9,
        ),
        RetrievedChunk(
            chunk_id="c2",
            document_id="d1",
            excerpt="Another excerpt here.",
            score=0.8,
        ),
    ]
    result, stats = compress_chunks(chunks, question="test", mode="none", target_tokens=100)
    assert len(result) == 2
    assert stats["mode"] == "none"
    assert stats["before_tokens"] == 0  # none mode returns 0 for tokens


def test_compress_chunks_heuristic_reduces_size():
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            excerpt="Sentence one. Sentence two. Sentence three. Sentence four. Sentence five.",
            score=0.9,
        ),
    ]
    result, stats = compress_chunks(chunks, question="two", mode="heuristic", target_tokens=4)
    assert len(result) == 1
    assert stats["mode"] == "heuristic"
    assert stats["after_tokens"] <= stats["before_tokens"]
    # Should have fewer sentences
    assert len(_split_sentences(result[0].excerpt)) <= len(_split_sentences(chunks[0].excerpt))


def test_compress_chunks_llmlingua_fallback_on_missing_dep():
    # When llmlingua is not installed, should fall back to heuristic
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            excerpt="Some text to compress.",
            score=0.9,
        ),
    ]
    result, stats = compress_chunks(chunks, question="test", mode="llmlingua", target_tokens=10)
    # Falls back to heuristic
    assert stats["mode"] == "heuristic"
    assert len(result) == 1


def test_compress_chunks_empty_input():
    result, stats = compress_chunks([], question="test", mode="heuristic", target_tokens=100)
    assert result == []
    assert stats["mode"] == "none"
