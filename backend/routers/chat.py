"""Chat endpoint with SSE streaming and structured citations."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from openai import APIError
from sse_starlette.sse import EventSourceResponse

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.metrics import metrics
from backend.models import ChatRequest, Citation
from backend.routers.deps import RequestContext, get_request_context, require_provider_api_key
from backend.services.embeddings import embed_query
from backend.services.llm import build_rag_prompt, create_openai_text, gemini_text
from backend.services.vectorstore import query_similar
from backend.settings import settings

logger = logging.getLogger("ragapp.chat")
TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"
router = APIRouter()


@router.post("/chat", response_model=None)
async def chat(
    body: ChatRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(require_provider_api_key),
):
    document = await fetch_one(
        "SELECT * FROM documents WHERE id = ? AND owner_id = ?",
        (body.document_id.strip(), context.owner_id),
    )
    if not document:
        return api_error_response(
            request=request,
            status_code=404,
            error="Unknown document_id.",
            code="DOCUMENT_NOT_FOUND",
            details={"document_id": body.document_id.strip()},
        )
    if document["status"] != "ready":
        return api_error_response(
            request=request,
            status_code=400,
            error=f"Document is not ready. Current status: {document['status']}",
            code="DOCUMENT_NOT_READY",
            details={"status": document["status"]},
        )
    if document["provider"] != body.provider:
        return api_error_response(
            request=request,
            status_code=400,
            error="Provider does not match the indexed document.",
            code="PROVIDER_MISMATCH",
        )

    question = body.question.strip()
    try:
        question_embedding = await embed_query(body.provider, provider_api_key, document["embedding_model"], question)
    except Exception as exc:
        metrics.inc("chat_stream_failures_total", reason="embedding_failed")
        return api_error_response(
            request=request,
            status_code=502,
            error=f"Query embedding failed: {exc}",
            code="QUERY_EMBEDDING_FAILED",
        )

    citations = await query_similar(body.document_id, context.owner_id, question_embedding, settings.rag_top_k)
    if not citations:
        return api_error_response(
            request=request,
            status_code=400,
            error="No matching context found. Try re-indexing the document.",
            code="NO_MATCHING_CONTEXT",
        )
    metrics.observe("chat_citations_count", float(len(citations)), provider=body.provider)

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
        title = question[:80] + ("..." if len(question) > 80 else "")
        await execute(
            "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, ?, ?)",
            (conversation_id, context.owner_id, body.document_id, title),
        )

    history_rows = await fetch_all(
        "SELECT role, content FROM messages WHERE conversation_id = ? AND owner_id = ? ORDER BY created_at ASC",
        (conversation_id, context.owner_id),
    )
    history = [{"role": row["role"], "content": row["content"]} for row in history_rows][-settings.max_conversation_history:]

    user_message_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO messages (id, owner_id, conversation_id, role, content) VALUES (?, ?, ?, 'user', ?)",
        (user_message_id, context.owner_id, conversation_id, question),
    )

    prompt = build_rag_prompt(citations, question, history=history)
    assistant_message_id = str(uuid.uuid4())
    source_payload = [
        Citation(
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            excerpt=citation.excerpt,
            score=citation.score,
            page_number=citation.page_number,
        ).model_dump(mode="json")
        for citation in citations
    ]

    try:
        if body.provider == "openai":
            answer = await create_openai_text(provider_api_key, body.model.strip(), prompt)
        else:
            loop = asyncio.get_running_loop()
            answer = await loop.run_in_executor(None, gemini_text, provider_api_key, body.model.strip(), prompt)
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
        (assistant_message_id, context.owner_id, conversation_id, answer, json.dumps(source_payload)),
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
