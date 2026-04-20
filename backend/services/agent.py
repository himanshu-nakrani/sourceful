"""Agentic retrieval loop (Phase 3.1 + 3.6).

A planner LLM sees the user's question, the active document set, and
the tool registry from :mod:`backend.services.agent_tools`. On each
iteration it replies with a JSON envelope that chooses one of:

    {"action": "call_tool", "tool": "search_chunks", "args": {...}, "thought": "..."}
    {"action": "answer",    "thought": "..."}
    {"action": "abstain",   "reason": "..."}

We keep the envelope dead simple — a plain ``json.loads`` on the reply
rather than a provider-specific tool-calling API — so both OpenAI and
Gemini users share one code path. The tradeoff is that models
occasionally wrap the JSON in prose; we strip prose aggressively and
fall back to a terminal ``answer`` action if parsing fails N times in a
row.

Why a dedicated loop instead of native tool calling?

    - Provider-agnostic (OpenAI & Gemini today; future Anthropic etc.
      just need a completion endpoint).
    - Observable: every planner reply + tool result shows up in the
      Langfuse trace and the ``stages`` payload the UI already renders
      for Phase-0 retrieval debugging.
    - Cheap: one LLM call per iteration, hard-capped at
      ``RETRIEVAL_AGENT_MAX_ITERATIONS`` (default 4).

Failure modes are fail-soft:

    - planner LLM down           → answer from whatever chunks we have
    - malformed planner JSON     → retry once, then answer
    - tool argument error        → planner sees the error and re-plans
    - iteration cap reached      → partial answer with a stages note
    - no chunks collected at all → fall back to a single `search_chunks`
      call using the raw question before giving up

Cross-document synthesis (3.6) falls out naturally: the planner is told
to prefer ``compare_documents`` when more than one document is in scope,
and every retrieved chunk keeps its ``document_id`` so the downstream
prompt builder can render per-document citations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.services import tracing
from backend.services.agent_tools import (
    AgentToolContext,
    ToolArgumentError,
    execute_tool,
    tool_name_list,
    TOOL_DEFINITIONS,
)
from backend.services.llm import create_openai_text, gemini_text
from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings

logger = logging.getLogger("ragapp.agent")


@dataclass(slots=True)
class AgentRunResult:
    """Outcome of :func:`run_agent`: chunks for the answer + observability."""

    chunks: list[RetrievedChunk]
    iterations: int
    stopped_reason: str
    stages: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    per_document_confidence: dict[str, float] = field(default_factory=dict)


_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a planner reply.

    Models love to wrap JSON in prose or fences ("Here's my plan:```json
    {...} ```"). We strip fences, then look for a balanced ``{...}``
    substring and attempt to parse it. Return ``None`` on any failure;
    the caller decides whether to retry or end the loop.
    """
    if not raw:
        return None
    stripped = _JSON_FENCE_RE.sub("", raw.strip())
    # First balanced object scan — tolerant of prose suffix/prefix.
    start = stripped.find("{")
    if start == -1:
        return None
    depth = 0
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = stripped[start : idx + 1]
                try:
                    data = json.loads(blob)
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None


def _planner_system_prompt(document_ids: list[str]) -> str:
    tools_doc = []
    for name in tool_name_list():
        td = TOOL_DEFINITIONS[name]
        required = td.parameters.get("required", [])
        tools_doc.append(
            f"- {td.name}(required={required}): {td.description}"
        )
    tools_block = "\n".join(tools_doc)
    doc_block = ", ".join(document_ids) if document_ids else "(none)"
    multi_doc_hint = (
        "Prefer `compare_documents` when more than one document is in "
        "scope and the question asks for a contrast, comparison, or "
        "synthesis across sources."
        if len(document_ids) > 1
        else "Only one document is in scope; use `search_chunks` for retrieval."
    )
    return (
        "You are a retrieval planning agent for a document QA system. "
        "On each step you must reply with ONLY a compact JSON object — no "
        "prose, no markdown fences. The JSON must match one of:\n"
        '  {"action":"call_tool","tool":"<name>","args":{...},"thought":"..."}\n'
        '  {"action":"answer","thought":"why we have enough context"}\n'
        '  {"action":"abstain","reason":"why retrieval cannot help"}\n\n'
        f"Documents in scope: [{doc_block}].\n"
        "Available tools:\n"
        f"{tools_block}\n\n"
        "Planning rules:\n"
        "1. Call tools only when they add information you do not already have.\n"
        "2. Do NOT re-run the exact same query against the exact same docs.\n"
        "3. Stop (action=answer) as soon as you have enough grounded chunks.\n"
        f"4. {multi_doc_hint}\n"
        "5. If no tool can help (e.g. chit-chat), use action=abstain.\n"
        "Respond with JSON only."
    )


