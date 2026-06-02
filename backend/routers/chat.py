"""Chat endpoints with grounded answers and rerun support."""

from __future__ import annotations

import json
import logging
import uuid
import asyncio
from typing import Any

try:
    import orjson
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    orjson = None

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import APIError
from pydantic import TypeAdapter

from backend.database import execute, execute_many, fetch_all, fetch_one, transaction, sql_format
from backend.errors import api_error_response
from backend.metrics import metrics
from backend.models import ChatRequest, Citation, RerunMessageRequest
from backend.routers.deps import RequestContext, get_request_context, require_provider_api_key
from backend.services import memory as memory_service
from backend.services import tracing
from backend.services.agent import run_agent
from backend.services.compression import compress_chunks
from backend.services.embeddings import embed_query
from backend.services.grounding import verify_groundedness
from backend.services.llm import (
    build_rag_prompt,
    create_openai_text,
    gemini_text,
    stream_gemini_text,
    stream_openai_text,
)
from backend.services.query_transform import transform as transform_query
from backend.services.retrieval_pipeline import RetrievalRequest, retrieve
from backend.settings import settings

logger = logging.getLogger("ragapp.chat")
TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"
router = APIRouter()

# ⚡ BOLT OPTIMIZATION:
# Pre-compile the TypeAdapter for list[Citation] to avoid runtime overhead.
# This uses Pydantic's underlying Rust-based JSON parser (pydantic-core) directly via
# dump_json(), skipping the standard library's json.dumps() and iterative dict instantiation.
# This yields a measurable performance improvement when parsing message histories with many sources.
_citation_list_adapter = TypeAdapter(list[Citation])

_TOKEN_PREFIX = b"event: token\ndata: "


async def _resolve_workspace_documents(
    *,
    owner_id: str,
    workspace_id: str,
    source_ids: list[str] | None,
    provider: str,
) -> list[dict]:
    """Phase 1: resolve workspace-scoped source selection into concrete documents.

    Returns ready documents that belong to ``workspace_id`` and match
    ``provider``. When ``source_ids`` is provided, the result is filtered to
    exactly those ``workspace_sources`` rows (each of which may reference a
    document). The result is ordered by document ``created_at`` ascending so
    the primary-document choice is deterministic.

    Fix #1: scope by workspace_id (not owner_id) so workspace members who
    didn't personally upload a doc can still see ready documents after RBAC
    has already cleared them.
    """
    base_query = """
        SELECT DISTINCT d.*
        FROM documents d
        {join}
        WHERE d.workspace_id = ?
          AND d.provider = ?
          AND d.status = 'ready'
        {where_extra}
        ORDER BY d.created_at ASC
    """
    params: tuple
    if source_ids:
        placeholders = ", ".join(["?"] * len(source_ids))
        query = base_query.format(
            join="JOIN workspace_sources ws ON ws.document_id = d.id AND ws.workspace_id = d.workspace_id",
            where_extra=f"AND ws.id IN ({placeholders})",
        )
        params = (workspace_id, provider, *source_ids)
    else:
        query = base_query.format(join="", where_extra="")
        params = (workspace_id, provider)
    rows = await fetch_all(query, params)
    return rows


async def _apply_workspace_to_chat_body(
    *,
    request: Request,
    context: RequestContext,
    body: ChatRequest,
):
    """Phase 1: populate ``document_id``/``document_ids`` from workspace scope.

    Mutates ``body`` in place. Returns ``(ok, error_response)``. If ok is False
    the caller must return ``error_response``.
    """
    # Phase 3 RBAC: when chat is workspace-scoped, every caller (including the
    # owner) must have at least ``viewer`` access. The shared helper already
    # returns 404 for unknown workspaces and 403 for insufficient roles.
    if body.workspace_id:
        from backend.services.workspace_rbac import check_workspace_role

        _, err = await check_workspace_role(
            workspace_id=body.workspace_id,
            request=request,
            context=context,
            minimum="viewer",
        )
        if err:
            return False, err

    if body.document_id:
        return True, None
    if not body.workspace_id:
        return False, api_error_response(
            request=request,
            status_code=400,
            error="Either document_id or workspace_id is required.",
            code="DOCUMENT_OR_WORKSPACE_REQUIRED",
        )
    docs = await _resolve_workspace_documents(
        owner_id=context.owner_id,
        workspace_id=body.workspace_id,
        source_ids=body.source_ids or None,
        provider=body.provider,
    )
    if not docs:
        return False, api_error_response(
            request=request,
            status_code=400,
            error="No ready sources in the selected workspace.",
            code="WORKSPACE_NO_READY_SOURCES",
            details={"workspace_id": body.workspace_id},
        )
    body.document_id = docs[0]["id"]
    extras = [d["id"] for d in docs[1:]]
    existing = list(body.document_ids or [])
    for doc_id in extras:
        if doc_id not in existing:
            existing.append(doc_id)
    body.document_ids = existing or None
    return True, None


