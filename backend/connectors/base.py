"""Base connector interface for document source integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator


@dataclass
class ConnectorConfig:
    """Configuration for a connector instance."""

    id: str  # Unique connector instance ID
    source_type: str  # e.g., "google_drive", "notion", "confluence", "s3"
    workspace_id: str | None = None
    enabled: bool = True
    # Source-specific credentials (encrypted at rest)
    credentials: dict[str, Any] | None = None
    # Sync settings
    sync_interval_minutes: int = 60
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None  # "success", "error", "in_progress"
    last_sync_error: str | None = None
    # Filter settings
    include_paths: list[str] | None = None  # Whitelist patterns
    exclude_paths: list[str] | None = None  # Blacklist patterns
    # Source-specific options
    options: dict[str, Any] | None = None


@dataclass
class SyncResult:
    """Result of a sync operation."""

    connector_id: str
    started_at: datetime
    completed_at: datetime
    status: str  # "success", "error", "partial"
    documents_added: int = 0
    documents_updated: int = 0
    documents_removed: int = 0
    documents_failed: int = 0
    error_message: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class RemoteDocument:
    """Document metadata from a remote source."""

    source_id: str  # ID in the remote system
    source_type: str
    connector_id: str
    name: str
    path: str | None = None  # Human-readable path
    mime_type: str | None = None
    content_hash: str | None = None  # For change detection
    modified_at: datetime | None = None
    created_at: datetime | None = None
    size_bytes: int | None = None
    download_url: str | None = None  # Temporary URL for fetch
    metadata: dict[str, Any] | None = None  # Source-specific metadata


class BaseConnector(ABC):
    """Abstract base class for document source connectors."""

    SOURCE_TYPE: str = ""

    def __init__(self, config: ConnectorConfig):
        self.config = config

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str | None]:
        """Validate credentials and connectivity.

        Returns: (success, error_message)
        """
        ...

    @abstractmethod
    async def list_documents(
        self, since: datetime | None = None
    ) -> AsyncIterator[RemoteDocument]:
        """List all documents from the source, optionally filtered by modification time."""
        ...

    @abstractmethod
    async def download_document(self, remote_doc: RemoteDocument) -> bytes:
        """Download document content as bytes."""
        ...

    @abstractmethod
    async def sync(self, db_session: Any, document_service: Any) -> SyncResult:
        """Perform full sync: list, compare, download, ingest.

        Args:
            db_session: Database session for persistence
            document_service: Service for document creation/updates

        Returns:
            SyncResult with statistics
        """
        ...

    def should_include(self, path: str) -> bool:
        """Check if path passes include/exclude filters."""
        import fnmatch

        # Check excludes first
        if self.config.exclude_paths:
            for pattern in self.config.exclude_paths:
                if fnmatch.fnmatch(path, pattern):
                    return False

        # Check includes (if specified, path must match at least one)
        if self.config.include_paths:
            for pattern in self.config.include_paths:
                if fnmatch.fnmatch(path, pattern):
                    return True
            return False

        return True
