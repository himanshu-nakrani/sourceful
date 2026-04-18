"""Chat endpoints with grounded answers and rerun support."""

from __future__ import annotations

import json
import logging
import uuid
import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import APIError
from pydantic import TypeAdapter

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.metrics import metrics
from backend.models import ChatRequest, Citation, RerunMessageRequest
from backend.routers.deps import RequestContext, get_request_context, require_provider_api_key
from backend.services import tracing
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


async def _load_ready_document(
    *,
    request: Request,
    context: RequestContext,
    document_id: str,
    provider: str,
):
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
        for tq in transformed:
            try:
                emb = await embed_query(provider, provider_api_key, embedding_model, tq.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("transform_embed_failed kind=%s err=%s", tq.kind, exc)
                continue
            lanes.append((tq.kind, emb))
    return lanes, [tq.kind for tq in transformed]


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
):
    """Embed the question and run the retrieval pipeline. Returns (chunks, stages, error_response)."""
    if extra_document_ids:
        all_doc_ids = [document["id"]] + list(extra_document_ids)
        placeholders = ", ".join(["?"] * len(all_doc_ids))
        rows = await fetch_all(
            f"SELECT id, embedding_model FROM documents WHERE owner_id = ? AND id IN ({placeholders})",
            (context.owner_id, *all_doc_ids),
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
    return [
        Citation(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            excerpt=c.excerpt,
            score=c.score,
            page_number=c.page_number,
        )
        for c in chunks
    ]


async def _save_turn(
    *,
    context: RequestContext,
    conversation_id: str,
    user_question: str,
    assistant_message_id: str,
    answer: str,
    sources_json: str,
) -> None:
    user_message_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', ?)",
        (user_message_id, context.owner_id, conversation_id, user_question),
    )
    await execute(
        """
        INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json)
        VALUES (?, ?, ?, 'assistant', ?, ?)
        """,
        (assistant_message_id, context.owner_id, conversation_id, answer, sources_json),
    )
    await execute(
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
        )
        if err is not None:
            return err

        source_payload = _citations_from_chunks(chunks)
        source_payload_json = _citation_list_adapter.dump_json(source_payload).decode("utf-8")
        prompt = build_rag_prompt(chunks, trimmed_question, history=history)
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
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


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

            prompt = build_rag_prompt(chunks, trimmed_question, history=history)
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
                        queue: asyncio.Queue[str | None] = asyncio.Queue()

                        def _run_gemini():
                            try:
                                for piece in stream_gemini_text(provider_api_key, model.strip(), prompt):
                                    loop.call_soon_threadsafe(queue.put_nowait, piece)
                            finally:
                                loop.call_soon_threadsafe(queue.put_nowait, None)

                        loop.run_in_executor(None, _run_gemini)
                        while True:
                            piece = await queue.get()
                            if piece is None:
                                break
                            collected.append(piece)
                            yield _sse_event("token", {"delta": piece})
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
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, title, document_ids_json) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, context.owner_id, body.document_id, title, doc_ids_json),
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
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
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
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
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
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
    )
    if error_response:
        return error_response
    assert document is not None

    conversation = await fetch_one(
        "SELECT id, document_id FROM conversations WHERE id = ? AND owner_id = ?",
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

    original_messages = await fetch_all(
        """
        SELECT id, role, content, sources_json
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
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, ?, ?)",
        (next_conversation_id, context.owner_id, body.document_id, title),
    )
    for row in prior_messages:
        await execute(
            """
            INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                context.owner_id,
                next_conversation_id,
                row["role"],
                row["content"],
                row.get("sources_json"),
            ),
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
