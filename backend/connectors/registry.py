"""Connector registry for managing source connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.connectors.base import BaseConnector, ConnectorConfig

# Registry of connector classes by source type
_CONNECTOR_CLASSES: dict[str, type["BaseConnector"]] = {}


def register_connector(source_type: str, cls: type["BaseConnector"]) -> type["BaseConnector"]:
    """Decorator to register a connector class."""
    _CONNECTOR_CLASSES[source_type] = cls
    return cls


def get_connector_class(source_type: str) -> type["BaseConnector"] | None:
    """Get connector class by source type."""
    return _CONNECTOR_CLASSES.get(source_type)


def get_connector(config: "ConnectorConfig") -> "BaseConnector":
    """Instantiate a connector from config."""
    cls = get_connector_class(config.source_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {config.source_type}")
    return cls(config)


class ConnectorRegistry:
    """Registry for connector instances (per-workspace)."""

    def __init__(self):
        self._connectors: dict[str, "BaseConnector"] = {}

    async def load_for_workspace(
        self, workspace_id: str, db_session: Any
    ) -> list["BaseConnector"]:
        """Load all enabled connectors for a workspace from DB."""
        # Import here to avoid circular imports
        from backend.database import get_workspace_connectors

        configs = await get_workspace_connectors(db_session, workspace_id)
        connectors = []
        for cfg in configs:
            if cfg.enabled:
                try:
                    conn = get_connector(cfg)
                    self._connectors[cfg.id] = conn
                    connectors.append(conn)
                except ValueError as e:
                    # Log but don't fail entire load
                    print(f"Failed to load connector {cfg.id}: {e}")
        return connectors

    def get(self, connector_id: str) -> "BaseConnector" | None:
        """Get loaded connector by ID."""
        return self._connectors.get(connector_id)

    def all(self) -> list["BaseConnector"]:
        """Get all loaded connectors."""
        return list(self._connectors.values())


# Global registry instance
_global_registry = ConnectorRegistry()


def get_global_registry() -> ConnectorRegistry:
    """Get the global connector registry."""
    return _global_registry
