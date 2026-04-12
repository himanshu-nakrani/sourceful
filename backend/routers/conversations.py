"""Conversation management endpoints."""

from __future__ import annotations


from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import TypeAdapter

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.models import Citation, ConversationListItem, ConversationListResponse, ConversationResponse, MessageResponse, UpdateConversationRequest
from backend.routers.deps import RequestContext, get_request_context

router = APIRouter()

# ⚡ BOLT OPTIMIZATION:
# Pre-compile the TypeAdapter for list[Citation] to avoid runtime overhead.
# This uses Pydantic's underlying Rust-based JSON parser (pydantic-core) directly via
# validate_json(), skipping the standard library's json.loads() and iterative dict instantiation.
# This yields a measurable performance improvement when parsing message histories with many sources.
_citation_list_adapter = TypeAdapter(list[Citation])


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    document_id: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
):
    params: tuple = (context.owner_id,)
    where = "WHERE c.owner_id = ?"
    if document_id:
        where += " AND c.document_id = ?"
        params = (context.owner_id, document_id)
    rows = await fetch_all(
        f"""
        SELECT c.id, c.document_id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
        FROM conversations c
        {where}
        ORDER BY c.updated_at DESC
        LIMIT 200
        """,
        params,
    )
    return ConversationListResponse(conversations=[ConversationListItem(**row) for row in rows])


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    conversation = await fetch_one(
        "SELECT id, document_id, title, created_at, updated_at FROM conversations WHERE id = ? AND owner_id = ?",
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
    rows = await fetch_all(
        "SELECT id, role, content, sources_json, created_at FROM messages WHERE conversation_id = ? AND owner_id = ? ORDER BY created_at ASC",
        (conversation_id, context.owner_id),
    )
    messages = []
    for row in rows:
        sources = None
        if row.get("sources_json"):
            # ⚡ BOLT OPTIMIZATION: Parse and validate in a single Rust-backed pass
            sources = _citation_list_adapter.validate_json(row["sources_json"])
        messages.append(
            MessageResponse(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                sources=sources,
                created_at=row["created_at"],
            )
        )
    return ConversationResponse(**conversation, messages=messages)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one("SELECT id FROM conversations WHERE id = ? AND owner_id = ?", (conversation_id, context.owner_id))
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Conversation not found.",
            code="CONVERSATION_NOT_FOUND",
            details={"conversation_id": conversation_id},
        )
    await execute(
        "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_id = ?",
        (body.title.strip(), conversation_id, context.owner_id),
    )
    return {"status": "updated", "conversation_id": conversation_id, "title": body.title.strip()}


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    request: Request,
    format: str = Query(default="markdown"),
    context: RequestContext = Depends(get_request_context),
):
    conversation = await fetch_one(
        "SELECT id, title, document_id, created_at, updated_at FROM conversations WHERE id = ? AND owner_id = ?",
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
    detail = await get_conversation(conversation_id, request, context)
    if isinstance(detail, JSONResponse):
        return detail
    if format == "json":
        return JSONResponse(content=detail.model_dump(mode="json"))

    lines = [f"# {detail.title}", ""]
    for message in detail.messages:
        lines.append(f"## {message.role.capitalize()}")
        lines.append(message.content)
        if message.sources:
            lines.append("")
            lines.append("Sources:")
            for source in message.sources:
                page = f" page {source.page_number}" if source.page_number else ""
                lines.append(f"- {source.chunk_id}{page}: {source.excerpt}")
        lines.append("")
    return PlainTextResponse("\n".join(lines))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await fetch_one("SELECT id FROM conversations WHERE id = ? AND owner_id = ?", (conversation_id, context.owner_id))
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Conversation not found.",
            code="CONVERSATION_NOT_FOUND",
            details={"conversation_id": conversation_id},
        )
    await execute("DELETE FROM conversations WHERE id = ? AND owner_id = ?", (conversation_id, context.owner_id))
    return {"status": "deleted", "conversation_id": conversation_id}
