"""Document source connectors for background sync.

Supports: Google Drive, Notion, Confluence, S3.
Each connector implements the BaseConnector interface for unified polling/sync.
"""

from __future__ import annotations

from backend.connectors.base import BaseConnector, ConnectorConfig, SyncResult
from backend.connectors.registry import ConnectorRegistry, get_connector

__all__ = [
    "BaseConnector",
    "ConnectorConfig",
    "ConnectorRegistry",
    "SyncResult",
    "get_connector",
]
