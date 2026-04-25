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
    existing = await get_artifact(artifact_id, workspace_id)
    if not existing:
        return False
    await execute(
        "DELETE FROM workspace_artifacts WHERE id = ? AND workspace_id = ?",
        (artifact_id, workspace_id),
    )
    return True
