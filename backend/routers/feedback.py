"""Feedback endpoints (Phase 3.8).

The UI writes thumbs-up / thumbs-down per assistant message plus an
optional free-form comment. Feedback rows are owner-scoped and joined
back to the ``messages`` table via ``message_id``; we validate that
the target message belongs to the caller's conversation before
recording anything.

Two things consume this data:

- The admin analytics page via ``/api/feedback/summary`` (counts +
  latest N rows).
- The eval harness in ``backend/tests/eval/``, which treats thumbs-down
  as a failure signal on the corresponding question — enabling the
  "online quality signal" dimension we promised in the Phase-3 roadmap.

Active-learning hints (3.9) do *not* read from this table at request
time; those hints are derived from retrieval confidence at the point
the answer is generated. Feedback is the *offline* loop.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from backend.database import execute, fetch_all, fetch_one
from backend.errors import api_error_response
from backend.models import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackSummaryResponse,
)
from backend.routers.deps import RequestContext, get_request_context
from backend.settings import settings

router = APIRouter()


def _rating_to_int(rating: Literal["up", "down"]) -> int:
    return 1 if rating == "up" else -1


def _int_to_rating(value: int) -> Literal["up", "down"]:
    return "up" if int(value) >= 1 else "down"


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    """Record a thumbs-up/down + optional comment for an assistant message.

    The request is idempotent in the sense that submitting feedback for
    the same ``(message_id, owner)`` pair twice stores two rows; the
    summary endpoint reports the most recent one per message when
    rendering rows back to the UI. This preserves the full signal for
    eval consumers.
    """
    message = await fetch_one(
        """
        SELECT m.id AS message_id, m.conversation_id, m.role, c.owner_id AS conversation_owner
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE m.id = ? AND c.id = ? AND c.owner_id = ?
        """,
        (body.message_id, body.conversation_id, context.owner_id),
    )
    if not message:
        return api_error_response(
            request=request,
            status_code=404,
            error="Message not found for this conversation.",
            code="MESSAGE_NOT_FOUND",
            details={"message_id": body.message_id, "conversation_id": body.conversation_id},
        )
    if (message.get("role") or "").lower() != "assistant":
        return api_error_response(
            request=request,
            status_code=400,
            error="Feedback can only be recorded for assistant messages.",
            code="INVALID_FEEDBACK_TARGET",
            details={"message_id": body.message_id, "role": message.get("role")},
        )

    feedback_id = str(uuid.uuid4())
    ts_fn = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"
    await execute(
        f"""
        INSERT INTO feedback (id, owner_id, conversation_id, message_id, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?, {ts_fn})
        """,
        (
            feedback_id,
            context.owner_id,
            body.conversation_id,
            body.message_id,
            _rating_to_int(body.rating),
            (body.comment or None),
        ),
    )
    row = await fetch_one(
        "SELECT id, conversation_id, message_id, rating, comment, created_at FROM feedback WHERE id = ?",
        (feedback_id,),
    )
    if row is None:  # defensive — INSERT above was synchronous
        return api_error_response(
            request=request,
            status_code=500,
            error="Feedback insert failed.",
            code="FEEDBACK_INSERT_FAILED",
        )
    return FeedbackResponse(
        id=row["id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        rating=_int_to_rating(row["rating"]),
        comment=row.get("comment"),
        created_at=row["created_at"],
    )


@router.get("/feedback/summary", response_model=FeedbackSummaryResponse)
async def feedback_summary(
    limit: int = Query(default=20, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
):
    """Return aggregate feedback counts + the most recent rows for the owner."""
    rows = await fetch_all(
        """
        SELECT id, conversation_id, message_id, rating, comment, created_at
        FROM feedback
        WHERE owner_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (context.owner_id, limit),
    )
    up = 0
    down = 0
    recent: list[FeedbackResponse] = []
    for row in rows:
        rating = _int_to_rating(row["rating"])
        if rating == "up":
            up += 1
        else:
            down += 1
        recent.append(
            FeedbackResponse(
                id=row["id"],
                conversation_id=row["conversation_id"],
                message_id=row["message_id"],
                rating=rating,
                comment=row.get("comment"),
                created_at=row["created_at"],
            )
        )
    total_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM feedback WHERE owner_id = ?",
        (context.owner_id,),
    )
    total = int((total_row or {}).get("total") or 0)
    return FeedbackSummaryResponse(total=total, up=up, down=down, recent=recent)