async def _load_ready_document(
    *,
    request: Request,
    context: RequestContext,
    document_id: str,
    provider: str,
    workspace_id: str | None = None,
):
    # Fix #1: when a workspace_id is provided (RBAC already passed), allow
    # loading documents that belong to that workspace even if the caller is
    # not the uploader. Fall back to owner_id scoping for non-workspace calls.
    if workspace_id:
        document = await fetch_one(
            "SELECT * FROM documents WHERE id = ? AND workspace_id = ?",
            (document_id.strip(), workspace_id),
        )
    else:
        document = await fetch_one(
            "SELECT * FROM documents WHERE id = ? AND owner_id = ?",
            (document_id.strip(), context.owner_id),
        )
    if not document:
        return None, api_error_response(
            request=request,
            status_code=404,
            error="Unknown document_id.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id.strip()},
        )
    if document["status"] != "ready":
        return None, api_error_response(
            request=request,
            status_code=400,
            error=f"Document is not ready. Current status: {document['status']}",
            code="DOCUMENT_NOT_READY",
            details={"status": document["status"]},
        )
    if document["provider"] != provider:
        return None, api_error_response(
            request=request,
            status_code=400,
            error="Provider does not match the indexed document.",
            code="PROVIDER_MISMATCH",
        )
    return document, None


