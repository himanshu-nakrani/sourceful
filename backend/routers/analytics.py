from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from backend.database import fetch_all, fetch_one
from backend.models import (
    AnalyticsOverviewResponse,
    AnalyticsProviderBreakdown,
    AnalyticsRecent,
    AnalyticsTotals,
)
from backend.routers.deps import require_admin_context

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
async def analytics_overview(_: object = Depends(require_admin_context)):
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
