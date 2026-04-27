"""Workspace service: CRUD + default-workspace + source helpers.

This service is the single source of truth for the knowledge-workspace
Phase 0 and Phase 1 data operations. It purposefully uses the same
``fetch_one`` / ``fetch_all`` / ``execute`` helpers as the rest of the
backend so SQLite and Postgres stay in lockstep.

Ownership is scoped via ``owner_scope`` — the same ``owner_id`` string
used across ``documents``/``conversations`` (``user:<uuid>`` or
``anon:<session>``). The legacy ``workspaces.owner_id`` column (FK to
``users.id``) is preserved for historical rows but is not used for new
anonymous scopes.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from backend.database import execute, fetch_all, fetch_one
from backend.settings import settings


TIMESTAMP_SQL = "NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP"

VISIBILITY_VALUES = {"private", "shared"}
SOURCE_TYPES = {"file", "url", "note"}
SOURCE_STATUSES = {"queued", "processing", "ready", "error"}


def _slugify(name: str) -> str:
    base = re.sub(r"[^\w\s-]", "", name.lower())
    base = re.sub(r"[-\s]+", "-", base).strip("-") or "workspace"
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"1", "true", "t", "yes"}
    return False


def _serialize_workspace(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row.get("slug"),
        "description": row.get("description"),
        "visibility": row.get("visibility") or "private",
        "archived": _to_bool(row.get("archived")),
        "is_default": _to_bool(row.get("is_default")),
        "owner_scope": row.get("owner_scope"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def list_workspaces(owner_scope: str, *, include_archived: bool = False) -> list[dict[str, Any]]:
    where = "WHERE owner_scope = ?"
    params: tuple = (owner_scope,)
    if not include_archived:
        where += " AND (archived = 0 OR archived IS NULL OR archived = FALSE)" if not settings.using_postgres else " AND archived = FALSE"
    rows = await fetch_all(
        f"""
        SELECT id, name, slug, description, visibility, archived, is_default,
               owner_scope, created_at, updated_at
        FROM workspaces
        {where}
        ORDER BY is_default DESC, updated_at DESC
        """,
        params,
    )
    return [_serialize_workspace(r) for r in rows]


async def get_workspace(workspace_id: str, owner_scope: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT id, name, slug, description, visibility, archived, is_default,
               owner_scope, created_at, updated_at
        FROM workspaces
        WHERE id = ? AND owner_scope = ?
        """,
        (workspace_id, owner_scope),
    )
    return _serialize_workspace(row) if row else None


async def get_default_workspace(owner_scope: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT id, name, slug, description, visibility, archived, is_default,
               owner_scope, created_at, updated_at
        FROM workspaces
        WHERE owner_scope = ?
          AND (is_default = 1 OR is_default = TRUE)
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (owner_scope,),
    )
    return _serialize_workspace(row) if row else None


async def ensure_default_workspace(owner_scope: str) -> dict[str, Any]:
    """Return the caller's default workspace, creating it if missing.

    Idempotent: concurrent calls are safe because we check-then-create and the
    workspace owner_scope is unique-enough under the default flag.
    """
    existing = await get_default_workspace(owner_scope)
    if existing:
        return existing
    return await create_workspace(
        owner_scope,
        name="Personal workspace",
        description="Default workspace",
        is_default=True,
    )


async def create_workspace(
    owner_scope: str,
    *,
    name: str,
    description: str | None = None,
    visibility: str = "private",
    is_default: bool = False,
) -> dict[str, Any]:
    if visibility not in VISIBILITY_VALUES:
        raise ValueError(f"Invalid visibility: {visibility}")
    name = name.strip()
    if not name:
        raise ValueError("Workspace name cannot be empty.")
    workspace_id = str(uuid.uuid4())
    slug = _slugify(name)
    legacy_owner = owner_scope.split(":", 1)[1] if owner_scope.startswith("user:") else None
    archived_val = False if settings.using_postgres else 0
    default_val = (True if settings.using_postgres else 1) if is_default else (False if settings.using_postgres else 0)

    # Workspaces.owner_id historically FK-references users(id). For anonymous
    # scopes we cannot satisfy the FK, so we insert NULL there and rely on
    # owner_scope for ownership lookups.
    await execute(
        f"""
        INSERT INTO workspaces (
            id, name, slug, owner_id, owner_scope, description, visibility,
            archived, is_default, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {TIMESTAMP_SQL}, {TIMESTAMP_SQL})
        """,
        (
            workspace_id,
            name,
            slug,
            legacy_owner,
            owner_scope,
            description,
            visibility,
            archived_val,
            default_val,
        ),
    )
    created = await get_workspace(workspace_id, owner_scope)
    assert created is not None, "Workspace insert did not persist"
    return created


