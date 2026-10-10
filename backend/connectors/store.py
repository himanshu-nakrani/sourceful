"""Persistence helpers for workspace connectors (the ``connectors`` table)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from backend.connectors.base import ConnectorConfig
from backend.database import fetch_all

logger = logging.getLogger("ragapp.connectors")


def _json_value(raw: Any, default: Any) -> Any:
    """Decode a JSON column: TEXT on SQLite, already-decoded JSONB on Postgres."""
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _timestamp(raw: Any) -> datetime | None:
    if raw is None or isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _credentials(row: dict) -> dict[str, Any] | None:
    """Decode ``credentials_encrypted``.

    The schema reserves this column for encrypted credentials, but no
    encryption layer exists yet and nothing writes the table, so the only
    readable format is a JSON object. Anything else is treated as unreadable
    (raises) rather than guessed at.
    """
    raw = row.get("credentials_encrypted")
    if raw in (None, ""):
        return None
    value = _json_value(raw, None)
    if not isinstance(value, dict):
        raise ValueError("credentials are not a readable JSON object (encrypted credentials are not supported yet)")
    return value


def row_to_config(row: dict) -> ConnectorConfig:
    """Map a ``connectors`` row to a :class:`ConnectorConfig`."""
    options = _json_value(row.get("options"), {})
    return ConnectorConfig(
        id=row["id"],
        source_type=row["source_type"],
        workspace_id=row.get("workspace_id"),
        enabled=bool(row.get("enabled")),
        credentials=_credentials(row),
        sync_interval_minutes=int(row.get("sync_interval_minutes") or 60),
        last_sync_at=_timestamp(row.get("last_sync_at")),
        last_sync_status=row.get("last_sync_status"),
        last_sync_error=row.get("last_sync_error"),
        include_paths=_json_value(row.get("include_paths"), []) or None,
        exclude_paths=_json_value(row.get("exclude_paths"), []) or None,
        options=options if isinstance(options, dict) and options else None,
    )


async def get_workspace_connectors(workspace_id: str, *, enabled_only: bool = False) -> list[ConnectorConfig]:
    """Return connector configs for a workspace, oldest first.

    Rows that cannot be decoded are logged and skipped so one bad row does not
    hide the workspace's other connectors.
    """
    where = "workspace_id = ?" + (" AND enabled = TRUE" if enabled_only else "")
    rows = await fetch_all(f"SELECT * FROM connectors WHERE {where} ORDER BY created_at ASC, id ASC", (workspace_id,))
    configs: list[ConnectorConfig] = []
    for row in rows:
        try:
            configs.append(row_to_config(dict(row)))
        except Exception as exc:  # noqa: BLE001 - isolate bad rows
            logger.warning("connector_config_invalid id=%s err=%s", row.get("id"), exc)
    return configs
