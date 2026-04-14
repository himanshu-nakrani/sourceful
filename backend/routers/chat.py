"""Chat endpoints with grounded answers and rerun support."""

from __future__ import annotations

import logging
import uuid
import asyncio

from fastapi import APIRouter, Depends, Request
from openai import APIError
from pydantic import TypeAdapter

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.metrics import metrics
from backend.models import ChatRequest, Citation, RerunMessageRequest
from backend.routers.deps import RequestContext, get_request_context, require_provider_api_key
from backend.services.embeddings import embed_query
from backend.services.llm import build_rag_prompt, create_openai_text, gemini_text
from backend.services.vectorstore import query_similar # , query_vertex_search
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
):
    trimmed_question = question.strip()

    # if provider == "vertex_search":
    #     if not settings.vertex_search_configured:
    #         return api_error_response(
    #             request=request,
    #             status_code=503,
    #             error="Vertex AI Search is not configured on the server.",
    #             code="VERTEX_SEARCH_NOT_CONFIGURED",
    #         )
    #     citations = await query_vertex_search(
    #         document["id"],
    #         trimmed_question,
    #         settings.rag_top_k,
    #     )
    # else:
    # Always use vector search since vertex_search is disabled
    try:
        question_embedding = await embed_query(
            provider,
            provider_api_key,
            document["embedding_model"],
            trimmed_question,
        )
    except Exception as exc:
        metrics.inc("chat_stream_failures_total", reason="embedding_failed")
        return api_error_response(
            request=request,
            status_code=502,
            error=f"Query embedding failed: {exc}",
            code="QUERY_EMBEDDING_FAILED",
        )

    citations = await query_similar(
        document["id"],
        context.owner_id,
        question_embedding,
        settings.rag_top_k,
    )
    if not citations:
        return api_error_response(
            request=request,
            status_code=400,
            error="No matching context found. Try re-indexing the document.",
            code="NO_MATCHING_CONTEXT",
        )
    metrics.observe("chat_citations_count", float(len(citations)), provider=provider)

    user_message_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', ?)",
        (user_message_id, context.owner_id, conversation_id, trimmed_question),
    )

    prompt = build_rag_prompt(citations, trimmed_question, history=history)
    assistant_message_id = str(uuid.uuid4())

    # ⚡ BOLT OPTIMIZATION: Serialize citations to JSON using Pydantic's TypeAdapter directly
    # This avoids intermediate dict creation and Python's json.dumps() overhead.
    source_payload = [
        Citation(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            excerpt=citation.excerpt,
            score=citation.score,
            page_number=citation.page_number,
        )
        for citation in citations
    ]
    source_payload_json = _citation_list_adapter.dump_json(source_payload).decode("utf-8")

    try:
        if provider == "openai":
            answer = await create_openai_text(provider_api_key, model.strip(), prompt)
        # elif provider == "vertex_search":
        #     loop = asyncio.get_running_loop()
        #     answer = await loop.run_in_executor(
        #         None,
        #         gemini_text,
        #         provider_api_key,
        #         model.strip(),
        #         prompt,
        #     )
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

    await execute(
        """
        INSERT INTO messages (id, owner_id, conversation_id, role, content, sources_json)
        VALUES (?, ?, ?, 'assistant', ?, ?)
        """,
        (assistant_message_id, context.owner_id, conversation_id, answer, source_payload_json),
    )
    await execute(
        f"UPDATE conversations SET updated_at = {TIMESTAMP_SQL} WHERE id = ? AND owner_id = ?",
        (conversation_id, context.owner_id),
    )

    return {
        "conversation_id": conversation_id,
        "message_id": assistant_message_id,
        "sources": source_payload,
        "content": answer,
    }


@router.post("/chat", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    document, error_response = await _load_ready_document(
        request=request,
        context=context,
        document_id=body.document_id,
        provider=body.provider,
    )
    if error_response:
        return error_response
    assert document is not None

    conversation_id = body.conversation_id
    if conversation_id:
        conversation = await fetch_one(
            "SELECT id, document_id FROM conversations WHERE id = ? AND owner_id = ?",
            (conversation_id, context.owner_id),
        )
        if not conversation:
            return api_error_response(
                request=request,
                status_code=404,
                error="Conversation not found.",
                code="CONVERSATION_NOT_FOUND",
                details={"conversation_id": conversation_id},
            )
        if conversation["document_id"] != body.document_id:
            return api_error_response(
                request=request,
                status_code=400,
                error="Conversation does not belong to that document.",
                code="CONVERSATION_DOCUMENT_MISMATCH",
            )
    else:
        conversation_id = str(uuid.uuid4())
        title = body.question.strip()[:80] + ("..." if len(body.question.strip()) > 80 else "")
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, ?, ?)",
            (conversation_id, context.owner_id, body.document_id, title),
        )

    history_rows = await fetch_all(
        "SELECT role, content FROM messages WHERE conversation_id = ? AND owner_id = ? ORDER BY created_at ASC",
        (conversation_id, context.owner_id),
    )
    history = [
        {"role": row["role"], "content": row["content"]}
        for row in history_rows
    ][-settings.max_conversation_history :]
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
    )


@router.post("/chat/rerun", response_model=None)
async def rerun_chat_message(
    body: RerunMessageRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
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
    )