async def update_workspace(
    workspace_id: str,
    owner_scope: str,
    *,
    name: str | None = None,
    description: str | None = None,
    visibility: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any] | None:
    existing = await get_workspace(workspace_id, owner_scope)
    if not existing:
        return None
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValueError("Workspace name cannot be empty.")
        sets.append("name = ?")
        params.append(clean)
    if description is not None:
        sets.append("description = ?")
        params.append(description)
    if visibility is not None:
        if visibility not in VISIBILITY_VALUES:
            raise ValueError(f"Invalid visibility: {visibility}")
        sets.append("visibility = ?")
        params.append(visibility)
    if archived is not None:
        sets.append("archived = ?")
        params.append((True if settings.using_postgres else 1) if archived else (False if settings.using_postgres else 0))
    if not sets:
        return existing
    sets.append(f"updated_at = {TIMESTAMP_SQL}")
    params.extend([workspace_id, owner_scope])
    await execute(
        f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ? AND owner_scope = ?",
        tuple(params),
    )
    return await get_workspace(workspace_id, owner_scope)


# ---------- Sources ---------------------------------------------------------


def _serialize_source(row: dict[str, Any]) -> dict[str, Any]:
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
        "source_type": row.get("source_type") or "file",
        "document_id": row.get("document_id"),
        "source_title": row.get("source_title"),
        "source_url": row.get("source_url"),
        "mime_type": row.get("mime_type"),
        "status": row.get("status") or "queued",
        "last_fetched_at": row.get("last_fetched_at"),
        "metadata": metadata,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        # Phase 3 sync columns. Older rows pre-dating migration v14 may not
        # have these populated; ``.get`` keeps the serializer safe.
        "last_sync_status": row.get("last_sync_status"),
        "last_sync_error": row.get("last_sync_error"),
        "next_sync_at": row.get("next_sync_at"),
    }


async def list_sources(workspace_id: str) -> list[dict[str, Any]]:
    rows = await fetch_all(
        """
        SELECT ws.id, ws.workspace_id, ws.source_type, ws.document_id, ws.source_title,
               ws.source_url, ws.mime_type,
               COALESCE(d.status, ws.status) AS status,
               ws.last_fetched_at, ws.metadata_json, ws.created_at, ws.updated_at,
               ws.last_sync_status, ws.last_sync_error, ws.next_sync_at
        FROM workspace_sources ws
        LEFT JOIN documents d ON d.id = ws.document_id
        WHERE ws.workspace_id = ?
        ORDER BY ws.created_at DESC
        """,
        (workspace_id,),
    )
    return [_serialize_source(r) for r in rows]


async def get_source(source_id: str, workspace_id: str) -> dict[str, Any] | None:
    row = await fetch_one(
        """
        SELECT ws.id, ws.workspace_id, ws.source_type, ws.document_id, ws.source_title,
               ws.source_url, ws.mime_type,
               COALESCE(d.status, ws.status) AS status,
               ws.last_fetched_at, ws.metadata_json, ws.created_at, ws.updated_at,
               ws.last_sync_status, ws.last_sync_error, ws.next_sync_at
        FROM workspace_sources ws
        LEFT JOIN documents d ON d.id = ws.document_id
        WHERE ws.id = ? AND ws.workspace_id = ?
        """,
        (source_id, workspace_id),
    )
    return _serialize_source(row) if row else None


async def create_source(
    workspace_id: str,
    *,
    source_type: str,
    source_title: str,
    document_id: str | None = None,
    source_url: str | None = None,
    mime_type: str | None = None,
    status: str = "queued",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")
    if status not in SOURCE_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    title = source_title.strip()
    if not title:
        raise ValueError("Source title cannot be empty.")
    source_id = str(uuid.uuid4())
    meta_payload = json.dumps(metadata) if metadata else None
    await execute(
        f"""
        INSERT INTO workspace_sources (
            id, workspace_id, source_type, document_id, source_title, source_url,
            mime_type, status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, {TIMESTAMP_SQL}, {TIMESTAMP_SQL})
        """,
        (
            source_id,
            workspace_id,
            source_type,
            document_id,
            title,
            source_url,
            mime_type,
            status,
            meta_payload,
        ),
    )
    created = await get_source(source_id, workspace_id)
    assert created is not None, "Source insert did not persist"
    return created


async def upsert_source_for_document(
    workspace_id: str,
    *,
    document_id: str,
    source_title: str,
    mime_type: str | None,
    status: str = "queued",
) -> dict[str, Any]:
    """Create (or update title/status of) a workspace_source row bound to a document.

    Used during ingest to link a document to the caller's default workspace as a
    first-class source.
    """
    existing = await fetch_one(
        "SELECT id FROM workspace_sources WHERE document_id = ? AND workspace_id = ?",
        (document_id, workspace_id),
    )
    if existing:
        await execute(
            f"""
            UPDATE workspace_sources
            SET source_title = ?, mime_type = ?, status = ?, updated_at = {TIMESTAMP_SQL}
            WHERE id = ?
            """,
            (source_title, mime_type, status, existing["id"]),
        )
        result = await get_source(existing["id"], workspace_id)
        assert result is not None
        return result
    return await create_source(
        workspace_id,
        source_type="file",
        source_title=source_title,
        document_id=document_id,
        mime_type=mime_type,
        status=status,
    )
