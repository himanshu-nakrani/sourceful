"""Phase 0 migration tests: default workspace creation and backfill."""

import pytest

from backend.database import execute, fetch_one


@pytest.mark.asyncio
async def test_default_workspace_created_for_owner():
    """Verify that ensure_default_workspace creates a workspace when none exists."""
    from backend.services.workspace_service import ensure_default_workspace

    owner_scope = "test:default-workspace-test"
    
    # Clean up any existing workspace for this owner
    await execute("DELETE FROM workspaces WHERE owner_scope = ?", (owner_scope,))
    
    # Ensure default workspace is created
    workspace = await ensure_default_workspace(owner_scope)
    
    assert workspace is not None
    assert workspace["owner_scope"] == owner_scope
    assert workspace["is_default"] is True
    assert workspace["name"] == "Personal workspace"
    
    # Verify it's idempotent - calling again returns the same workspace
    workspace2 = await ensure_default_workspace(owner_scope)
    assert workspace2["id"] == workspace["id"]
    
    # Clean up
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace["id"],))


@pytest.mark.asyncio
async def test_backfill_documents_to_default_workspace():
    """Verify that existing documents without workspace_id are backfilled."""
    from backend.services.workspace_service import ensure_default_workspace
    import uuid

    owner_scope = "test:backfill-docs-test"
    
    # Clean up
    await execute("DELETE FROM workspace_sources WHERE workspace_id IN (SELECT id FROM workspaces WHERE owner_scope = ?)", (owner_scope,))
    await execute("DELETE FROM documents WHERE owner_id = ?", (owner_scope,))
    await execute("DELETE FROM workspaces WHERE owner_scope = ?", (owner_scope,))
    
    # Create a document without workspace_id (simulating legacy data)
    doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, owner_scope, "test.pdf", "openai", "text-embedding-3-small", "application/pdf", "abc123", 10, 1000, "ready")
    )
    
    # Ensure default workspace exists
    workspace = await ensure_default_workspace(owner_scope)
    
    # Manually run backfill (simulating migration logic)
    await execute(
        "UPDATE documents SET workspace_id = ? WHERE owner_id = ? AND workspace_id IS NULL",
        (workspace["id"], owner_scope)
    )
    
    # Create workspace_sources entry
    source_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_sources (id, workspace_id, source_type, document_id, source_title, mime_type, status)
        VALUES (?, ?, 'file', ?, ?, ?, ?)
        """,
        (source_id, workspace["id"], doc_id, "test.pdf", "application/pdf", "ready")
    )
    
    # Verify document now has workspace_id
    doc = await fetch_one("SELECT * FROM documents WHERE id = ?", (doc_id,))
    assert doc is not None
    assert doc["workspace_id"] == workspace["id"]
    
    # Verify workspace_sources entry exists
    source = await fetch_one("SELECT * FROM workspace_sources WHERE document_id = ?", (doc_id,))
    assert source is not None
    assert source["workspace_id"] == workspace["id"]
    
    # Clean up
    await execute("DELETE FROM workspace_sources WHERE id = ?", (source_id,))
    await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace["id"],))


@pytest.mark.asyncio
async def test_backfill_conversations_to_default_workspace():
    """Verify that existing conversations without workspace_id are backfilled."""
    from backend.services.workspace_service import ensure_default_workspace
    import uuid

    owner_scope = "test:backfill-conv-test"
    
    # Clean up
    await execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE owner_id = ?)", (owner_scope,))
    await execute("DELETE FROM conversations WHERE owner_id = ?", (owner_scope,))
    await execute("DELETE FROM workspaces WHERE owner_scope = ?", (owner_scope,))
    
    # Create a document first (conversations need a document)
    doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, owner_scope, "test.pdf", "openai", "text-embedding-3-small", "application/pdf", "abc123", 10, 1000, "ready")
    )
    
    # Create a conversation without workspace_id (simulating legacy data)
    conv_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO conversations (id, owner_id, document_id, title)
        VALUES (?, ?, ?, ?)
        """,
        (conv_id, owner_scope, doc_id, "Test conversation")
    )
    
    # Ensure default workspace exists
    workspace = await ensure_default_workspace(owner_scope)
    
    # Manually run backfill (simulating migration logic)
    await execute(
        "UPDATE conversations SET workspace_id = ? WHERE owner_id = ? AND workspace_id IS NULL",
        (workspace["id"], owner_scope)
    )
    
    # Verify conversation now has workspace_id
    conv = await fetch_one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    assert conv is not None
    assert conv["workspace_id"] == workspace["id"]
    
    # Clean up
    await execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace["id"],))
