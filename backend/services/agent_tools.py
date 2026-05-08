"""Tool registry for the agentic retrieval loop (Phase 3.2).

Each tool exposes:

- a stable ``name`` (used by the planner LLM and logged in traces)
- a strict JSON Schema for its arguments
- a short natural-language ``description`` the planner sees
- an async ``run`` function returning a JSON-serializable payload

The registry is deliberately small and audited: we never execute
free-form SQL or shell commands. Every tool is owner-scoped — the
``AgentToolContext`` carries the ``owner_id``, provider, and API key so
even if the LLM tries to switch document or user scope the tool layer
rejects it.

Tools currently shipped:

    search_chunks           — hybrid retrieval over the active document set
    get_document_summary    — first-paragraph-style synopsis from stored chunks
    list_documents          — owner-scoped inventory with filenames + status
    compare_documents       — parallel search_chunks against ≥2 docs for
                              cross-document synthesis (3.6)

Deferred intentionally:

    run_sql — requires the structured-extraction-table plumbing that
    lives behind ``extract.py`` schemas. Left as a TODO anchor so the
    agent loop can be extended without touching the prompt layer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from backend.database import fetch_all
from backend.services.embeddings import embed_query
from backend.services.retrieval_pipeline import RetrievalRequest, retrieve
from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings

logger = logging.getLogger("ragapp.agent_tools")


# ---------------------------------------------------------------------------
# Context & dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentToolContext:
    """Execution context shared by every tool call for a single chat turn.

    The agent loop creates one context per user question and threads it
    through every tool invocation. We keep provider credentials here
    (vs. on the tool arguments) so the planner LLM can *never* leak them
    into its thought traces.
    """

    owner_id: str
    provider: str
    provider_api_key: str
    primary_document_id: str
    allowed_document_ids: list[str]
    embedding_model: str
    top_k: int
    min_score: float = 0.0
    # Chunks accumulated across all tool calls this turn. The agent
    # inspects this to decide when to stop and also dedupes by chunk_id.
    collected_chunks: list[RetrievedChunk] = field(default_factory=list)
    # Per-tool-call trace records; surfaced via the `stages` payload.
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ToolResult:
    """Unified tool return envelope: serializable payload + chunks harvested."""

    payload: Any
    new_chunks: list[RetrievedChunk] = field(default_factory=list)


ToolRunner = Callable[[AgentToolContext, dict[str, Any]], Awaitable[ToolResult]]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    run: ToolRunner


# ---------------------------------------------------------------------------
# Argument validation (lightweight JSON Schema subset)
# ---------------------------------------------------------------------------


class ToolArgumentError(ValueError):
    """Raised when the planner hands back malformed tool arguments."""


def _coerce_doc_ids(value: Any, ctx: AgentToolContext) -> list[str]:
    """Normalize a user-supplied document_ids field and scope-check it.

    The planner frequently returns a single string instead of an array;
    we also accept the common tuple/string edge cases. Every returned ID
    must live in ``ctx.allowed_document_ids`` — we silently drop unknown
    IDs to keep the loop moving rather than 400-ing the whole turn.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value if v is not None]
    else:
        raise ToolArgumentError(f"document_ids must be a string or list, got {type(value).__name__}")
    allowed = set(ctx.allowed_document_ids)
    return [doc_id for doc_id in items if doc_id in allowed]


def _require_str(args: dict[str, Any], key: str, *, max_len: int = 500) -> str:
    value = args.get(key)
    if not isinstance(value, str):
        raise ToolArgumentError(f"argument '{key}' must be a string")
    value = value.strip()
    if not value:
        raise ToolArgumentError(f"argument '{key}' must be non-empty")
    if len(value) > max_len:
        value = value[:max_len]
    return value


