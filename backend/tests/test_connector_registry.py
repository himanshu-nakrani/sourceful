"""Connector registry: class registration and loading connectors from the DB.

Regression: ``ConnectorRegistry.load_for_workspace`` imported a nonexistent
``backend.database.get_workspace_connectors`` (ImportError on every call), and
``register_connector`` was used as a decorator factory by every built-in
connector but took ``(source_type, cls)``, so importing any connector module
raised TypeError and the registry was always empty.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import uuid

import pytest

from backend.connectors import registry
from backend.connectors.base import ConnectorConfig


@pytest.mark.parametrize(
    ("source_type", "module", "class_name"),
    [
        ("google_drive", "backend.connectors.google_drive", "GoogleDriveConnector"),
        ("notion", "backend.connectors.notion", "NotionConnector"),
        ("confluence", "backend.connectors.confluence", "ConfluenceConnector"),
        ("s3", "backend.connectors.s3", "S3Connector"),
    ],
)
def test_builtin_connectors_import_and_register(source_type, module, class_name):
    mod = importlib.import_module(module)
    assert registry.get_connector_class(source_type) is getattr(mod, class_name)


def test_available_types_match_schema_check_constraint():
    assert registry.available_connector_types() == ["confluence", "google_drive", "notion", "s3"]


def test_register_connector_decorator_and_direct_call():
    class _Dummy:
        def __init__(self, config):
            self.config = config

    try:
        assert registry.register_connector("dummy-a")(_Dummy) is _Dummy
        assert registry.register_connector("dummy-b", _Dummy) is _Dummy
        cfg = ConnectorConfig(id="c", source_type="dummy-a")
        assert isinstance(registry.get_connector(cfg), _Dummy)
    finally:
        registry._CONNECTOR_CLASSES.pop("dummy-a", None)
        registry._CONNECTOR_CLASSES.pop("dummy-b", None)


def test_get_connector_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown connector type"):
        registry.get_connector(ConnectorConfig(id="c", source_type="nope"))


def test_load_for_workspace_from_database():
    from backend.database import close_db, execute, init_db
    from backend.services import workspace_service

    async def insert(ws: str, cid: str, source_type: str, *, enabled: bool, creds: str | None, created: str):
        await execute(
            "INSERT INTO connectors (id, workspace_id, source_type, name, enabled, credentials_encrypted, "
            "sync_interval_minutes, last_sync_at, include_paths, exclude_paths, options, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 15, ?, ?, ?, ?, ?)",
            (
                cid, ws, source_type, cid, enabled, creds, "2026-10-01T12:00:00+00:00",
                json.dumps(["/docs/*"]), json.dumps([]), json.dumps({"space": "ENG"}), created,
            ),
        )

    async def scenario():
        await init_db()
        tag = uuid.uuid4().hex[:8]
        ws = (await workspace_service.ensure_default_workspace(f"anon:conn-{tag}"))["id"]
        other = (await workspace_service.ensure_default_workspace(f"anon:conn-other-{tag}"))["id"]
        ids = {k: f"{k}-{tag}" for k in ("notion", "s3off", "badcreds", "conf", "foreign")}
        try:
            await insert(ws, ids["notion"], "notion", enabled=True,
                         creds=json.dumps({"integration_token": "secret"}), created="2026-01-01 00:00:00")
            await insert(ws, ids["s3off"], "s3", enabled=False, creds=None, created="2026-01-02 00:00:00")
            await insert(ws, ids["badcreds"], "google_drive", enabled=True,
                         creds="gAAAA-not-json-ciphertext", created="2026-01-03 00:00:00")
            await insert(ws, ids["conf"], "confluence", enabled=True,
                         creds=json.dumps({"base_url": "https://x.atlassian.net/", "username": "u"}),
                         created="2026-01-04 00:00:00")
            await insert(other, ids["foreign"], "s3", enabled=True, creds=None, created="2026-01-05 00:00:00")

            reg = registry.ConnectorRegistry()
            loaded = await reg.load_for_workspace(ws)
            first = [(c.config.id, type(c).__name__) for c in loaded]
            notion = reg.get(ids["notion"])

            # Disable one connector and reload: it must not linger.
            await execute("UPDATE connectors SET enabled = FALSE WHERE id = ?", (ids["conf"],))
            reloaded = [c.config.id for c in await reg.load_for_workspace(ws)]
            return ids, first, notion, reloaded, [c.config.id for c in reg.all()]
        finally:
            await execute("DELETE FROM connectors WHERE id IN (?, ?, ?, ?, ?)", tuple(ids.values()))
            await execute("DELETE FROM workspaces WHERE id IN (?, ?)", (ws, other))
            await close_db()

    ids, first, notion, reloaded, all_ids = asyncio.run(scenario())
    # Enabled, decodable, this workspace only, oldest first; bad credentials skipped.
    assert first == [(ids["notion"], "NotionConnector"), (ids["conf"], "ConfluenceConnector")]
    cfg = notion.config
    assert cfg.credentials == {"integration_token": "secret"}
    assert notion._token == "secret"
    assert cfg.enabled is True and cfg.sync_interval_minutes == 15
    assert cfg.include_paths == ["/docs/*"] and cfg.exclude_paths is None
    assert cfg.options == {"space": "ENG"}
    assert cfg.last_sync_at is not None and cfg.last_sync_at.year == 2026
    assert reloaded == [ids["notion"]] and all_ids == [ids["notion"]]


def test_global_registry_is_singleton():
    assert registry.get_global_registry() is registry.get_global_registry()