async def _maybe_transform_queries(
    *,
    provider: str,
    provider_api_key: str,
    chat_model: str,
    embedding_model: str,
    question: str,
    trace_span: tracing._Span | None,
) -> tuple[list[tuple[str, list[float]]], list[str]]:
    """If query-transform flag is on, generate + embed alternative queries.

    Returns (extra_query_embeddings, transform_labels). Both empty when
    the flag is off or any step fails.
    """
    if not settings.retrieval_query_transforms_enabled:
        return [], []
    with tracing.span(trace_span, "query_transform", provider=provider) as t_span:
        try:
            transformed = await transform_query(
                question,
                provider=provider,
                api_key=provider_api_key,
                model=chat_model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("query_transform_failed err=%s", exc)
            transformed = []
        t_span.update(hits=len(transformed))
    if not transformed:
        return [], []

    with tracing.span(trace_span, "embed_transformed_queries", count=len(transformed)):
        lanes: list[tuple[str, list[float]]] = []

        # ⚡ BOLT OPTIMIZATION: Batch multiple embeddings using gather
        tasks = [
            embed_query(provider, provider_api_key, embedding_model, tq.text)
            for tq in transformed
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for tq, result in zip(transformed, results):
            if isinstance(result, Exception):
                logger.warning("transform_embed_failed kind=%s err=%s", tq.kind, result)
                continue
            lanes.append((tq.kind, result))
    return lanes, [tq.kind for tq in transformed]


def _compute_active_learning_hint(
    stages: dict[str, Any],
    chunks: list,
) -> dict[str, Any] | None:
    """Phase 3.9: surface a one-line nudge when retrieval looks weak.

    The rule is deliberately conservative so the UI isn't noisy:

    - honors ``ACTIVE_LEARNING_HINT_ENABLED``
    - triggers only when the best retrieved score is below
      ``ACTIVE_LEARNING_SCORE_FLOOR`` or the agent abstained

    Returns ``None`` when no hint should fire (preferred: UI hides the
    element rather than rendering an empty state).
    """
    if not settings.active_learning_hint_enabled:
        return None
    stopped_reason = stages.get("stopped_reason") if isinstance(stages, dict) else None
    best_score = 0.0
    if chunks:
        best_score = max((getattr(c, "score", 0.0) or 0.0) for c in chunks)

    if stopped_reason == "planner_abstain":
        return {
            "suggestion": "The agent couldn't ground this question in your documents.",
            "action": "rephrase",
            "reason": "planner_abstain",
        }
    if not chunks:
        return {
            "suggestion": "No matching passages were found.",
            "action": "rephrase",
            "reason": "no_chunks",
        }
    if best_score < settings.active_learning_score_floor:
        return {
            "suggestion": "Retrieval confidence is low — try rephrasing or widening the document set.",
            "action": "expand_search",
            "reason": "low_confidence",
            "best_score": round(float(best_score), 4),
        }
    return None


async def _run_agent_retrieval(
    *,
    request: Request,
    context: RequestContext,
    provider: str,
    provider_api_key: str,
    document: dict,
    question: str,
    top_k: int | None,
    similarity_threshold: float | None,
    extra_document_ids: list[str] | None,
    trace_span: tracing._Span | None,
    chat_model: str | None,
    workspace_id: str | None = None,
):
    """Phase 3.1 dispatch: plan → tools → chunks, replacing the linear pipeline.

    Returns the same ``(chunks, stages, error_response)`` tuple as
    :func:`_embed_and_retrieve` so the calling sites stay oblivious to
    which retrieval path ran.
    """
    effective_top_k = top_k if top_k is not None else settings.rag_top_k
    effective_min_score = similarity_threshold if similarity_threshold is not None else 0.0
    allowed = [document["id"]] + list(extra_document_ids or [])

    result = await run_agent(
        question=question,
        owner_id=context.owner_id,
        provider=provider,
        provider_api_key=provider_api_key,
        chat_model=(chat_model or "").strip(),
        embedding_model=document["embedding_model"],
        primary_document_id=document["id"],
        allowed_document_ids=allowed,
        top_k=effective_top_k,
        min_score=effective_min_score,
        workspace_id=workspace_id,
        trace_span=trace_span,
    )
    stages = {"retrieval_path": "agent", **result.stages}
    if not result.chunks:
        return None, stages, api_error_response(
            request=request,
            status_code=400,
            error="The agent could not gather any grounded context for this question.",
            code="AGENT_NO_CONTEXT",
        )
    metrics.observe("chat_citations_count", float(len(result.chunks)), provider=provider)
    return result.chunks, stages, None


async def _embed_and_retrieve(
    *,
    request: Request,
    context: RequestContext,
    provider: str,
    provider_api_key: str,
    document: dict,
    question: str,
    top_k: int | None,
    similarity_threshold: float | None,
    extra_document_ids: list[str] | None,
    trace_span: tracing._Span | None,
    chat_model: str | None = None,
    workspace_id: str | None = None,
):
    """Embed the question and run the retrieval pipeline. Returns (chunks, stages, error_response)."""
    if extra_document_ids:
        all_doc_ids = [document["id"]] + list(extra_document_ids)
        placeholders = ", ".join(["?"] * len(all_doc_ids))
        ws_id = workspace_id or ""
        rows = await fetch_all(
            f"SELECT id, embedding_model FROM documents WHERE (owner_id = ? OR workspace_id = ?) AND id IN ({placeholders})",
            (context.owner_id, ws_id, *all_doc_ids),
        )
        models_by_id = {row["id"]: row["embedding_model"] for row in rows}
        expected_model = document["embedding_model"]
        mismatched = [
            doc_id
            for doc_id in extra_document_ids
            if models_by_id.get(doc_id) and models_by_id.get(doc_id) != expected_model
        ]
        if mismatched:
            return None, None, api_error_response(
                request=request,
                status_code=400,
                error="All selected documents must use the same embedding model for multi-document chat.",
                code="EMBEDDING_MODEL_MISMATCH",
                details={
                    "expected_embedding_model": expected_model,
                    "mismatched_document_ids": mismatched,
                },
            )

    effective_top_k = top_k if top_k is not None else settings.rag_top_k
    effective_min_score = similarity_threshold if similarity_threshold is not None else 0.0

    with tracing.span(trace_span, "embed_query", provider=provider, model=document["embedding_model"]):
        try:
            question_embedding = await embed_query(
                provider,
                provider_api_key,
                document["embedding_model"],
                question,
            )
        except Exception as exc:
            metrics.inc("chat_stream_failures_total", reason="embedding_failed")
            return None, None, api_error_response(
                request=request,
                status_code=502,
                error=f"Query embedding failed: {exc}",
                code="QUERY_EMBEDDING_FAILED",
            )

    # Optional query transformations produce extra dense lanes that the
    # pipeline RRF-fuses with the primary lane. Failures degrade silently.
    extra_lanes, transform_kinds = await _maybe_transform_queries(
        provider=provider,
        provider_api_key=provider_api_key,
        chat_model=(chat_model or "").strip(),
        embedding_model=document["embedding_model"],
        question=question,
        trace_span=trace_span,
    )

    document_ids = [document["id"]] + list(extra_document_ids or [])
    retrieval = await retrieve(
        RetrievalRequest(
            query=question,
            document_ids=document_ids,
            owner_id=context.owner_id,
            query_embedding=question_embedding,
            top_k=effective_top_k,
            min_score=effective_min_score,
            workspace_id=workspace_id,
            extra_query_embeddings=extra_lanes,
        ),
        trace_span=trace_span,
    )
    if transform_kinds:
        retrieval.stages["query_transforms"] = transform_kinds
    if not retrieval.chunks:
        return None, retrieval.stages, api_error_response(
            request=request,
            status_code=400,
            error="No matching context found. Try re-indexing the document.",
            code="NO_MATCHING_CONTEXT",
        )
    retrieval.stages["retrieval_path"] = "pipeline"
    metrics.observe("chat_citations_count", float(len(retrieval.chunks)), provider=provider)

    # Optional context compression — shrinks each chunk's excerpt before
    # prompt-build without touching stored citations. Default: no-op.
    if settings.context_compression_mode != "none":
        with tracing.span(
            trace_span,
            "context_compression",
            mode=settings.context_compression_mode,
            target_tokens=settings.context_compression_target_tokens,
        ) as comp_span:
            compressed, comp_stats = compress_chunks(
                retrieval.chunks,
                question=question,
                mode=settings.context_compression_mode,
                target_tokens=settings.context_compression_target_tokens,
            )
            comp_span.update(**comp_stats)
        retrieval.stages["compression"] = comp_stats
        return compressed, retrieval.stages, None
    return retrieval.chunks, retrieval.stages, None


def _citations_from_chunks(chunks) -> list[Citation]:
    citations: list[Citation] = []
    for c in chunks:
        chunk_type = getattr(c, "chunk_type", "text") or "text"
        artifact_metadata: dict | None = None
        raw_meta = getattr(c, "metadata_json", None)
        if chunk_type == "artifact" and raw_meta:
            try:
                parsed = json.loads(raw_meta)
                if isinstance(parsed, dict):
                    artifact_metadata = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                artifact_metadata = None
        citations.append(
            Citation(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                excerpt=c.excerpt,
                score=c.score,
                page_number=c.page_number,
                chunk_type=chunk_type,
                artifact_metadata=artifact_metadata,
            )
        )
    return citations


async def _save_turn(
    *,
    context: RequestContext,
    conversation_id: str,
    user_question: str,
    assistant_message_id: str,
    answer: str,
    sources_json: str,
    mode: str | None = None,
) -> None:
    user_message_id = str(uuid.uuid4())
    async with transaction() as conn:
        if settings.using_postgres:
            await conn.execute(
                sql_format("INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', ?)"),
                (user_message_id, context.owner_id, conversation_id, user_question),
            )
            await conn.execute(
                sql_format("""
                    INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json, mode)
                    VALUES (?, ?, ?, 'assistant', ?, ?, ?)
                """),
                (assistant_message_id, context.owner_id, conversation_id, answer, sources_json, mode or "ask"),
            )
            await conn.execute(
                sql_format(f"UPDATE conversations SET updated_at = {TIMESTAMP_SQL} WHERE id = ? AND owner_id = ?"),
                (conversation_id, context.owner_id),
            )
        else:
            await conn.execute(
                "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', ?)",
                (user_message_id, context.owner_id, conversation_id, user_question),
            )
            await conn.execute(
                """
                INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json, mode)
                VALUES (?, ?, ?, 'assistant', ?, ?, ?)
                """,
                (assistant_message_id, context.owner_id, conversation_id, answer, sources_json, mode or "ask"),
            )
            await conn.execute(
                f"UPDATE conversations SET updated_at = {TIMESTAMP_SQL} WHERE id = ? AND owner_id = ?",
                (conversation_id, context.owner_id),
            )


async def _generate_chat_response(
    *,
    request: Request,
    context: RequestContext,
    provider: str,
    model: str,
    document: dict,
    question: str,
    conversation_id: str,
    history: list[dict[str, str]],
    provider_api_key: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    extra_document_ids: list[str] | None = None,
    mode: str | None = None,
    workspace_id: str | None = None,
):
    """
    Generate a grounded assistant response for a question, persist the user and assistant messages, update the conversation timestamp, and return the created assistant message payload.
    
    Parameters:
        provider (str): LLM provider identifier (e.g., "openai"). Used to select the generation path.
        model (str): Model name to use for text generation.
        document (dict): Document record containing at least `id` and `embedding_model` used for retrieval and embedding.
        history (list[dict[str, str]]): Prior conversation messages (each item with `role` and `content`) used to build the RAG prompt; will be truncated by caller if needed.
        top_k (int | None): Optional override for the number of retrieved passages to return to the generator; when omitted, falls back to server settings.
        similarity_threshold (float | None): Optional minimum similarity score filter for retrieval; when omitted, defaults to 0.0.
        extra_document_ids (list[str] | None): Optional additional document IDs to include in the retrieval pool alongside the primary `document["id"]`.
    
    Returns:
        dict: A payload with the assistant response and metadata:
            conversation_id (str): ID of the conversation the response belongs to.
            message_id (str): Newly created assistant message ID.
            sources (list[tuple|object]): List of `Citation` objects describing retrieved citations (chunk_id, document_id, excerpt, score, page_number).
            content (str): The assistant's generated answer.
    """
    trimmed_question = question.strip()

    with tracing.trace(
        "chat.non_streaming",
        provider=provider,
        model=model,
        document_id=document["id"],
        owner_id=context.owner_id,
    ) as trace_span:
        if settings.retrieval_agent_enabled:
            chunks, stages, err = await _run_agent_retrieval(
                request=request,
                context=context,
                provider=provider,
                provider_api_key=provider_api_key,
                document=document,
                question=trimmed_question,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                extra_document_ids=extra_document_ids,
                trace_span=trace_span,
                chat_model=model,
                workspace_id=workspace_id,
            )
        else:
            chunks, stages, err = await _embed_and_retrieve(
                request=request,
                context=context,
                provider=provider,
                provider_api_key=provider_api_key,
                document=document,
                question=trimmed_question,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                extra_document_ids=extra_document_ids,
                trace_span=trace_span,
                chat_model=model,
                workspace_id=workspace_id,
            )
        if err is not None:
            return err

        # Phase 2: augment workspace-scoped retrieval with saved artifacts.
        if workspace_id and chunks is not None:
            from backend.services import artifact_retrieval as _art

            artifact_chunks = await _art.retrieve_workspace_artifacts(
                workspace_id=workspace_id,
                question=trimmed_question,
                primary_citation_count=len(chunks),
            )
            if artifact_chunks:
                chunks = list(chunks) + list(artifact_chunks)
                if isinstance(stages, dict):
                    stages["artifacts"] = {"count": len(artifact_chunks)}

        hint = _compute_active_learning_hint(stages or {}, chunks or [])
        if hint is not None and isinstance(stages, dict):
            stages["active_learning_hint"] = hint

        memory_ctx = await memory_service.build_context(
            conversation_id=conversation_id,
            owner_id=context.owner_id,
            history=history,
            provider=provider,
            api_key=provider_api_key,
            model=model,
        )
        if isinstance(stages, dict):
            stages["memory"] = memory_ctx.stages

        source_payload = _citations_from_chunks(chunks)
        source_payload_json = _citation_list_adapter.dump_json(source_payload).decode("utf-8")
        prompt = build_rag_prompt(
            chunks, trimmed_question, history=memory_ctx.recent, mode=mode
        )
        prompt = memory_service.inject_summary_into_messages(prompt, memory_ctx.summary)
        assistant_message_id = str(uuid.uuid4())

        try:
            with tracing.span(trace_span, "generate", provider=provider, model=model):
                if provider == "openai":
                    answer = await create_openai_text(provider_api_key, model.strip(), prompt)
                else:
                    loop = asyncio.get_running_loop()
                    answer = await loop.run_in_executor(
                        None,
                        gemini_text,
                        provider_api_key,
                        model.strip(),
                        prompt,
                    )
        except APIError as exc:
            metrics.inc("chat_stream_failures_total", reason="provider_api_error")
            return api_error_response(request=request, status_code=502, error=str(exc), code="PROVIDER_API_ERROR")
        except Exception as exc:
            logger.exception("chat_generation_failed")
            metrics.inc("chat_stream_failures_total", reason="stream_failed")
            return api_error_response(request=request, status_code=500, error=str(exc), code="GENERATION_FAILED")

        # Optional groundedness verification (second-pass LLM). Default OFF.
        grounding = None
        if settings.groundedness_verifier_enabled:
            with tracing.span(trace_span, "verify_groundedness", provider=provider, model=model):
                grounding = await verify_groundedness(
                    answer=answer,
                    sources=source_payload,
                    provider=provider,
                    api_key=provider_api_key,
                    model=model,
                )
            stages["groundedness"] = {
                "verified": grounding.get("verified"),
                "score": grounding.get("score"),
            }

        await _save_turn(
            context=context,
            conversation_id=conversation_id,
            user_question=trimmed_question,
            assistant_message_id=assistant_message_id,
            answer=answer,
            sources_json=source_payload_json,
            mode=mode,
        )

        response_body: dict[str, Any] = {
            "conversation_id": conversation_id,
            "message_id": assistant_message_id,
            "sources": source_payload,
            "content": answer,
            "stages": stages,
        }
        if grounding is not None:
            response_body["grounding"] = grounding
        return response_body


def _sse_event(event: str, data: dict | str) -> bytes:
    if event == "token" and isinstance(data, dict):
        # ⚡ BOLT OPTIMIZATION: Fast path for high-frequency token events.
        # Bypasses string encoding and datetime parsing overhead.
        if orjson is not None:
            payload_bytes = orjson.dumps(data)
        else:
            payload_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return _TOKEN_PREFIX + payload_bytes + b"\n\n"

    if isinstance(data, str):
        payload_bytes = data.encode("utf-8")
    elif orjson is not None:
        payload_bytes = orjson.dumps(data, default=str, option=orjson.OPT_PASSTHROUGH_DATETIME)
    else:
        payload_bytes = json.dumps(data, default=str).encode("utf-8")

    event_bytes = event.encode("utf-8")
    return b"event: " + event_bytes + b"\ndata: " + payload_bytes + b"\n\n"


async def _stream_chat_response(
    *,
    request: Request,
    context: RequestContext,
    provider: str,
    model: str,
    document: dict,
    question: str,
    conversation_id: str,
    history: list[dict[str, str]],
    provider_api_key: str,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    extra_document_ids: list[str] | None = None,
    mode: str | None = None,
    workspace_id: str | None = None,
):
    trimmed_question = question.strip()
    trace_span_cm = tracing.trace(
        "chat.streaming",
        provider=provider,
        model=model,
        document_id=document["id"],
        owner_id=context.owner_id,
    )

    async def generator():
        with trace_span_cm as trace_span:
            if settings.retrieval_agent_enabled:
                chunks, stages, err = await _run_agent_retrieval(
                    request=request,
                    context=context,
                    provider=provider,
                    provider_api_key=provider_api_key,
                    document=document,
                    question=trimmed_question,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    extra_document_ids=extra_document_ids,
                    trace_span=trace_span,
                    chat_model=model,
                    workspace_id=workspace_id,
                )
            else:
                chunks, stages, err = await _embed_and_retrieve(
                    request=request,
                    context=context,
                    provider=provider,
                    provider_api_key=provider_api_key,
                    document=document,
                    question=trimmed_question,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                    extra_document_ids=extra_document_ids,
                    trace_span=trace_span,
                    chat_model=model,
                    workspace_id=workspace_id,
                )
            if err is not None:
                # Serialize the error response's body through SSE.
                body = err.body if hasattr(err, "body") else b"{}"
                try:
                    payload = json.loads(body)
                except Exception:
                    payload = {"error": "chat failed", "code": "UNKNOWN"}
                yield _sse_event("error", payload)
                return

            # Phase 2: augment workspace-scoped retrieval with saved artifacts.
            if workspace_id and chunks is not None:
                from backend.services import artifact_retrieval as _art

                artifact_chunks = await _art.retrieve_workspace_artifacts(
                    workspace_id=workspace_id,
                    question=trimmed_question,
                    primary_citation_count=len(chunks),
                )
                if artifact_chunks:
                    chunks = list(chunks) + list(artifact_chunks)
                    if isinstance(stages, dict):
                        stages["artifacts"] = {"count": len(artifact_chunks)}

            hint = _compute_active_learning_hint(stages or {}, chunks or [])
            if hint is not None and isinstance(stages, dict):
                stages["active_learning_hint"] = hint

            memory_ctx = await memory_service.build_context(
                conversation_id=conversation_id,
                owner_id=context.owner_id,
                history=history,
                provider=provider,
                api_key=provider_api_key,
                model=model,
            )
            if isinstance(stages, dict):
                stages["memory"] = memory_ctx.stages

            source_payload = _citations_from_chunks(chunks)
            source_payload_json = _citation_list_adapter.dump_json(source_payload).decode("utf-8")
            yield _sse_event(
                "sources",
                {
                    "conversation_id": conversation_id,
                    "sources": [s.model_dump() for s in source_payload],
                    "stages": stages,
                },
            )

            prompt = build_rag_prompt(
                chunks, trimmed_question, history=memory_ctx.recent, mode=mode
            )
            prompt = memory_service.inject_summary_into_messages(prompt, memory_ctx.summary)
            assistant_message_id = str(uuid.uuid4())
            collected: list[str] = []

            try:
                with tracing.span(trace_span, "generate", provider=provider, model=model, streaming=True):
                    if provider == "openai":
                        async for delta in stream_openai_text(provider_api_key, model.strip(), prompt):
                            collected.append(delta)
                            yield _sse_event("token", {"delta": delta})
                    else:
                        loop = asyncio.get_running_loop()
                        # Bounded queue provides backpressure so a fast Gemini
                        # stream can't grow memory without bound.
                        queue: asyncio.Queue[str | None | Exception] = asyncio.Queue(maxsize=64)

                        def _run_gemini():
                            # Use run_coroutine_threadsafe(...).result() rather
                            # than call_soon_threadsafe(put_nowait, ...). On a
                            # bounded queue, put_nowait raises QueueFull from
                            # inside the event-loop callback (outside this
                            # try/except), which silently drops tokens or the
                            # final sentinel and can hang the consumer forever.
                            # put() applies real backpressure and surfaces any
                            # error here so it propagates via the queue.
                            def _put(item: str | None | Exception) -> None:
                                asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()

                            try:
                                for piece in stream_gemini_text(provider_api_key, model.strip(), prompt):
                                    _put(piece)
                            except Exception as exc:
                                _put(exc)
                            finally:
                                _put(None)

                        loop.run_in_executor(None, _run_gemini)
                        consumed_sentinel = False
                        try:
                            while True:
                                piece = await queue.get()
                                if piece is None:
                                    consumed_sentinel = True
                                    break
                                if isinstance(piece, Exception):
                                    raise piece
                                collected.append(piece)
                                yield _sse_event("token", {"delta": piece})
                        finally:
                            # If we exited before consuming the sentinel (client
                            # disconnect or a raised exception), the producer
                            # thread may be blocked putting into the bounded
                            # queue. Drain remaining items — awaiting get()
                            # suspends (no busy-loop) and frees queue slots — so
                            # the producer reaches its finally, emits the
                            # sentinel, and the executor thread exits cleanly.
                            if not consumed_sentinel:
                                while True:
                                    try:
                                        # Add a timeout to prevent indefinite hanging
                                        # if the producer thread fails to emit the sentinel.
                                        item = await asyncio.wait_for(queue.get(), timeout=5.0)
                                        if item is None:
                                            break
                                    except asyncio.TimeoutError:
                                        logger.warning("stream_queue_drain_timeout")
                                        break
            except APIError as exc:
                metrics.inc("chat_stream_failures_total", reason="provider_api_error")
                yield _sse_event("error", {"error": str(exc), "code": "PROVIDER_API_ERROR"})
                return
            except Exception as exc:
                logger.exception("chat_stream_failed")
                metrics.inc("chat_stream_failures_total", reason="stream_failed")
                yield _sse_event("error", {"error": str(exc), "code": "GENERATION_FAILED"})
                return

            answer = "".join(collected)
            if not answer.strip():
                logger.warning(
                    "chat_stream_empty_tokens_fallback provider=%s model=%s",
                    provider,
                    model.strip(),
                )
                try:
                    with tracing.span(trace_span, "generate_fallback", provider=provider, model=model):
                        if provider == "openai":
                            answer = await create_openai_text(
                                provider_api_key, model.strip(), prompt
                            )
                        else:
                            loop = asyncio.get_running_loop()
                            answer = await loop.run_in_executor(
                                None,
                                gemini_text,
                                provider_api_key,
                                model.strip(),
                                prompt,
                            )
                except APIError as exc:
                    metrics.inc("chat_stream_failures_total", reason="provider_api_error")
                    yield _sse_event("error", {"error": str(exc), "code": "PROVIDER_API_ERROR"})
                    return
                except Exception as exc:
                    logger.exception("chat_stream_fallback_failed")
                    metrics.inc("chat_stream_failures_total", reason="stream_failed")
                    yield _sse_event("error", {"error": str(exc), "code": "GENERATION_FAILED"})
                    return
                answer = (answer or "").strip()
                if not answer:
                    yield _sse_event(
                        "error",
                        {
                            "error": "The model returned no text. Try another model or check your API key.",
                            "code": "EMPTY_RESPONSE",
                        },
                    )
                    return
                yield _sse_event("token", {"delta": answer})

            if settings.groundedness_verifier_enabled:
                with tracing.span(trace_span, "verify_groundedness", provider=provider, model=model):
                    grounding = await verify_groundedness(
                        answer=answer,
                        sources=source_payload,
                        provider=provider,
                        api_key=provider_api_key,
                        model=model,
                    )
                yield _sse_event("grounding", grounding)

            await _save_turn(
                context=context,
                conversation_id=conversation_id,
                user_question=trimmed_question,
                assistant_message_id=assistant_message_id,
                answer=answer,
                sources_json=source_payload_json,
                mode=mode,
            )
            yield _sse_event(
                "message_saved",
                {
                    "conversation_id": conversation_id,
                    "message_id": assistant_message_id,
                },
            )
            yield _sse_event("done", {"content": answer})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _resolve_or_create_conversation(
    *,
    request: Request,
    context: RequestContext,
    body: ChatRequest,
):
    """Load an existing conversation (validating scope) or create a new one.

    Returns (conversation_id, error_response). Exactly one of them is set.
    """
    conversation_id = body.conversation_id
    if conversation_id:
        conversation = await fetch_one(
            "SELECT id, document_id FROM conversations WHERE id = ? AND owner_id = ?",
            (conversation_id, context.owner_id),
        )
        if not conversation:
            return None, api_error_response(
                request=request,
                status_code=404,
                error="Conversation not found.",
                code="CONVERSATION_NOT_FOUND",
                details={"conversation_id": conversation_id},
            )
        if conversation["document_id"] != body.document_id:
            return None, api_error_response(
                request=request,
                status_code=400,
                error="Conversation does not belong to that document.",
                code="CONVERSATION_DOCUMENT_MISMATCH",
            )
        return conversation_id, None

    conversation_id = str(uuid.uuid4())
    title = body.question.strip()[:80] + ("..." if len(body.question.strip()) > 80 else "")
    extra_ids = [d for d in (body.document_ids or []) if d != body.document_id]
    doc_ids_json = json.dumps([body.document_id] + extra_ids) if extra_ids else None
    # Phase 0: ensure every new conversation lands in a workspace. Prefer the
    # document's workspace, falling back to the caller's default.
    workspace_id = getattr(body, "workspace_id", None) or None
    if not workspace_id and body.document_id:
        # When body.workspace_id is absent, we intentionally pass an empty string
        # for ws_id_check so the OR clause is a no-op. This ensures only owner-scoped
        # documents are matched, preventing accidental matches with shared workspace docs.
        ws_id_check = workspace_id or ""
        doc_row = await fetch_one(
            "SELECT workspace_id FROM documents WHERE id = ? AND (owner_id = ? OR workspace_id = ?)",
            (body.document_id, context.owner_id, ws_id_check),
        )
        if doc_row and doc_row.get("workspace_id"):
            workspace_id = doc_row["workspace_id"]
    if not workspace_id:
        from backend.services import workspace_service as _ws

        default_ws = await _ws.ensure_default_workspace(context.owner_id)
        workspace_id = default_ws["id"]
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, title, document_ids_json, workspace_id) VALUES (?, ?, ?, ?, ?, ?)",
        (conversation_id, context.owner_id, body.document_id, title, doc_ids_json, workspace_id),
    )
    return conversation_id, None


