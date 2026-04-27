from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request

from backend.database import fetch_all, fetch_one
from backend.models import (
    AnalyticsOverviewResponse,
    AnalyticsProviderBreakdown,
    AnalyticsRecent,
    AnalyticsTotals,
)
from backend.routers.deps import RequestContext, get_request_context, require_admin_context
from backend.services.workspace_rbac import check_workspace_role

router = APIRouter()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
async def analytics_overview(_: RequestContext = Depends(require_admin_context)):
    counts = await fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM users) AS users,
            (SELECT COUNT(*) FROM documents) AS documents,
            (SELECT COUNT(*) FROM documents WHERE status = 'ready') AS ready_documents,
            (SELECT COUNT(*) FROM conversations) AS conversations,
            (SELECT COUNT(*) FROM messages) AS messages,
            (SELECT COALESCE(SUM(chunk_count), 0) FROM documents) AS chunks
        """
    ) or {}
    provider_rows = await fetch_all(
        """
        SELECT
            provider,
            COUNT(*) AS documents,
            SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) AS ready_documents
        FROM documents
        GROUP BY provider
        ORDER BY provider ASC
        """
    )
    user_rows = await fetch_all("SELECT created_at FROM users")
    document_rows = await fetch_all("SELECT created_at FROM documents")
    message_rows = await fetch_all("SELECT role, created_at FROM messages")
    session_rows = await fetch_all(
        "SELECT user_id, created_at FROM auth_sessions WHERE revoked = ?",
        (False,),
    )

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    active_users_7d = {
        row["user_id"]
        for row in session_rows
        if _parse_dt(row.get("created_at")) and _parse_dt(row.get("created_at")) >= cutoff_7d
    }
    signups_7d = sum(
        1
        for row in user_rows
        if _parse_dt(row.get("created_at")) and _parse_dt(row.get("created_at")) >= cutoff_7d
    )
    uploads_7d = sum(
        1
        for row in document_rows
        if _parse_dt(row.get("created_at")) and _parse_dt(row.get("created_at")) >= cutoff_7d
    )
    questions_24h = sum(
        1
        for row in message_rows
        if row.get("role") == "user"
        and _parse_dt(row.get("created_at"))
        and _parse_dt(row.get("created_at")) >= cutoff_24h
    )
    sessions_24h = sum(
        1
        for row in session_rows
        if _parse_dt(row.get("created_at")) and _parse_dt(row.get("created_at")) >= cutoff_24h
    )

    return AnalyticsOverviewResponse(
        totals=AnalyticsTotals(
            users=int(counts.get("users", 0) or 0),
            active_users_7d=len(active_users_7d),
            documents=int(counts.get("documents", 0) or 0),
            ready_documents=int(counts.get("ready_documents", 0) or 0),
            conversations=int(counts.get("conversations", 0) or 0),
            messages=int(counts.get("messages", 0) or 0),
            chunks=int(counts.get("chunks", 0) or 0),
        ),
        recent=AnalyticsRecent(
            signups_7d=signups_7d,
            uploads_7d=uploads_7d,
            questions_24h=questions_24h,
            sessions_24h=sessions_24h,
        ),
        provider_breakdown=[
            AnalyticsProviderBreakdown(
                provider=str(row.get("provider", "unknown")),
                documents=int(row.get("documents", 0) or 0),
                ready_documents=int(row.get("ready_documents", 0) or 0),
            )
            for row in provider_rows
        ],
    )


@router.get("/workspaces/{workspace_id}/analytics")
async def workspace_analytics(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    """Phase 3: Workspace-specific analytics (sources, artifacts, usage)."""

    # Check workspace access (minimum viewer role)
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="viewer"
    )
    if err:
        return err

    # Get workspace stats
    stats = await fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = ?) AS total_sources,
            (SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = ? AND status = 'ready') AS ready_sources,
            (SELECT COUNT(*) FROM workspace_artifacts WHERE workspace_id = ?) AS total_artifacts,
            (SELECT COUNT(*) FROM conversations WHERE workspace_id = ?) AS conversations,
            (SELECT COUNT(*) FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = ?)) AS messages
        """,
        (workspace_id, workspace_id, workspace_id, workspace_id, workspace_id),
    ) or {}

    # Get source type breakdown
    source_type_rows = await fetch_all(
        """
        SELECT source_type, COUNT(*) AS count
        FROM workspace_sources
        WHERE workspace_id = ?
        GROUP BY source_type
        """,
        (workspace_id,),
    )

    # Get artifact type breakdown
    artifact_type_rows = await fetch_all(
        """
        SELECT artifact_type, COUNT(*) AS count
        FROM workspace_artifacts
        WHERE workspace_id = ?
        GROUP BY artifact_type
        """,
        (workspace_id,),
    )

    # Get recent activity (last 7 days)
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)

    cutoff_7d_str = cutoff_7d.strftime("%Y-%m-%d %H:%M:%S") if not settings.using_postgres else cutoff_7d.isoformat()

    messages_7d_row = await fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM messages
        WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = ?)
          AND created_at >= ?
        """,
        (workspace_id, cutoff_7d_str),
    )
    messages_7d = int((messages_7d_row or {}).get("cnt", 0) or 0)

    artifacts_7d_row = await fetch_one(
        """
        SELECT COUNT(*) AS cnt
        FROM workspace_artifacts
        WHERE workspace_id = ?
          AND created_at >= ?
        """,
        (workspace_id, cutoff_7d_str),
    )
    artifacts_7d = int((artifacts_7d_row or {}).get("cnt", 0) or 0)

    return {
        "totals": {
            "sources": int(stats.get("total_sources", 0) or 0),
            "ready_sources": int(stats.get("ready_sources", 0) or 0),
            "artifacts": int(stats.get("total_artifacts", 0) or 0),
            "conversations": int(stats.get("conversations", 0) or 0),
            "messages": int(stats.get("messages", 0) or 0),
        },
        "breakdown": {
            "sources_by_type": [
                {"type": row.get("source_type"), "count": int(row.get("count", 0) or 0)}
                for row in source_type_rows
            ],
            "artifacts_by_type": [
                {"type": row.get("artifact_type"), "count": int(row.get("count", 0) or 0)}
                for row in artifact_type_rows
            ],
        },
        "recent": {
            "messages_7d": messages_7d,
            "artifacts_7d": artifacts_7d,
        },
    }


@router.get("/workspaces/{workspace_id}/activity")
async def workspace_activity(
    workspace_id: str,
    request: Request,
    limit: int = 20,
    context: RequestContext = Depends(get_request_context),
):
    """Phase 3: Recent activity feed for a workspace (messages, artifacts, source updates)."""
    # Check workspace access (minimum viewer role)
    _, err = await check_workspace_role(
        workspace_id=workspace_id, request=request, context=context, minimum="viewer"
    )
    if err:
        return err

    activities = []

    # Get recent messages
    message_rows = await fetch_all(
        """
        SELECT
            m.id,
            m.role,
            m.content,
            m.created_at,
            c.title AS conversation_title
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE c.workspace_id = ?
        ORDER BY m.created_at DESC
        LIMIT ?
        """,
        (workspace_id, limit),
    )

    for row in message_rows:
        activities.append(
            {
                "type": "message",
                "id": row.get("id"),
                "role": row.get("role"),
                "content_preview": (row.get("content") or "")[:100],
                "conversation_title": row.get("conversation_title"),
                "created_at": row.get("created_at"),
            }
        )

    # Get recent artifacts
    artifact_rows = await fetch_all(
        """
        SELECT
            id,
            artifact_type,
            title,
            created_at
        FROM workspace_artifacts
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (workspace_id, limit),
    )

    for row in artifact_rows:
        activities.append(
            {
                "type": "artifact",
                "id": row.get("id"),
                "artifact_type": row.get("artifact_type"),
                "title": row.get("title"),
                "created_at": row.get("created_at"),
            }
        )

    # Get recent source status changes
    source_rows = await fetch_all(
        """
        SELECT
            id,
            source_type,
            source_title,
            status,
            updated_at
        FROM workspace_sources
        WHERE workspace_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (workspace_id, limit),
    )

    for row in source_rows:
        activities.append(
            {
                "type": "source_update",
                "id": row.get("id"),
                "source_type": row.get("source_type"),
                "source_title": row.get("source_title"),
                "status": row.get("status"),
                "created_at": row.get("updated_at"),
            }
        )

    # Sort all activities by created_at descending
    activities.sort(key=lambda x: _parse_dt(x.get("created_at")) or datetime.min, reverse=True)

    # Return limited results
    return {"activities": activities[:limit]}

