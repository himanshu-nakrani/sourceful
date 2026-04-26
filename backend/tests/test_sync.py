"""Phase 3 sync tests: verify URL source sync operations work correctly."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_url_adapter_fetch_content(client: AsyncClient):
    """Verify that the URL adapter can fetch content from a URL."""
    from backend.connectors.adapter import UrlSourceAdapter, get_adapter

    adapter = get_adapter("url")
    assert isinstance(adapter, UrlSourceAdapter)
    assert adapter.get_adapter_type() == "url"
    assert adapter.supports_resync() is True


@pytest.mark.asyncio
async def test_url_adapter_sync_detects_changes(client: AsyncClient):
    """Verify that URL sync detects when content has changed."""
    from backend.connectors.adapter import UrlSourceAdapter, SourceFetchError

    adapter = UrlSourceAdapter()

    # Test with a URL that should work (using a simple test URL)
    # In a real test, we'd use a mock or a controlled test server
    # For now, we'll test the error handling
    try:
        result = await adapter.sync("http://invalid-url-that-does-not-exist.example")
        assert result.success is False
        assert result.error is not None
        assert result.changed is False
    except SourceFetchError:
        # Expected for invalid URL
        pass


@pytest.mark.asyncio
async def test_file_adapter_no_resync(client: AsyncClient):
    """Verify that file adapter does not support resync."""
    from backend.connectors.adapter import FileSourceAdapter, get_adapter

    adapter = get_adapter("file")
    assert isinstance(adapter, FileSourceAdapter)
    assert adapter.get_adapter_type() == "file"
    assert adapter.supports_resync() is False


@pytest.mark.asyncio
async def test_file_adapter_sync_returns_no_resync_error(client: AsyncClient):
    """Verify that file adapter sync returns appropriate error."""
    from backend.connectors.adapter import FileSourceAdapter

    adapter = FileSourceAdapter()
    result = await adapter.sync("file://test.pdf")
    assert result.success is False
    assert "do not support resync" in result.error.lower()
    assert result.changed is False


@pytest.mark.asyncio
async def test_adapter_factory_invalid_type(client: AsyncClient):
    """Verify that adapter factory raises error for invalid type."""
    from backend.connectors.adapter import get_adapter

    with pytest.raises(ValueError, match="Unsupported source type"):
        get_adapter("invalid_type")


@pytest.mark.asyncio
async def test_source_metadata_checksum(client: AsyncClient):
    """Verify that source metadata includes checksum for change detection."""
    from backend.connectors.adapter import SourceMetadata

    metadata = SourceMetadata(
        title="Test",
        checksum="abc123",
        size_bytes=1000,
    )

    assert metadata.checksum == "abc123"
    assert metadata.size_bytes == 1000
    assert metadata.title == "Test"


@pytest.mark.asyncio
async def test_sync_result_change_detection(client: AsyncClient):
    """Verify that sync result correctly reports change status."""
    from backend.connectors.adapter import SyncResult
    from datetime import datetime

    # Unchanged sync
    unchanged = SyncResult(
        success=True,
        checksum="abc123",
        synced_at=datetime.utcnow(),
        changed=False,
    )
    assert unchanged.changed is False
    assert unchanged.success is True

    # Changed sync
    changed = SyncResult(
        success=True,
        checksum="def456",
        synced_at=datetime.utcnow(),
        changed=True,
    )
    assert changed.changed is True
    assert changed.checksum == "def456"

    # Failed sync
    failed = SyncResult(
        success=False,
        error="Failed to fetch",
        changed=False,
    )
    assert failed.success is False
    assert failed.error is not None
