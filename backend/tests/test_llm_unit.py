"""Unit tests for prompt building and provider helpers in backend.services.llm."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from backend.services import llm
from backend.services.vectorstore import RetrievedChunk


def _chunk(cid, text, *, page=None, chunk_type="text", meta=None):
    return RetrievedChunk(chunk_id=cid, document_id="d", excerpt=text, score=0.5,
                          page_number=page, chunk_type=chunk_type, metadata_json=meta)


# --- prompt building ---------------------------------------------------------

def test_system_prompt_for_modes():
    assert llm.system_prompt_for_mode(None) == llm.SYSTEM_PROMPT
    assert llm.system_prompt_for_mode("ASK") == llm.SYSTEM_PROMPT
    assert "Mode: COMPARE" in llm.system_prompt_for_mode("Compare")
    assert llm.system_prompt_for_mode("unknown-mode") == llm.SYSTEM_PROMPT


def test_build_rag_prompt_numbers_pages_and_history_and_mode():
    msgs = llm.build_rag_prompt(
        [_chunk("1", "alpha", page=3), _chunk("2", "beta")],
        "What is alpha?",
        history=[{"role": "user", "content": "hi"}, {"role": "system", "content": "ignored"},
                 {"role": "assistant", "content": "hello"}],
        mode="brief",
    )
    assert msgs[0]["role"] == "system" and "Mode: BRIEF" in msgs[0]["content"]
    assert msgs[1]["content"].startswith("Document excerpts:")
    assert "[1] (page 3)\nalpha" in msgs[1]["content"] and "[2]\nbeta" in msgs[1]["content"]
    assert "Saved knowledge" not in msgs[1]["content"]
    # system-role history is dropped; question is last
    assert [m["role"] for m in msgs[2:]] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "What is alpha?"


def test_build_rag_prompt_separates_artifacts_with_shared_numbering():
    msgs = llm.build_rag_prompt(
        [_chunk("1", "source text"),
         _chunk("2", "my note", chunk_type="artifact", meta='{"title": "Q3 plan"}'),
         _chunk("3", "bad meta", chunk_type="artifact", meta="{not json")],
        "q",
    )
    user = msgs[1]["content"]
    assert "[1]\nsource text" in user
    assert "Saved knowledge (augmenting context, not primary sources)" in user
    assert "[2] (saved Q3 plan)\nmy note" in user
    assert "[3] (saved note)\nbad meta" in user  # malformed metadata falls back
    assert "augmenting context" in msgs[0]["content"]


# --- OpenAI (mocked client) --------------------------------------------------

class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def _fake_openai(result):
    calls = {}

    class Completions:
        async def create(self, **kwargs):
            calls.update(kwargs)
            return result

    class Client:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.chat = NS(completions=Completions())

    return Client, calls


def test_create_openai_text_returns_content_and_handles_empty():
    Client, calls = _fake_openai(NS(choices=[NS(message=NS(content="answer"))]))
    with patch.object(llm, "AsyncOpenAI", Client):
        assert asyncio.run(llm.create_openai_text("k", "gpt", [{"role": "user", "content": "q"}])) == "answer"
    assert calls["stream"] is False and calls["model"] == "gpt" and calls["client_kwargs"]["api_key"] == "k"
    for empty in (NS(choices=[]), NS(choices=[NS(message=NS(content=None))])):
        Client, _ = _fake_openai(empty)
        with patch.object(llm, "AsyncOpenAI", Client):
            assert asyncio.run(llm.create_openai_text("k", "gpt", [])) == ""


def test_stream_openai_text_yields_content_and_refusals_only():
    chunks = [
        NS(choices=[]),
        NS(choices=[NS(delta=None)]),
        NS(choices=[NS(delta=NS(content="Hel", refusal=None))]),
        NS(choices=[NS(delta=NS(content="", refusal=None))]),
        NS(choices=[NS(delta=NS(content="lo", refusal=None))]),
        NS(choices=[NS(delta=NS(content=None, refusal="I can't help"))]),
    ]
    Client, calls = _fake_openai(_FakeStream(chunks))

    async def collect():
        return [p async for p in llm.stream_openai_text("k", "gpt", [])]

    with patch.object(llm, "AsyncOpenAI", Client):
        assert asyncio.run(collect()) == ["Hel", "lo", "I can't help"]
    assert calls["stream"] is True


# --- Gemini (fake google.generativeai) ---------------------------------------

def _fake_genai(response):
    rec = {"chat_history": None, "sent": None, "generated": None}

    class Chat:
        def send_message(self, prompt, stream):
            rec["sent"] = (prompt, stream)
            return response

    class GenerativeModel:
        def __init__(self, model_name, system_instruction=None):
            rec["model"] = model_name
            rec["system"] = system_instruction

        def start_chat(self, history):
            rec["chat_history"] = history
            return Chat()

        def generate_content(self, prompt, stream):
            rec["generated"] = (prompt, stream)
            return response

    mod = types.ModuleType("google.generativeai")
    mod.configure = lambda api_key: rec.__setitem__("api_key", api_key)
    mod.GenerativeModel = GenerativeModel
    google = types.ModuleType("google")
    google.generativeai = mod
    return {"google": google, "google.generativeai": mod}, rec


def _part_chunk(*texts):
    return NS(candidates=[NS(content=NS(parts=[NS(text=t) for t in texts]))])


class _TextRaises:
    candidates = []

    @property
    def text(self):
        raise ValueError("not ready")


def test_stream_gemini_merges_history_and_uses_chat_when_history_exists():
    response = [_part_chunk("a", "b"), _TextRaises(), NS(candidates=[], text="c"), NS(candidates=[NS(content=None)])]
    mods, rec = _fake_genai(response)
    messages = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "u1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "final question"},
    ]
    with patch.dict(sys.modules, mods):
        out = list(llm.stream_gemini_text("key", "gemini-x", messages))
    assert out == ["ab", "c"]
    assert rec["system"] == "SYS" and rec["api_key"] == "key"
    assert rec["chat_history"] == [{"role": "user", "parts": ["u1\n\nu2"]}, {"role": "model", "parts": ["a1"]}]
    assert rec["sent"] == ("final question", True)


def test_stream_gemini_single_turn_uses_generate_content():
    mods, rec = _fake_genai([_part_chunk("x")])
    with patch.dict(sys.modules, mods):
        assert list(llm.stream_gemini_text("k", "m", [{"role": "user", "content": "only"}])) == ["x"]
    assert rec["generated"] == ("only", True) and rec["chat_history"] is None


def test_gemini_text_success_blocked_and_missing_text():
    mods, rec = _fake_genai(NS(text="full answer"))
    with patch.dict(sys.modules, mods):
        assert llm.gemini_text("k", "m", [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]) == "full answer"
    assert rec["generated"] == ("q", False)

    mods, _ = _fake_genai(_TextRaises())
    with patch.dict(sys.modules, mods), pytest.raises(ValueError, match="blocked or empty"):
        llm.gemini_text("k", "m", [{"role": "user", "content": "q"}])

    mods, _ = _fake_genai(NS())  # no .text attribute at all
    with patch.dict(sys.modules, mods):
        assert llm.gemini_text("k", "m", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                          {"role": "user", "content": "c"}]) == ""
