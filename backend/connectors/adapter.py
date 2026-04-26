"""Phase 3: Source adapter interface for future connectors.

This module defines the abstract interface that all source adapters must implement.
Adapters are responsible for:
1. Fetching content from external sources (URLs, APIs, etc.)
2. Converting content to a format suitable for chunking and embedding
3. Providing metadata about the source (title, mime type, etc.)
4. Supporting resync operations for sources that change over time

The current implementation includes:
- Base adapter abstract class
- URL source adapter (for web pages)
- File source adapter (for uploaded files)
Future adapters could include:
- Confluence adapter
- Notion adapter
- Google Drive adapter
- SharePoint adapter
- etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class SourceMetadata:
    """Metadata about a source document."""

    title: str
    mime_type: str | None = None
    author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    additional_metadata: dict[str, Any] | None = None


@dataclass
class SourceContent:
    """The raw content of a source document."""

    text: str
    metadata: SourceMetadata
    raw_bytes: bytes | None = None


@dataclass
class SyncResult:
    """Result of a source sync operation."""

    success: bool
    content: SourceContent | None = None
    error: str | None = None
    checksum: str | None = None
    synced_at: datetime | None = None
    changed: bool = False  # True if content changed since last sync


class SourceAdapter(ABC):
    """Abstract base class for source adapters.

    All source adapters must implement this interface to ensure consistent
    behavior across different source types.
    """

    @abstractmethod
    async def fetch(self, source_url: str, **kwargs: Any) -> SourceContent:
        """Fetch content from the source.

        Args:
            source_url: The URL or identifier of the source
            **kwargs: Additional adapter-specific parameters

        Returns:
            SourceContent containing the fetched content and metadata

        Raises:
            SourceFetchError: If fetching fails
        """
        pass

    @abstractmethod
    async def sync(self, source_url: str, last_checksum: str | None = None, **kwargs: Any) -> SyncResult:
        """Sync the source and detect if content has changed.

        Args:
            source_url: The URL or identifier of the source
            last_checksum: The checksum from the previous sync (if any)
            **kwargs: Additional adapter-specific parameters

        Returns:
            SyncResult indicating success, whether content changed, and new content

        Raises:
            SourceFetchError: If syncing fails
        """
        pass

    @abstractmethod
    def get_adapter_type(self) -> str:
        """Return the adapter type identifier (e.g., 'url', 'file', 'confluence')."""
        pass

    @abstractmethod
    def supports_resync(self) -> bool:
        """Return True if this adapter supports resync operations."""
        pass


class SourceFetchError(Exception):
    """Raised when source fetching fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        code: str = "SOURCE_FETCH_ERROR",
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class UrlSourceAdapter(SourceAdapter):
    """Adapter for fetching content from web URLs."""

    def get_adapter_type(self) -> str:
        return "url"

    def supports_resync(self) -> bool:
        return True

    async def fetch(self, source_url: str, **kwargs: Any) -> SourceContent:
        """Fetch content from a URL."""
        import hashlib
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(source_url, follow_redirects=True)
                response.raise_for_status()
                
                content_bytes = response.content
                text = response.text
                
                # Calculate checksum
                checksum = hashlib.sha256(content_bytes).hexdigest()
                
                # Try to extract metadata
                mime_type = response.headers.get("content-type", "text/html")
                
                return SourceContent(
                    text=text,
                    metadata=SourceMetadata(
                        title=source_url,  # Could extract from HTML title
                        mime_type=mime_type,
                        size_bytes=len(content_bytes),
                        checksum=checksum,
                    ),
                    raw_bytes=content_bytes,
                )
            except httpx.HTTPStatusError as e:
                raise SourceFetchError(
                    f"Failed to fetch URL: {e}",
                    status_code=e.response.status_code,
                    code="URL_FETCH_ERROR",
                    details={"url": source_url},
                )
            except Exception as e:
                raise SourceFetchError(
                    f"Failed to fetch URL: {e}",
                    code="URL_FETCH_ERROR",
                    details={"url": source_url},
                )

    async def sync(self, source_url: str, last_checksum: str | None = None, **kwargs: Any) -> SyncResult:
        """Sync a URL source and detect changes."""
        try:
            content = await self.fetch(source_url, **kwargs)
            new_checksum = content.metadata.checksum
            
            if last_checksum and new_checksum == last_checksum:
                return SyncResult(
                    success=True,
                    content=None,
                    checksum=new_checksum,
                    synced_at=datetime.utcnow(),
                    changed=False,
                )
            
            return SyncResult(
                success=True,
                content=content,
                checksum=new_checksum,
                synced_at=datetime.utcnow(),
                changed=True,
            )
        except SourceFetchError as e:
            return SyncResult(
                success=False,
                error=e.message,
                checksum=last_checksum,
                synced_at=datetime.utcnow(),
                changed=False,
            )


class FileSourceAdapter(SourceAdapter):
    """Adapter for file sources (uploaded files)."""

    def get_adapter_type(self) -> str:
        return "file"

    def supports_resync(self) -> bool:
        return False  # Uploaded files don't change after upload

    async def fetch(self, source_url: str, **kwargs: Any) -> SourceContent:
        """Fetch content from a file (source_url is the file path or ID)."""
        # This is a placeholder - actual implementation would depend on
        # how files are stored (local filesystem, S3, etc.)
        raise NotImplementedError("File source adapter not yet implemented")

    async def sync(self, source_url: str, last_checksum: str | None = None, **kwargs: Any) -> SyncResult:
        """File sources don't support resync."""
        return SyncResult(
            success=False,
            error="File sources do not support resync",
            changed=False,
        )


def get_adapter(source_type: str) -> SourceAdapter:
    """Factory function to get an adapter for a given source type.

    Args:
        source_type: The type of source ('url', 'file', etc.)

    Returns:
        An instance of the appropriate adapter

    Raises:
        ValueError: If the source type is not supported
    """
    adapters: dict[str, type[SourceAdapter]] = {
        "url": UrlSourceAdapter,
        "file": FileSourceAdapter,
    }

    adapter_class = adapters.get(source_type)
    if not adapter_class:
        raise ValueError(f"Unsupported source type: {source_type}")

    return adapter_class()
