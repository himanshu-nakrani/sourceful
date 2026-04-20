"""Rolling conversation memory (Phase 3.7).

Classic RAG chat apps truncate the last N turns and feed them verbatim
into every prompt. That's cheap but loses anything older than the cut —
facts, constraints, user preferences — right when the conversation gets
long enough to benefit from them.

This module replaces naive truncation with a two-layer memory:

    [system: running summary of older turns]
    [recent: last ``MEMORY_RECENT_TURNS`` turns verbatim]

The summary is persisted in ``conversation_memory`` and refreshed
lazily: when the conversation grows past the recent-turns window we
send the older slice through the user's primary chat model with a
compact "update this summary" prompt.

The feature is **fail-open** on every axis:

- If ``MEMORY_ENABLED`` is off we return the plain last-N history.
- If the summarizer LLM call fails we fall back to last-N for this turn
  and leave the stored summary untouched.
- If the DB row can't be read we still return history.

This mirrors how ``grounding.py`` and ``query_transform.py`` degrade —
a Phase-3 feature must never block the primary answer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Iterable

from backend.database import execute, fetch_one
from backend.services.llm import create_openai_text, gemini_text
from backend.settings import settings

logger = logging.getLogger("ragapp.memory")

_SYSTEM_ROLE = "system"


@dataclass(slots=True)
class MemoryContext:
    """What the chat router needs to inject memory into a prompt.

    ``summary`` is prepended as a system message; ``recent`` replaces the
    naive last-N slice. ``stages`` is a small dict suitable for merging
    into the retrieval stages payload the UI already renders.
    """

    summary: str | None
    recent: list[dict[str, str]]
    stages: dict[str, int | bool | str]


def _slice_last_n(history: list[dict[str, str]], n: int) -> list[dict[str, str]]:
    if n <= 0:
        return []
    return history[-n:]


def _pair_turns(history: Iterable[dict[str, str]]) -> int:
    """Count user-assistant turn pairs (best-effort)."""
    return sum(1 for m in history if m.get("role") == "user")


async def _call_llm(provider: str, api_key: str, model: str, messages: list[dict[str, str]]) -> str:
    if provider == "openai":
        return await create_openai_text(api_key, model, messages)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, gemini_text, api_key, model, messages)


def _summarize_prompt(
    prior_summary: str | None,
    older_slice: list[dict[str, str]],
    *,
    target_chars: int,
) -> list[dict[str, str]]:
    """Build the LLM messages that refresh a rolling conversation summary.

    We bias the prompt toward facts and commitments over chit-chat; the
    memory is consumed as context for retrieval-grounded answers, not
    reproduced verbatim back to the user.
    """
    transcript_lines: list[str] = []
    for msg in older_slice:
        role = msg.get("role", "?")
        content = (msg.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        if len(content) > 500:
            content = content[:500] + "…"
        transcript_lines.append(f"{role.upper()}: {content}")
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no older turns yet)"

    sys = (
        "You maintain a concise running summary of a document-grounded chat. "
        "Keep it under "
        f"{target_chars} characters. Prioritize: "
        "(1) concrete facts established, (2) user preferences/constraints, "
        "(3) open questions, (4) entities or document sections already "
        "discussed. Drop small talk. Write in third person, plain prose, "
        "no bullets or preamble."
    )
    user_parts: list[str] = []
    if prior_summary:
        user_parts.append("PRIOR SUMMARY:\n" + prior_summary.strip())
    user_parts.append("OLDER TURNS TO INCORPORATE:\n" + transcript)
    user_parts.append("Return only the updated summary.")
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


async def load_summary(conversation_id: str, owner_id: str) -> tuple[str | None, int]:
    """Return ``(summary, turn_count_at_last_update)`` or ``(None, 0)``.

    Isolated so tests can patch this without touching the DB layer.
    """
    row = await fetch_one(
        "SELECT summary, turn_count FROM conversation_memory WHERE conversation_id = ? AND owner_id = ?",
        (conversation_id, owner_id),
    )
    if not row:
        return None, 0
    summary = (row.get("summary") or "").strip()
    return (summary or None), int(row.get("turn_count") or 0)


async def _upsert_summary(
    *, conversation_id: str, owner_id: str, summary: str, turn_count: int
) -> None:
    """Upsert the rolling summary for a conversation (Postgres + SQLite compatible)."""
    ts_fn = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"
    if settings.using_postgres:
        await execute(
            f"""
            INSERT INTO conversation_memory (conversation_id, owner_id, summary, turn_count, updated_at)
            VALUES (?, ?, ?, ?, {ts_fn})
            ON CONFLICT (conversation_id) DO UPDATE
                SET summary = EXCLUDED.summary,
                    turn_count = EXCLUDED.turn_count,
                    updated_at = {ts_fn}
            """,
            (conversation_id, owner_id, summary, turn_count),
        )
        return
    await execute(
        f"""
        INSERT INTO conversation_memory (conversation_id, owner_id, summary, turn_count, updated_at)
        VALUES (?, ?, ?, ?, {ts_fn})
        ON CONFLICT(conversation_id) DO UPDATE
            SET summary = excluded.summary,
                turn_count = excluded.turn_count,
                updated_at = {ts_fn}
        """,
        (conversation_id, owner_id, summary, turn_count),
    )


async def build_context(
    *,
    conversation_id: str,
    owner_id: str,
    history: list[dict[str, str]],
    provider: str,
    api_key: str,
    model: str,
) -> MemoryContext:
    """Return prompt-ready memory context, refreshing the summary if needed.

    When the feature is disabled or the history is short enough to fit in
    the recent-turns window, we short-circuit without any LLM call.
    """
    recent_n = max(0, settings.memory_recent_turns)
    stages: dict[str, int | bool | str] = {
        "memory_enabled": settings.memory_enabled,
        "memory_recent_turns": recent_n,
    }

    if not settings.memory_enabled:
        return MemoryContext(summary=None, recent=_slice_last_n(history, settings.max_conversation_history), stages=stages)

    if len(history) <= recent_n:
        # Nothing to summarize yet; just surface the stored summary if any.
        try:
            summary, _ = await load_summary(conversation_id, owner_id)
        except Exception:  # noqa: BLE001
            logger.exception("memory_load_failed conversation_id=%s", conversation_id)
            summary = None
        stages["memory_state"] = "cold" if summary is None else "warm"
        return MemoryContext(summary=summary, recent=history, stages=stages)

    older = history[:-recent_n]
    recent = history[-recent_n:]

    try:
        prior_summary, prior_turn_count = await load_summary(conversation_id, owner_id)
    except Exception:  # noqa: BLE001
        logger.exception("memory_load_failed conversation_id=%s", conversation_id)
        prior_summary, prior_turn_count = None, 0

    current_turns = _pair_turns(history)
    stages["memory_turn_count"] = current_turns
    stages["memory_prior_turn_count"] = prior_turn_count

    # Only re-summarize when we have strictly more paired turns than were
    # captured by the prior summary. Prevents hammering the LLM when the
    # user re-opens a conversation without adding messages.
    if current_turns <= prior_turn_count and prior_summary:
        stages["memory_state"] = "reused"
        return MemoryContext(summary=prior_summary, recent=recent, stages=stages)

    if not api_key or not model:
        stages["memory_state"] = "skipped_no_key"
        return MemoryContext(summary=prior_summary, recent=recent, stages=stages)

    prompt = _summarize_prompt(
        prior_summary=prior_summary,
        older_slice=older,
        target_chars=settings.memory_summary_max_chars,
    )
    try:
        raw = await _call_llm(provider, api_key, model.strip(), prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_summarize_failed err=%s", exc)
        stages["memory_state"] = "llm_failed"
        return MemoryContext(summary=prior_summary, recent=recent, stages=stages)

    new_summary = (raw or "").strip()
    if not new_summary:
        stages["memory_state"] = "llm_empty"
        return MemoryContext(summary=prior_summary, recent=recent, stages=stages)

    if len(new_summary) > settings.memory_summary_max_chars:
        new_summary = new_summary[: settings.memory_summary_max_chars].rstrip() + "…"

    try:
        await _upsert_summary(
            conversation_id=conversation_id,
            owner_id=owner_id,
            summary=new_summary,
            turn_count=current_turns,
        )
    except Exception:  # noqa: BLE001
        logger.exception("memory_upsert_failed conversation_id=%s", conversation_id)
        # Still honor the new summary for this turn even if we can't persist.
    stages["memory_state"] = "refreshed"
    return MemoryContext(summary=new_summary, recent=recent, stages=stages)


def inject_summary_into_messages(
    messages: list[dict[str, str]],
    summary: str | None,
) -> list[dict[str, str]]:
    """Prepend a rolling memory system message to a RAG prompt.

    The retrieval-pipeline prompt already starts with a system prompt,
    followed by a user message containing the document excerpts. We
    insert the memory *after* the primary system prompt so both apply;
    the model sees system(role) → system(memory) → user(context) → …
    """
    if not summary:
        return messages
    memory_msg = {
        "role": _SYSTEM_ROLE,
        "content": f"Conversation memory so far: {summary}",
    }
    # Insert after the first system message if present, otherwise at the front.
    for idx, msg in enumerate(messages):
        if msg.get("role") == _SYSTEM_ROLE:
            return messages[: idx + 1] + [memory_msg] + messages[idx + 1 :]
    return [memory_msg] + messages


def new_memory_id() -> str:
    return str(uuid.uuid4())