def _optional_int(args: dict[str, Any], key: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = args.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ToolArgumentError(f"argument '{key}' must be an integer") from exc
    return max(minimum, min(maximum, value))


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _tool_search_chunks(ctx: AgentToolContext, args: dict[str, Any]) -> ToolResult:
    query = _require_str(args, "query", max_len=500)
    top_k = _optional_int(args, "top_k", default=ctx.top_k, minimum=1, maximum=20)
    doc_ids = _coerce_doc_ids(args.get("document_ids"), ctx) or ctx.allowed_document_ids

    embedding = await embed_query(ctx.provider, ctx.provider_api_key, ctx.embedding_model, query)
    result = await retrieve(
        RetrievalRequest(
            query=query,
            document_ids=doc_ids,
            owner_id=ctx.owner_id,
            query_embedding=embedding,
            top_k=top_k,
            min_score=ctx.min_score,
        ),
    )

    new_chunks: list[RetrievedChunk] = []
    seen_ids = {c.chunk_id for c in ctx.collected_chunks}
    for chunk in result.chunks:
        if chunk.chunk_id in seen_ids:
            continue
        seen_ids.add(chunk.chunk_id)
        new_chunks.append(chunk)

    payload = {
        "query": query,
        "document_ids": doc_ids,
        "hits": [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "score": round(c.score, 4),
                "page_number": c.page_number,
                "excerpt": (c.excerpt[:400] + "…") if len(c.excerpt) > 400 else c.excerpt,
            }
            for c in result.chunks
        ],
        "stages": result.stages,
        "new_chunks": len(new_chunks),
    }
    return ToolResult(payload=payload, new_chunks=new_chunks)


async def _tool_get_document_summary(ctx: AgentToolContext, args: dict[str, Any]) -> ToolResult:
    doc_ids = _coerce_doc_ids(args.get("document_id"), ctx) or _coerce_doc_ids(
        args.get("document_ids"), ctx
    )
    if not doc_ids:
        raise ToolArgumentError("document_id must reference an allowed document")
    document_id = doc_ids[0]

    rows = await fetch_all(
        """
        SELECT content, page_number, chunk_index, chunk_type
        FROM document_chunks
        WHERE document_id = ? AND owner_id = ?
        ORDER BY chunk_index ASC
        LIMIT ?
        """,
        (document_id, ctx.owner_id, 5),
    )
    if not rows:
        return ToolResult(payload={"document_id": document_id, "summary": "", "chunks_used": 0})

    text_parts: list[str] = []
    for row in rows:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 400:
            content = content[:400] + "…"
        text_parts.append(content)
    summary = "\n\n".join(text_parts)
    if len(summary) > 1500:
        summary = summary[:1500] + "…"
    return ToolResult(
        payload={
            "document_id": document_id,
            "summary": summary,
            "chunks_used": len(text_parts),
        }
    )