def _context_summary(ctx: AgentToolContext) -> str:
    """Compact summary of everything the planner has seen so far this turn."""
    if not ctx.trace:
        return "No tool calls yet."
    lines: list[str] = []
    for step in ctx.trace[-4:]:  # keep context bounded
        lines.append(
            f"- {step['tool']}(args={json.dumps(step.get('args', {}))}) → "
            f"added {step['new_chunks']} new chunks "
            f"(total {step['total_chunks']})"
        )
    return "\n".join(lines)


async def _call_planner(
    *,
    provider: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    if provider == "openai":
        return await create_openai_text(api_key, model, messages)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, gemini_text, api_key, model, messages)


def _score_confidence(chunks: list[RetrievedChunk]) -> tuple[float, dict[str, float]]:
    """Reduce retrieved chunk scores into a single 0..1 confidence number.

    We average the top-3 scores (or fewer if we don't have that many)
    and clip to [0, 1]. Per-document confidence uses the best chunk per
    document — this feeds 3.6's "per-doc confidence" requirement.
    """
    if not chunks:
        return 0.0, {}
    sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
    top_n = sorted_chunks[: min(3, len(sorted_chunks))]
    global_conf = sum(c.score for c in top_n) / len(top_n)
    global_conf = max(0.0, min(1.0, global_conf))
    per_doc: dict[str, float] = {}
    for c in sorted_chunks:
        if c.document_id in per_doc:
            continue
        per_doc[c.document_id] = max(0.0, min(1.0, float(c.score)))
    return global_conf, per_doc


async def _fallback_search(
    *, ctx: AgentToolContext, question: str, trace_span: tracing._Span | None
) -> None:
    """If the planner bails without ever calling a tool, force one last search.

    Keeps the agent flow non-destructive: we always try to answer from
    *some* grounded chunks rather than handing a bare question to the
    final LLM.
    """
    if ctx.collected_chunks:
        return
    try:
        with tracing.span(trace_span, "agent.fallback_search"):
            await execute_tool(
                name="search_chunks",
                args={"query": question},
                ctx=ctx,
            )
    except Exception:  # noqa: BLE001
        logger.exception("agent_fallback_search_failed")


