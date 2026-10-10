"""Connector registry for managing source connections."""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger("ragapp.connectors")

# Registry of connector classes by source type
_CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {}

# Built-in connector modules, imported lazily on first lookup so registration
# happens without importing optional SDKs (connectors import those in methods).
_BUILTIN_MODULES = (
    "backend.connectors.google_drive",
    "backend.connectors.notion",
    "backend.connectors.confluence",
    "backend.connectors.s3",
)
_builtins_loaded = False


def register_connector(source_type: str, cls: type[BaseConnector] | None = None) -> Any:
    """Register a connector class for ``source_type``.

    Use as a decorator (``@register_connector("notion")``, as the built-in
    connectors do) or call directly: ``register_connector("x", XConnector)``.
    """

    def _register(klass: type[BaseConnector]) -> type[BaseConnector]:
        _CONNECTOR_CLASSES[source_type] = klass
        return klass

    return _register(cls) if cls is not None else _register


def _ensure_builtin_connectors() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    for module in _BUILTIN_MODULES:
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001 - one broken connector must not hide the rest
            logger.exception("connector_module_import_failed module=%s", module)


def get_connector_class(source_type: str) -> type[BaseConnector] | None:
    """Get connector class by source type."""
    _ensure_builtin_connectors()
    return _CONNECTOR_CLASSES.get(source_type)


def available_connector_types() -> list[str]:
    """Source types with a registered connector class."""
    _ensure_builtin_connectors()
    return sorted(_CONNECTOR_CLASSES)


def get_connector(config: ConnectorConfig) -> BaseConnector:
    """Instantiate a connector from config."""
    cls = get_connector_class(config.source_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {config.source_type}")
    return cls(config)


class ConnectorRegistry:
    """Registry for connector instances (per-workspace)."""

    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    async def load_for_workspace(self, workspace_id: str, db_session: Any = None) -> list[BaseConnector]:
        """Load all enabled connectors for a workspace from the database.

        Reloading replaces the workspace's previously loaded connectors, so
        disabled or deleted ones do not linger. ``db_session`` is accepted for
        backwards compatibility and ignored (the app uses a module-level pool).
        """
        from backend.connectors.store import get_workspace_connectors

        configs = await get_workspace_connectors(workspace_id, enabled_only=True)
        for connector_id, existing in list(self._connectors.items()):
            if existing.config.workspace_id == workspace_id:
                del self._connectors[connector_id]

        connectors: list[BaseConnector] = []
        for cfg in configs:
            try:
                conn = get_connector(cfg)
            except Exception as exc:  # noqa: BLE001 - log, keep loading the rest
                logger.warning("connector_load_failed id=%s type=%s err=%s", cfg.id, cfg.source_type, exc)
                continue
            self._connectors[cfg.id] = conn
            connectors.append(conn)
        return connectors

    def get(self, connector_id: str) -> BaseConnector | None:
        """Get loaded connector by ID."""
        return self._connectors.get(connector_id)

    def all(self) -> list[BaseConnector]:
        """Get all loaded connectors."""
        return list(self._connectors.values())


# Global registry instance
_global_registry = ConnectorRegistry()


def get_global_registry() -> ConnectorRegistry:
    """Get the global connector registry."""
    return _global_registry