async def _load_history(conversation_id: str, owner_id: str) -> list[dict[str, str]]:
    rows = await fetch_all(
        "SELECT role, content FROM messages WHERE conversation_id = ? AND owner_id = ? ORDER BY created_at ASC",
        (conversation_id, owner_id),
    )
    return [{"role": row["role"], "content": row["content"]} for row in rows][
        -settings.max_conversation_history :
    ]


@router.post("/chat", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    """
    Handle a chat request: create or continue a conversation for a document and generate a grounded assistant response.
    
    Processes the incoming ChatRequest by validating the target document, creating a new conversation when none is supplied (including storing optional extra document IDs), loading recent conversation history, and delegating to the internal generation routine to retrieve context, persist messages, and produce the assistant reply. Returns immediately with structured API error responses for validation failures (document not found/not ready/provider mismatch, conversation not found, or conversation/document mismatch).
    
    Parameters:
        body (ChatRequest): The request payload containing at least `question`, `document_id`, `provider`, and `model`. May also include `conversation_id` to continue an existing conversation, `document_ids` to include extra documents for retrieval, and retrieval tuning fields `top_k` and `similarity_threshold`.
        request (Request): HTTP request object (injected dependency).
        context (RequestContext): Request-scoped context including `owner_id` (injected dependency).
    
    Returns:
        dict: On success, a payload with `conversation_id` (str), `message_id` (str) for the created assistant message, `sources` (list of Citation objects), and `content` (assistant text). On failure, an API error response dict produced by `api_error_response` with appropriate HTTP status and error `code`.
    """
    ok, err = await _apply_workspace_to_chat_body(request=request, context=context, body=body)
    if not ok:
        return err
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
        workspace_id=getattr(body, "workspace_id", None),
    )
    if error_response:
        return error_response
    assert document is not None

    conversation_id, err = await _resolve_or_create_conversation(
        request=request, context=context, body=body
    )
    if err:
        return err
    assert conversation_id is not None

    history = await _load_history(conversation_id, context.owner_id)
    extra_doc_ids = [d for d in (body.document_ids or []) if d != body.document_id]
    return await _generate_chat_response(
        request=request,
        context=context,
        provider=body.provider,
        model=body.model,
        document=document,
        question=body.question,
        conversation_id=conversation_id,
        history=history,
        provider_api_key=provider_api_key,
        top_k=body.top_k,
        similarity_threshold=body.similarity_threshold,
        extra_document_ids=extra_doc_ids or None,
        mode=body.mode,
        workspace_id=getattr(body, "workspace_id", None),
    )


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    body: ChatRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    """Server-sent events version of /chat. Emits `sources`, `token`,
    `message_saved`, `done`, and `error` events per README contract."""
    ok, err = await _apply_workspace_to_chat_body(request=request, context=context, body=body)
    if not ok:
        return err
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
        workspace_id=getattr(body, "workspace_id", None),
    )
    if error_response:
        return error_response
    assert document is not None

    conversation_id, err = await _resolve_or_create_conversation(
        request=request, context=context, body=body
    )
    if err:
        return err
    assert conversation_id is not None

    history = await _load_history(conversation_id, context.owner_id)
    extra_doc_ids = [d for d in (body.document_ids or []) if d != body.document_id]
    return await _stream_chat_response(
        request=request,
        context=context,
        provider=body.provider,
        model=body.model,
        document=document,
        question=body.question,
        conversation_id=conversation_id,
        history=history,
        provider_api_key=provider_api_key,
        top_k=body.top_k,
        similarity_threshold=body.similarity_threshold,
        extra_document_ids=extra_doc_ids or None,
        mode=body.mode,
        workspace_id=getattr(body, "workspace_id", None),
    )