async def run_agent(
    *,
    question: str,
    owner_id: str,
    provider: str,
    provider_api_key: str,
    chat_model: str,
    embedding_model: str,
    primary_document_id: str,
    allowed_document_ids: list[str],
    top_k: int,
    min_score: float = 0.0,
    trace_span: tracing._Span | None = None,
) -> AgentRunResult:
    """Run the planner ↔ tools loop and return harvested chunks + telemetry."""

    ctx = AgentToolContext(
        owner_id=owner_id,
        provider=provider,
        provider_api_key=provider_api_key,
        primary_document_id=primary_document_id,
        allowed_document_ids=[d for d in allowed_document_ids if d],
        embedding_model=embedding_model,
        top_k=top_k,
        min_score=min_score,
    )

    max_iter = max(1, settings.retrieval_agent_max_iterations)
    stages: dict[str, Any] = {
        "agent_enabled": True,
        "max_iterations": max_iter,
        "documents_in_scope": len(ctx.allowed_document_ids),
    }

    if not ctx.allowed_document_ids:
        stages["planner_iterations"] = 0
        stages["stopped_reason"] = "no_documents"
        return AgentRunResult(
            chunks=[], iterations=0, stopped_reason="no_documents", stages=stages
        )

    system_prompt = _planner_system_prompt(ctx.allowed_document_ids)

    iteration = 0
    parse_failures = 0
    stopped_reason = "iteration_cap"

    with tracing.span(trace_span, "agent.loop", max_iterations=max_iter) as agent_span:
        while iteration < max_iter:
            iteration += 1
            planner_messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"User question: {question}\n\n"
                        f"Chunks collected so far: {len(ctx.collected_chunks)}"
                        f" (max {settings.retrieval_agent_max_chunks}).\n"
                        f"Prior tool trace:\n{_context_summary(ctx)}\n\n"
                        "Respond with the next JSON action only."
                    ),
                },
            ]
            with tracing.span(
                trace_span,
                "agent.planner_call",
                iteration=iteration,
                provider=provider,
                model=chat_model,
            ) as step_span:
                try:
                    raw = await _call_planner(
                        provider=provider,
                        api_key=provider_api_key,
                        model=chat_model.strip(),
                        messages=planner_messages,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("agent_planner_call_failed err=%s", exc)
                    step_span.update(error=str(exc))
                    stopped_reason = "planner_error"
                    break
                step_span.update(reply_chars=len(raw or ""))

            decision = _extract_json(raw or "")
            if decision is None:
                parse_failures += 1
                if parse_failures >= 2:
                    stopped_reason = "planner_parse_failed"
                    break
                continue
            parse_failures = 0
            action = (decision.get("action") or "").strip().lower()

            if action == "answer":
                stopped_reason = "planner_answer"
                break
            if action == "abstain":
                stopped_reason = "planner_abstain"
                break
            if action != "call_tool":
                # Unknown action — give the planner one more chance.
                parse_failures += 1
                if parse_failures >= 2:
                    stopped_reason = "planner_invalid_action"
                    break
                continue

            tool_name = decision.get("tool")
            tool_args = decision.get("args") or {}
            if not isinstance(tool_name, str) or not isinstance(tool_args, dict):
                parse_failures += 1
                if parse_failures >= 2:
                    stopped_reason = "planner_invalid_action"
                    break
                continue

            try:
                with tracing.span(
                    trace_span,
                    "agent.tool_call",
                    iteration=iteration,
                    tool=tool_name,
                ) as tool_span:
                    result = await execute_tool(name=tool_name, args=tool_args, ctx=ctx)
                    tool_span.update(
                        new_chunks=len(result.new_chunks),
                        total_chunks=len(ctx.collected_chunks),
                    )
            except ToolArgumentError as exc:
                # Inject the error back into the planner context via trace;
                # the next iteration's context_summary will surface it.
                ctx.trace.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "error": str(exc),
                        "new_chunks": 0,
                        "total_chunks": len(ctx.collected_chunks),
                    }
                )
                if "budget exhausted" in str(exc):
                    stopped_reason = "tool_budget_exhausted"
                    break
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent_tool_unexpected_error tool=%s", tool_name)
                ctx.trace.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "error": f"internal: {exc}",
                        "new_chunks": 0,
                        "total_chunks": len(ctx.collected_chunks),
                    }
                )
                stopped_reason = "tool_error"
                break

            # Early stop: we hit the chunk budget. More iterations won't help.
            if len(ctx.collected_chunks) >= settings.retrieval_agent_max_chunks:
                stopped_reason = "chunk_budget_reached"
                break

        agent_span.update(
            iterations=iteration,
            stopped_reason=stopped_reason,
            chunks=len(ctx.collected_chunks),
        )

    await _fallback_search(ctx=ctx, question=question, trace_span=trace_span)

    confidence, per_doc_conf = _score_confidence(ctx.collected_chunks)
    stages.update(
        {
            "planner_iterations": iteration,
            "stopped_reason": stopped_reason,
            "tool_trace": ctx.trace,
            "agent_chunk_count": len(ctx.collected_chunks),
            "agent_confidence": round(confidence, 4),
            "per_document_confidence": {k: round(v, 4) for k, v in per_doc_conf.items()},
        }
    )

    # Keep top-K for the final answer; the trace retains the full harvest.
    ranked_chunks = sorted(ctx.collected_chunks, key=lambda c: c.score, reverse=True)
    answer_chunks = ranked_chunks[: max(top_k, 1)]

    return AgentRunResult(
        chunks=answer_chunks,
        iterations=iteration,
        stopped_reason=stopped_reason,
        stages=stages,
        confidence=confidence,
        per_document_confidence=per_doc_conf,
    )
