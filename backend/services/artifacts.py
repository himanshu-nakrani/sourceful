"""Phase 2: workspace artifacts (user notes + saved assistant answers).

Artifacts are durable knowledge that accumulates inside a workspace alongside
the indexed sources. They are NOT first-class retrieval evidence — uploaded
sources remain primary — but they can be surfaced by the chat composer to
augment future answers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.database import execute, fetch_all, fetch_one
from backend.settings import settings


TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"

ARTIFACT_TYPES = {
    "user_note",
    "saved_answer",
    "saved_brief",
    "extraction_result",
}


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """Serialize a database row to an artifact dict.

    Parses the metadata_json field and returns a clean artifact representation.

    Args:
        row: The database row dict.

    Returns:
        A serialized artifact dict with parsed metadata.
    """
    metadata: dict[str, Any] = {}
    raw_meta = row.get("metadata_json")
    if raw_meta:
        if isinstance(raw_meta, str):
            try:
                metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = raw_meta
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "artifact_type": row["artifact_type"],
        "title": row["title"],
        "content": row["content"],
        "metadata": metadata,
        "source_message_id": row.get("source_message_id"),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_artifacts(
    workspace_id: str,
    *,
    artifact_type: str | None = None,
) -> list[dict[str, Any]]:
    """List artifacts in a workspace, optionally filtered by type.

    Args:
        workspace_id: The workspace ID.
        artifact_type: Optional artifact type to filter by.

    Returns:
        A list of serialized artifact dicts, ordered by updated_at DESC.

    Raises:
        ValueError: If artifact_type is not a valid ARTIFACT_TYPES value.
    """
    if artifact_type and artifact_type not in ARTIFACT_TYPES:
        raise ValueError(f"Invalid artifact_type: {artifact_type}")
    if artifact_type:
        rows = await fetch_all(
            """
            SELECT * FROM workspace_artifacts
            WHERE workspace_id = ? AND artifact_type = ?
            ORDER BY updated_at DESC
            """,
            (workspace_id, artifact_type),
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM workspace_artifacts WHERE workspace_id = ? ORDER BY updated_at DESC",
            (workspace_id,),
        )
    return [_serialize(r) for r in rows]


async def get_artifact(artifact_id: str, workspace_id: str) -> dict[str, Any] | None:
    """Retrieve a single artifact by ID.

    Args:
        artifact_id: The artifact ID.
        workspace_id: The workspace ID (for scoping).

    Returns:
        The serialized artifact dict, or None if not found.
    """
    row = await fetch_one(
        "SELECT * FROM workspace_artifacts WHERE id = ? AND workspace_id = ?",
        (artifact_id, workspace_id),
    )
    return _serialize(row) if row else None


async def create_artifact(
    workspace_id: str,
    *,
    artifact_type: str,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    source_message_id: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Create a new artifact in a workspace.

    Args:
        workspace_id: The workspace ID.
        artifact_type: The type of artifact (must be in ARTIFACT_TYPES).
        title: The artifact title.
        content: The artifact content.
        metadata: Optional metadata dict.
        source_message_id: Optional source message ID for provenance.
        created_by: Optional creator ID.

    Returns:
        The created artifact dict.

    Raises:
        ValueError: If artifact_type is invalid, title is empty, or content is empty.
    """
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError(f"Invalid artifact_type: {artifact_type}")
    title_clean = title.strip()
    if not title_clean:
        raise ValueError("Artifact title cannot be empty.")
    if not content or not content.strip():
        raise ValueError("Artifact content cannot be empty.")
    artifact_id = str(uuid.uuid4())
    meta_payload = json.dumps(metadata) if metadata else None
    await execute(
        f"""
        INSERT INTO workspace_artifacts (
            id, workspace_id, artifact_type, title, content, metadata_json,
            source_message_id, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, {TIMESTAMP_SQL}, {TIMESTAMP_SQL})
        """,
        (
            artifact_id,
            workspace_id,
            artifact_type,
            title_clean,
            content,
            meta_payload,
            source_message_id,
            created_by,
        ),
    )
    created = await get_artifact(artifact_id, workspace_id)
    assert created is not None
    return created


async def update_artifact(
    artifact_id: str,
    workspace_id: str,
    *,
    title: str | None = None,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update an existing artifact.

    Only updates fields that are provided (partial update).

    Args:
        artifact_id: The artifact ID.
        workspace_id: The workspace ID.
        title: Optional new title.
        content: Optional new content.
        metadata: Optional new metadata dict.

    Returns:
        The updated artifact dict, or None if not found.

    Raises:
        ValueError: If title or content is provided but empty.
    """
    existing = await get_artifact(artifact_id, workspace_id)
    if not existing:
        return None
    sets: list[str] = []
    params: list[Any] = []
    if title is not None:
        clean = title.strip()
        if not clean:
            raise ValueError("Artifact title cannot be empty.")
        sets.append("title = ?")
        params.append(clean)
    if content is not None:
        if not content.strip():
            raise ValueError("Artifact content cannot be empty.")
        sets.append("content = ?")
        params.append(content)
    if metadata is not None:
        sets.append("metadata_json = ?")
        params.append(json.dumps(metadata))
    if not sets:
        return existing
    sets.append(f"updated_at = {TIMESTAMP_SQL}")
    params.extend([artifact_id, workspace_id])
    await execute(
        f"UPDATE workspace_artifacts SET {', '.join(sets)} WHERE id = ? AND workspace_id = ?",
        tuple(params),
    )
    return await get_artifact(artifact_id, workspace_id)


async def delete_artifact(artifact_id: str, workspace_id: str) -> bool:
    """Delete an artifact from a workspace.

    Args:
        artifact_id: The artifact ID.
        workspace_id: The workspace ID.

    Returns:
        True if the artifact was deleted, False if it didn't exist.
    """
    existing = await get_artifact(artifact_id, workspace_id)
    if not existing:
        return False
    await execute(
        "DELETE FROM workspace_artifacts WHERE id = ? AND workspace_id = ?",
        (artifact_id, workspace_id),
    )
    return True