@router.post("/chat/rerun", response_model=None)
async def rerun_chat_message(
    body: RerunMessageRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    """
    Create a new conversation by rerunning a previously stored user message and generate a grounded assistant response.
    
    This endpoint validates the target document and conversation, ensures the target message exists and is a user message, copies all messages prior to the target into a new conversation, and then invokes the core generation routine to produce and persist a new assistant reply for the rerun message content.
    
    Parameters:
        body (RerunMessageRequest): Request payload containing `conversation_id`, `message_id`, `document_id`, `provider`, `model`, and optional retrieval tuning (`top_k`, `similarity_threshold`).
        request (Request): FastAPI request object for the current HTTP call.
        context (RequestContext): Authenticated request context (owner information).
        provider_api_key (str): Provider API key resolved from dependencies.
    
    Returns:
        dict: On success, a payload with keys `conversation_id`, `message_id`, `sources`, and `content` representing the new assistant response.
        OR
        Response: An API error response describing the failure (e.g., document/conversation/message not found or validation/generation errors).
    """
    # Fix: resolve the conversation first so we can scope the document load by
    # the conversation's workspace_id. Without this, rerunning a message in a
    # shared workspace fails because _load_ready_document would fall back to
    # owner_id scoping and reject documents the caller didn't personally upload.
    conversation = await fetch_one(
        "SELECT id, document_id, workspace_id FROM conversations WHERE id = ? AND owner_id = ?",
        (body.conversation_id, context.owner_id),
    )
    if not conversation:
        return api_error_response(
            request=request,
            status_code=404,
            error="Conversation not found.",
            code="CONVERSATION_NOT_FOUND",
            details={"conversation_id": body.conversation_id},
        )
    if conversation["document_id"] != body.document_id:
        return api_error_response(
            request=request,
            status_code=400,
            error="Conversation does not belong to that document.",
            code="CONVERSATION_DOCUMENT_MISMATCH",
        )

    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
        workspace_id=conversation.get("workspace_id"),
    )
    if error_response:
        return error_response
    assert document is not None

    original_messages = await fetch_all(
        """
        SELECT id, role, content, sources_json, mode
        FROM messages
        WHERE conversation_id = ? AND owner_id = ?
        ORDER BY created_at ASC
        """,
        (body.conversation_id, context.owner_id),
    )
    rerun_index = next(
        (index for index, row in enumerate(original_messages) if row["id"] == body.message_id),
        None,
    )
    if rerun_index is None:
        return api_error_response(
            request=request,
            status_code=404,
            error="Message not found.",
            code="MESSAGE_NOT_FOUND",
            details={"message_id": body.message_id},
        )
    rerun_message = original_messages[rerun_index]
    if rerun_message["role"] != "user":
        return api_error_response(
            request=request,
            status_code=400,
            error="Only user messages can be rerun.",
            code="INVALID_RERUN_TARGET",
        )

    prior_messages = original_messages[:rerun_index]
    next_conversation_id = str(uuid.uuid4())
    title = rerun_message["content"][:80] + ("..." if len(rerun_message["content"]) > 80 else "")
    # Phase 0: inherit the workspace of the document being rerun.
    # When body.workspace_id is absent, we intentionally pass an empty string
    # for ws_id_check so the OR clause is a no-op, ensuring only owner-scoped
    # documents are matched.
    ws_id_check = getattr(body, "workspace_id", None) or ""
    doc_row = await fetch_one(
        "SELECT workspace_id FROM documents WHERE id = ? AND (owner_id = ? OR workspace_id = ?)",
        (body.document_id, context.owner_id, ws_id_check),
    )
    rerun_workspace_id = (doc_row or {}).get("workspace_id")
    if not rerun_workspace_id:
        from backend.services import workspace_service as _ws

        default_ws = await _ws.ensure_default_workspace(context.owner_id)
        rerun_workspace_id = default_ws["id"]
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, title, workspace_id) VALUES (?, ?, ?, ?, ?)",
        (next_conversation_id, context.owner_id, body.document_id, title, rerun_workspace_id),
    )
    # ⚡ BOLT OPTIMIZATION:
    # Use execute_many to batch insert prior messages instead of executing a query in a loop.
    # This reduces network roundtrips and database overhead by converting N inserts into 1 bulk insert.
    params_list = [
        (
            str(uuid.uuid4()),
            context.owner_id,
            next_conversation_id,
            row["role"],
            row["content"],
            row.get("sources_json"),
            row.get("mode"),
        )
        for row in prior_messages
    ]
    if params_list:
        await execute_many(
            """
            INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params_list,
        )

    history = [
        {"role": row["role"], "content": row["content"]}
        for row in prior_messages
    ][-settings.max_conversation_history :]
    return await _generate_chat_response(
        request=request,
        context=context,
        provider=body.provider,
        model=body.model,
        document=document,
        question=rerun_message["content"],
        conversation_id=next_conversation_id,
        history=history,
        provider_api_key=provider_api_key,
        top_k=body.top_k,
        similarity_threshold=body.similarity_threshold,
    )
