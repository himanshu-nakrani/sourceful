"""Context compression before prompt-build.

Two modes are supported:

- **heuristic** — cheap, no external deps. Ranks sentences within each
  chunk by lexical overlap with the question; drops the lowest-ranked
  sentences first until the total token budget is met. Preserves the
  excerpt structure so citations still point at the right chunk.

- **llmlingua** — uses the optional `llmlingua` package. If the import
  fails at runtime we fall back to `heuristic` automatically so no
  deployment breaks when the extra isn't installed.

The output is a new list of `RetrievedChunk` objects (originals are not
mutated) with shortened `excerpt` fields. `compress_chunks` returns
`(chunks, stats_dict)` so the caller can surface the savings in traces.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import replace
from typing import Iterable

from backend.services.vectorstore import RetrievedChunk

logger = logging.getLogger("ragapp.compression")

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n+")

# Conservative chars-per-token estimate covering English + code-y docs.
_CHARS_PER_TOKEN = 4.0


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def _words(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def _split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    # Split on sentence terminators followed by whitespace+capital, or on
    # newlines. Fall back to the whole text if nothing matches.
    parts = _SENTENCE_RE.split(text)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts or [text]


def _score_sentence(sentence_words: set[str], q_words: set[str]) -> float:
    if not sentence_words or not q_words:
        return 0.0
    overlap = len(sentence_words & q_words)
    if overlap == 0:
        return 0.0
    # Normalize by sentence size to avoid always preferring long sentences.
    return overlap / math.sqrt(len(sentence_words))


def _heuristic_compress_chunk(excerpt: str, question: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if _approx_tokens(excerpt) <= max_tokens:
        return excerpt

    sentences = _split_sentences(excerpt)
    if len(sentences) <= 1:
        # Single-sentence chunk: truncate by characters, respecting tokens.
        budget_chars = int(max_tokens * _CHARS_PER_TOKEN)
        return excerpt[:budget_chars].rstrip() + "…"

    q_words = set(_words(question))
    scored = [
        (idx, sentence, _score_sentence(set(_words(sentence)), q_words))
        for idx, sentence in enumerate(sentences)
    ]
    # Sort by score desc, with original order as the tiebreaker so that
    # equally-scored sentences keep their document flow.
    scored.sort(key=lambda item: (-item[2], item[0]))

    picked: list[tuple[int, str]] = []
    used_tokens = 0
    for idx, sentence, _score in scored:
        cost = _approx_tokens(sentence)
        if used_tokens + cost > max_tokens and picked:
            break
        picked.append((idx, sentence))
        used_tokens += cost
    picked.sort(key=lambda item: item[0])
    return " ".join(sentence for _idx, sentence in picked)


def _llmlingua_compress(
    chunks: list[RetrievedChunk], question: str, target_tokens: int
) -> list[RetrievedChunk] | None:
    """Compress via LLMLingua. Returns None if the dep is unavailable."""
    try:
        from llmlingua import PromptCompressor  # type: ignore
    except ImportError:
        return None
    try:
        compressor = PromptCompressor()
        out: list[RetrievedChunk] = []
        per_chunk_budget = max(32, target_tokens // max(1, len(chunks)))
        for chunk in chunks:
            result = compressor.compress_prompt(
                [chunk.excerpt],
                instruction="",
                question=question,
                target_token=per_chunk_budget,
            )
            compressed_text = (result or {}).get("compressed_prompt") or chunk.excerpt
            out.append(replace(chunk, excerpt=compressed_text))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("llmlingua_failed_falling_back err=%s", exc)
        return None


def compress_chunks(
    chunks: Iterable[RetrievedChunk],
    *,
    question: str,
    mode: str,
    target_tokens: int,
) -> tuple[list[RetrievedChunk], dict[str, int | str]]:
    chunks_list = list(chunks)
    if not chunks_list or mode == "none":
        return chunks_list, {"mode": "none", "before_tokens": 0, "after_tokens": 0}

    before_tokens = sum(_approx_tokens(c.excerpt) for c in chunks_list)

    effective_mode = mode
    if mode == "llmlingua":
        lm_out = _llmlingua_compress(chunks_list, question, target_tokens)
        if lm_out is not None:
            after_tokens = sum(_approx_tokens(c.excerpt) for c in lm_out)
            return lm_out, {
                "mode": "llmlingua",
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
            }
        effective_mode = "heuristic"  # fall back

    # Heuristic mode: distribute the token budget proportionally to the
    # original excerpt size so bigger chunks keep more detail.
    if before_tokens == 0:
        return chunks_list, {
            "mode": effective_mode,
            "before_tokens": 0,
            "after_tokens": 0,
        }
    out: list[RetrievedChunk] = []
    for chunk in chunks_list:
        chunk_tokens = _approx_tokens(chunk.excerpt)
        share = max(1, int(round(target_tokens * chunk_tokens / before_tokens)))
        compressed_text = _heuristic_compress_chunk(chunk.excerpt, question, share)
        out.append(replace(chunk, excerpt=compressed_text))
    after_tokens = sum(_approx_tokens(c.excerpt) for c in out)
    return out, {
        "mode": effective_mode,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
    }
