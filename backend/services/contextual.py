"""Contextual retrieval (Anthropic 2024).

At ingest time, prepend each chunk's embedded text with a short
LLM-generated situating context. The stored `content` (and therefore
the citation excerpt returned to the user) stays untouched — we only
enrich the text that goes into the embedder, so the retrieval side
sees a richer representation while the display side stays faithful.

Implementation notes:

- Runs in the worker, behind `RETRIEVAL_CONTEXTUAL_ENABLED`.
- Batches chunks into a single LLM call per document for cost control
  by giving the model the whole document once (as a "cache-key"
  document) and asking for one situating sentence per chunk.
- On any provider failure we fall back to the original chunks with no
  context prefix. The caller always gets a usable chunk list.
- Output format is a JSON array of strings. If the model returns fewer
  items than we expect we pad with empty strings; if more, we truncate.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace

from backend.services.chunking import ChunkPayload
from backend.services.llm import create_openai_text, gemini_text
from backend.settings import settings

logger = logging.getLogger("ragapp.contextual")

# Hard cap: sending a 100-page document to the model for every ingest is
# wasteful. We truncate the "whole document" prompt; the situating step
# only needs high-level signal.
_MAX_DOC_CHARS = 12_000
_MAX_CONTEXT_CHARS = 400


def _build_prompt(full_document: str, chunk_texts: list[str]) -> list[dict[str, str]]:
    numbered_chunks = "\n\n".join(
        f"<chunk id=\"{i}\">\n{text}\n</chunk>"
        for i, text in enumerate(chunk_texts)
    )
    system = (
        "You improve retrieval quality by producing a ONE-sentence "
        "situating context for each chunk of a document. Each context "
        "should tell a retriever where this chunk sits in the bigger "
        "picture (section, topic, relative position) using keywords "
        "that would help match related questions. Do NOT paraphrase the "
        "chunk itself."
    )
    user = (
        "DOCUMENT (may be truncated):\n"
        f"<document>\n{full_document[:_MAX_DOC_CHARS]}\n</document>\n\n"
        "CHUNKS:\n"
        f"{numbered_chunks}\n\n"
        "Reply with ONLY a JSON array of strings — one situating "
        "sentence per chunk, in the same order as the chunks above. "
        f"Each sentence must be <= {_MAX_CONTEXT_CHARS} characters. "
        "No preamble, no trailing commentary, no markdown fences."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_contexts(raw: str, expected: int) -> list[str]:
    if not raw:
        return [""] * expected
    text = raw.strip()
    # Strip code fences the model might add despite instructions.
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -3]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return [""] * expected
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return [""] * expected
    if not isinstance(data, list):
        return [""] * expected
    out = [str(item).strip()[:_MAX_CONTEXT_CHARS] for item in data]
    if len(out) < expected:
        out.extend([""] * (expected - len(out)))
    return out[:expected]


async def _call_llm(provider: str, api_key: str, model: str, messages: list[dict[str, str]]) -> str:
    if provider == "openai":
        return await create_openai_text(api_key, model, messages)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, gemini_text, api_key, model, messages)


async def situate_chunks(
    *,
    chunks: list[ChunkPayload],
    full_document: str,
    provider: str,
    api_key: str,
    chat_model: str,
) -> tuple[list[ChunkPayload], dict[str, int]]:
    """Return a new chunks list where each chunk's `content` is prefixed
    with an LLM-generated situating sentence.

    Falls back to the input list unchanged on any failure. Returns a
    stats dict with `enriched` / `skipped` counts for observability.
    """
    stats: dict[str, int] = {"enriched": 0, "skipped": 0}
    if not settings.retrieval_contextual_enabled or not chunks:
        stats["skipped"] = len(chunks)
        return chunks, stats
    if not api_key or not chat_model:
        logger.info("contextual_skipped reason=missing_provider_key_or_model")
        stats["skipped"] = len(chunks)
        return chunks, stats

    # Single LLM call per document (batched) for cost efficiency.
    messages = _build_prompt(full_document, [c.content for c in chunks])
    try:
        raw = await _call_llm(provider, api_key, chat_model, messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("contextual_llm_failed err=%s", exc)
        stats["skipped"] = len(chunks)
        return chunks, stats

    contexts = _parse_contexts(raw, expected=len(chunks))
    enriched: list[ChunkPayload] = []
    for chunk, ctx in zip(chunks, contexts):
        if ctx:
            # Embed the situating context + chunk text together, but keep
            # `content` untouched so citations stay verbatim.
            enriched.append(
                replace(chunk, embedding_content=f"{ctx}\n\n{chunk.content}")
            )
            stats["enriched"] += 1
        else:
            enriched.append(chunk)
            stats["skipped"] += 1
    return enriched, stats
