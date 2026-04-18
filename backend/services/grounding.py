"""Groundedness verifier.

After the primary answer is produced, we optionally run a second-pass
LLM call that returns, for each answer sentence, the list of citation
indices that support it plus an overall confidence score.

The verifier is deliberately lightweight:

- It runs only when `GROUNDEDNESS_VERIFIER_ENABLED=true`.
- It consumes the same provider and chat model as the answer so users
  don't need a separate key.
- On any error (bad JSON, provider timeout, missing key) it fails open:
  `verified=False, score=None`. The answer is still returned to the
  user — we just don't decorate it with a groundedness badge.

Return shape:

    {
        "enabled": bool,
        "verified": bool | None,
        "score": float | None,
        "sentences": [
            {"text": str, "citations": [int, ...], "supported": bool},
            ...
        ],
    }

Sentence indices into `sources` are 0-based.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from backend.models import Citation
from backend.services.llm import create_openai_text, gemini_text
from backend.settings import settings

logger = logging.getLogger("ragapp.grounding")

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")


def _split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def _build_prompt(answer: str, sources: list[Citation]) -> list[dict[str, str]]:
    source_block = "\n\n".join(
        f"[{idx}] {src.excerpt}" for idx, src in enumerate(sources)
    )
    system = (
        "You are a strict grounding checker. For each sentence in the "
        "ANSWER, decide which SOURCE passages (if any) directly support "
        "it. Reply with ONLY a compact JSON object matching this schema:\n"
        '{"sentences":[{"text":"...","citations":[0,2],"supported":true}],'
        '"score":0.0}\n'
        "`score` is your overall confidence in [0,1] that the answer is "
        "grounded in the provided sources. Do not include any other text."
    )
    user = (
        f"SOURCES:\n{source_block}\n\nANSWER:\n{answer.strip()}\n\n"
        "Return JSON only."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_response(raw: str, answer: str) -> dict[str, Any] | None:
    if not raw:
        return None
    # Strip optional code fences the model might add.
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    # Find the first '{' and the last '}' to survive minor preamble/suffix.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    sentences_raw = data.get("sentences") or []
    if not isinstance(sentences_raw, list):
        return None
    sentences: list[dict[str, Any]] = []
    for item in sentences_raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        citations = item.get("citations") or []
        if not isinstance(citations, list):
            citations = []
        citations_clean = [int(c) for c in citations if isinstance(c, (int, float))]
        supported = bool(item.get("supported", bool(citations_clean)))
        sentences.append(
            {"text": text, "citations": citations_clean, "supported": supported}
        )
    score = data.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    if not sentences:
        # Fall back to lexical mapping: every answer sentence → no cites.
        sentences = [
            {"text": s, "citations": [], "supported": False}
            for s in _split_sentences(answer)
        ]
    return {"sentences": sentences, "score": score_f}


async def _call(provider: str, api_key: str, model: str, messages: list[dict[str, str]]) -> str:
    if provider == "openai":
        return await create_openai_text(api_key, model, messages)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, gemini_text, api_key, model, messages)


async def verify_groundedness(
    *,
    answer: str,
    sources: list[Citation],
    provider: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    if not settings.groundedness_verifier_enabled:
        return {"enabled": False, "verified": None, "score": None, "sentences": []}
    if not answer.strip() or not sources:
        return {"enabled": True, "verified": None, "score": None, "sentences": []}
    if not api_key or not model:
        return {"enabled": True, "verified": None, "score": None, "sentences": []}

    messages = _build_prompt(answer, sources)
    try:
        raw = await _call(provider, api_key, model.strip(), messages)
    except Exception as exc:  # noqa: BLE001
        logger.warning("groundedness_llm_failed err=%s", exc)
        return {"enabled": True, "verified": None, "score": None, "sentences": []}

    parsed = _parse_response(raw, answer)
    if parsed is None:
        logger.debug("groundedness_parse_failed raw=%s", raw[:200])
        return {"enabled": True, "verified": None, "score": None, "sentences": []}

    score = parsed.get("score")
    threshold = settings.groundedness_min_score
    verified = False
    if score is not None:
        verified = score >= threshold
    else:
        # Fall back to sentence-level support ratio.
        sents = parsed["sentences"]
        if sents:
            supported = sum(1 for s in sents if s["supported"])
            score = supported / len(sents)
            verified = score >= threshold
    return {
        "enabled": True,
        "verified": verified,
        "score": score,
        "sentences": parsed["sentences"],
    }