async def _tool_list_documents(ctx: AgentToolContext, args: dict[str, Any]) -> ToolResult:
    name_contains = args.get("name_contains")
    rows = await fetch_all(
        """
        SELECT id, filename, status, provider, embedding_model, chunk_count
        FROM documents
        WHERE owner_id = ?
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (ctx.owner_id,),
    )
    filtered = []
    needle = (name_contains or "").strip().lower() if isinstance(name_contains, str) else ""
    for row in rows:
        if row.get("id") not in ctx.allowed_document_ids:
            continue
        filename = (row.get("filename") or "").lower()
        if needle and needle not in filename:
            continue
        filtered.append(
            {
                "id": row["id"],
                "filename": row["filename"],
                "status": row["status"],
                "chunk_count": row.get("chunk_count", 0),
            }
        )
    return ToolResult(payload={"documents": filtered, "count": len(filtered)})


async def _tool_compare_documents(ctx: AgentToolContext, args: dict[str, Any]) -> ToolResult:
    query = _require_str(args, "query", max_len=500)
    doc_ids = _coerce_doc_ids(args.get("document_ids"), ctx)
    if len(doc_ids) < 2:
        raise ToolArgumentError(
            "compare_documents requires at least 2 allowed document_ids"
        )
    top_k = _optional_int(args, "top_k_per_doc", default=3, minimum=1, maximum=8)

    embedding = await embed_query(ctx.provider, ctx.provider_api_key, ctx.embedding_model, query)

    per_doc_payload: list[dict[str, Any]] = []
    aggregated_chunks: list[RetrievedChunk] = []
    seen_ids = {c.chunk_id for c in ctx.collected_chunks}

    tasks = [
        retrieve(
            RetrievalRequest(
                query=query,
                document_ids=[doc_id],
                owner_id=ctx.owner_id,
                query_embedding=embedding,
                top_k=top_k,
                min_score=ctx.min_score,
            ),
        )
        for doc_id in doc_ids
    ]
    results = await asyncio.gather(*tasks)

    for doc_id, result in zip(doc_ids, results):
        for chunk in result.chunks:
            if chunk.chunk_id in seen_ids:
                continue
            seen_ids.add(chunk.chunk_id)
            aggregated_chunks.append(chunk)

        best_score = max((c.score for c in result.chunks), default=0.0)
        per_doc_payload.append(
            {
                "document_id": doc_id,
                "best_score": round(best_score, 4),
                "hit_count": len(result.chunks),
                "top_excerpt": (
                    (result.chunks[0].excerpt[:400] + "…")
                    if result.chunks and len(result.chunks[0].excerpt) > 400
                    else (result.chunks[0].excerpt if result.chunks else "")
                ),
            }
        )

    per_doc_payload.sort(key=lambda d: d["best_score"], reverse=True)
    return ToolResult(
        payload={
            "query": query,
            "per_document": per_doc_payload,
            "new_chunks": len(aggregated_chunks),
        },
        new_chunks=aggregated_chunks,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "search_chunks": ToolDefinition(
        name="search_chunks",
        description=(
            "Retrieve document chunks relevant to a query using hybrid dense + "
            "lexical search over the active document set. Use this when the user "
            "question needs grounding in the source material."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subset of allowed document IDs to search.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "How many chunks to return. Defaults to the chat top_k.",
                },
            },
            "required": ["query"],
        },
        run=_tool_search_chunks,
    ),
    "get_document_summary": ToolDefinition(
        name="get_document_summary",
        description=(
            "Return a short synopsis of a single document by concatenating its "
            "first few stored chunks. Use this to orient the planner before "
            "deciding on further search_chunks calls."
        ),
        parameters={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "ID of the document to summarize.",
                },
            },
            "required": ["document_id"],
        },
        run=_tool_get_document_summary,
    ),
    "list_documents": ToolDefinition(
        name="list_documents",
        description=(
            "List documents available in the current user's scope so the agent "
            "can identify candidates before deeper retrieval."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name_contains": {
                    "type": "string",
                    "description": "Optional case-insensitive filename filter.",
                }
            },
        },
        run=_tool_list_documents,
    ),
    "compare_documents": ToolDefinition(
        name="compare_documents",
        description=(
            "Run parallel chunk retrieval against two or more allowed documents "
            "for the same query. Use for cross-document synthesis or to see "
            "where a topic is covered best. Adds the union of retrieved chunks "
            "to the citation pool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
                "document_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "description": "At least two allowed document IDs to compare.",
                },
                "top_k_per_doc": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "description": "Chunks per document to retrieve.",
                },
            },
            "required": ["query", "document_ids"],
        },
        run=_tool_compare_documents,
    ),
}


def tool_schemas_for_planner() -> list[dict[str, Any]]:
    """Serialize every tool into the planner-visible schema list.

    Deliberately matches the OpenAI function-calling shape so the same
    payload can be handed directly to ``chat.completions.create(tools=...)``
    in a future upgrade without translation.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": td.name,
                "description": td.description,
                "parameters": td.parameters,
            },
        }
        for td in TOOL_DEFINITIONS.values()
    ]


def tool_name_list() -> list[str]:
    return list(TOOL_DEFINITIONS.keys())


async def execute_tool(
    *, name: str, args: dict[str, Any], ctx: AgentToolContext
) -> ToolResult:
    """Run a registered tool with owner-scoped argument checks.

    Invariants enforced here so every caller benefits:

    1. Unknown tool → raise ``ToolArgumentError``.
    2. Per-turn tool-call cap from ``retrieval_agent_max_tool_calls``.
    3. Accumulated chunks capped at ``retrieval_agent_max_chunks``.
    """
    if len(ctx.trace) >= settings.retrieval_agent_max_tool_calls:
        raise ToolArgumentError("tool call budget exhausted")
    tool = TOOL_DEFINITIONS.get(name)
    if tool is None:
        raise ToolArgumentError(f"unknown tool '{name}'")
    result = await tool.run(ctx, args or {})

    if result.new_chunks:
        budget = max(0, settings.retrieval_agent_max_chunks - len(ctx.collected_chunks))
        accepted = result.new_chunks[:budget]
        ctx.collected_chunks.extend(accepted)
        # Reflect the post-cap count in the payload so the planner sees the
        # real number of chunks that joined the answer pool this call.
        if isinstance(result.payload, dict) and "new_chunks" in result.payload:
            result.payload["new_chunks"] = len(accepted)
        result = ToolResult(payload=result.payload, new_chunks=accepted)

    ctx.trace.append(
        {
            "tool": name,
            "args": args,
            "new_chunks": len(result.new_chunks),
            "total_chunks": len(ctx.collected_chunks),
        }
    )
    return result
