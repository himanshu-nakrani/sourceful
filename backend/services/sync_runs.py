"""Phase 3: durable sync history for URL-backed workspace sources."""

from __future__ import annotations

import uuid
from typing import Any

from backend.database import execute, fetch_all, fetch_one
from backend.settings import settings


TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a database row to a sync run dict.

    Args:
        row: The database row dict.

    Returns:
        A serialized sync run dict.
    """
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "source_id": row["source_id"],
        "status": row["status"],
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "error_message": row.get("error_message"),
        "checksum": row.get("checksum"),
    }


async def start_run(*, workspace_id: str, source_id: str) -> str:
    """Start a new sync run for a workspace source.

    Creates a sync run record and updates the source's last_sync_status.

    Args:
        workspace_id: The workspace ID.
        source_id: The source ID to sync.

    Returns:
        The new run ID.
    """
    run_id = str(uuid.uuid4())
    await execute(
        f"""
        INSERT INTO workspace_source_sync_runs
            (id, workspace_id, source_id, started_at, status)
        VALUES (?, ?, ?, {TIMESTAMP_SQL}, 'running')
        """,
        (run_id, workspace_id, source_id),
    )
    # Mirror the latest status onto the source for quick listing.
    await execute(
        f"UPDATE workspace_sources SET last_sync_status = 'running', last_sync_error = NULL, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
        (source_id,),
    )
    return run_id


async def finish_run(
    *,
    run_id: str,
    source_id: str,
    status: str,
    error_message: str | None = None,
    checksum: str | None = None,
) -> None:
    """Complete a sync run with success or error status.

    Updates the run record and mirrors the status to the source.

    Args:
        run_id: The run ID to complete.
        source_id: The source ID to update.
        status: Either 'success' or 'error'.
        error_message: Optional error message if status is 'error'.
        checksum: Optional content checksum for change detection.

    Raises:
        ValueError: If status is not 'success' or 'error'.
    """
    if status not in {"success", "error"}:
        raise ValueError(f"Invalid run status: {status}")
    await execute(
        f"""
        UPDATE workspace_source_sync_runs
        SET status = ?, completed_at = {TIMESTAMP_SQL}, error_message = ?, checksum = ?
        WHERE id = ?
        """,
        (status, error_message, checksum, run_id),
    )
    await execute(
        f"UPDATE workspace_sources SET last_sync_status = ?, last_sync_error = ?, updated_at = {TIMESTAMP_SQL} WHERE id = ?",
        (status, error_message, source_id),
    )


async def list_runs(*, workspace_id: str, source_id: str, limit: int = 25) -> list[dict[str, Any]]:
    """List sync runs for a workspace source.

    Args:
        workspace_id: The workspace ID.
        source_id: The source ID.
        limit: Maximum number of runs to return.

    Returns:
        A list of serialized sync run dicts, ordered by started_at DESC.
    """
    rows = await fetch_all(
        f"""
        SELECT * FROM workspace_source_sync_runs
        WHERE workspace_id = ? AND source_id = ?
        ORDER BY started_at DESC
        LIMIT {int(limit)}
        """,
        (workspace_id, source_id),
    )
    return [_serialize(r) for r in rows]


async def latest_run(*, workspace_id: str, source_id: str) -> dict[str, Any] | None:
    """Get the most recent sync run for a workspace source.

    Args:
        workspace_id: The workspace ID.
        source_id: The source ID.

    Returns:
        The serialized sync run dict, or None if no runs exist.
    """
    row = await fetch_one(
        """
        SELECT * FROM workspace_source_sync_runs
        WHERE workspace_id = ? AND source_id = ?
        ORDER BY started_at DESC LIMIT 1
        """,
        (workspace_id, source_id),
    )
    return _serialize(row) if row else None
