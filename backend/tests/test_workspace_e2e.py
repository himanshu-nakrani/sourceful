"""Phase 3 end-to-end validation tests: verify complete workspace workflows."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_e2e_workspace_lifecycle(client: AsyncClient):
    """Verify complete workspace lifecycle: create, add sources, chat, artifacts."""
    from backend.database import execute, fetch_one
    import uuid

    owner_scope = "test:e2e-workspace-lifecycle"
    workspace_id = str(uuid.uuid4())

    # Create workspace
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_scope, description, visibility, archived, is_default)
        VALUES (?, ?, ?, ?, ?, 'private', 0, 0)
        """,
        (workspace_id, "E2E Test Workspace", f"e2e-{workspace_id[:8]}", owner_scope, "Test workspace")
    )

    # Verify workspace exists
    workspace = await fetch_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    assert workspace is not None
    assert workspace["name"] == "E2E Test Workspace"

    # Add a source to the workspace
    doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, owner_scope, "test.pdf", "openai", "text-embedding-3-small", "application/pdf", "abc123", 10, 1000, "ready", workspace_id)
    )

    source_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_sources (id, workspace_id, source_type, document_id, source_title, mime_type, status)
        VALUES (?, ?, 'file', ?, ?, ?, 'ready')
        """,
        (source_id, workspace_id, doc_id, "test.pdf", "application/pdf")
    )

    # Verify source is in workspace
    source = await fetch_one("SELECT * FROM workspace_sources WHERE id = ?", (source_id,))
    assert source is not None
    assert source["workspace_id"] == workspace_id

    # Create a conversation in the workspace
    conv_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO conversations (id, owner_id, document_id, workspace_id, title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (conv_id, owner_scope, doc_id, workspace_id, "E2E Test Conversation")
    )

    # Verify conversation is in workspace
    conv = await fetch_one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    assert conv is not None
    assert conv["workspace_id"] == workspace_id

    # Add messages to the conversation
    user_msg_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO messages (id, conversation_id, role, content, owner_id)
        VALUES (?, ?, 'user', 'What is this document about?', ?)
        """,
        (user_msg_id, conv_id, owner_scope)
    )

    # Verify message exists
    msg = await fetch_one("SELECT * FROM messages WHERE id = ?", (user_msg_id,))
    assert msg is not None
    assert msg["role"] == "user"

    # Create an artifact in the workspace
    artifact_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'E2E Test Note', 'This is a test note')
        """,
        (artifact_id, workspace_id)
    )

    # Verify artifact is in workspace
    artifact = await fetch_one("SELECT * FROM workspace_artifacts WHERE id = ?", (artifact_id,))
    assert artifact is not None
    assert artifact["workspace_id"] == workspace_id

    # Verify workspace analytics include all data
    stats = await fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = ?) AS total_sources,
            (SELECT COUNT(*) FROM workspace_artifacts WHERE workspace_id = ?) AS total_artifacts,
            (SELECT COUNT(*) FROM conversations WHERE workspace_id = ?) AS conversations,
            (SELECT COUNT(*) FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE workspace_id = ?)) AS messages
        """,
        (workspace_id, workspace_id, workspace_id, workspace_id),
    )

    assert stats["total_sources"] == 1
    assert stats["total_artifacts"] == 1
    assert stats["conversations"] == 1
    assert stats["messages"] == 1

    # Clean up
    await execute("DELETE FROM messages WHERE id = ?", (user_msg_id,))
    await execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    await execute("DELETE FROM workspace_artifacts WHERE id = ?", (artifact_id,))
    await execute("DELETE FROM workspace_sources WHERE id = ?", (source_id,))
    await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))


@pytest.mark.asyncio
async def test_e2e_workspace_isolation(client: AsyncClient):
    """Verify that data is properly isolated between workspaces."""
    from backend.database import execute, fetch_all
    import uuid

    owner_scope = "test:e2e-workspace-isolation"
    workspace1_id = str(uuid.uuid4())
    workspace2_id = str(uuid.uuid4())

    # Create two workspaces
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_scope, description, visibility, archived, is_default)
        VALUES (?, ?, ?, ?, ?, 'private', 0, 0)
        """,
        (workspace1_id, "Workspace 1", f"ws1-{workspace1_id[:8]}", owner_scope, "Test workspace 1")
    )
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_scope, description, visibility, archived, is_default)
        VALUES (?, ?, ?, ?, ?, 'private', 0, 0)
        """,
        (workspace2_id, "Workspace 2", f"ws2-{workspace2_id[:8]}", owner_scope, "Test workspace 2")
    )

    # Add sources to each workspace
    source1_id = str(uuid.uuid4())
    source2_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_sources (id, workspace_id, source_type, source_title, status)
        VALUES (?, ?, 'file', 'source1.pdf', 'ready')
        """,
        (source1_id, workspace1_id)
    )
    await execute(
        """
        INSERT INTO workspace_sources (id, workspace_id, source_type, source_title, status)
        VALUES (?, ?, 'file', 'source2.pdf', 'ready')
        """,
        (source2_id, workspace2_id)
    )

    # Verify isolation
    sources1 = await fetch_all("SELECT * FROM workspace_sources WHERE workspace_id = ?", (workspace1_id,))
    sources2 = await fetch_all("SELECT * FROM workspace_sources WHERE workspace_id = ?", (workspace2_id,))

    assert len(sources1) == 1
    assert len(sources2) == 1
    assert sources1[0]["id"] == source1_id
    assert sources2[0]["id"] == source2_id

    # Add artifacts to each workspace
    artifact1_id = str(uuid.uuid4())
    artifact2_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'Note 1', 'Content 1')
        """,
        (artifact1_id, workspace1_id)
    )
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'Note 2', 'Content 2')
        """,
        (artifact2_id, workspace2_id)
    )

    # Verify artifact isolation
    artifacts1 = await fetch_all("SELECT * FROM workspace_artifacts WHERE workspace_id = ?", (workspace1_id,))
    artifacts2 = await fetch_all("SELECT * FROM workspace_artifacts WHERE workspace_id = ?", (workspace2_id,))

    assert len(artifacts1) == 1
    assert len(artifacts2) == 1
    assert artifacts1[0]["id"] == artifact1_id
    assert artifacts2[0]["id"] == artifact2_id

    # Clean up
    await execute("DELETE FROM workspace_artifacts WHERE id IN (?, ?)", (artifact1_id, artifact2_id))
    await execute("DELETE FROM workspace_sources WHERE id IN (?, ?)", (source1_id, source2_id))
    await execute("DELETE FROM workspaces WHERE id IN (?, ?)", (workspace1_id, workspace2_id))


@pytest.mark.asyncio
async def test_e2e_workspace_cascade_delete(client: AsyncClient):
    """Verify that deleting a workspace cascades to related data."""
    from backend.database import execute, fetch_one
    import uuid

    owner_scope = "test:e2e-cascade-delete"
    workspace_id = str(uuid.uuid4())

    # Create workspace with data
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_scope, description, visibility, archived, is_default)
        VALUES (?, ?, ?, ?, ?, 'private', 0, 0)
        """,
        (workspace_id, "Cascade Test Workspace", f"cascade-{workspace_id[:8]}", owner_scope, "Test workspace")
    )

    # Add source
    source_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_sources (id, workspace_id, source_type, source_title, status)
        VALUES (?, ?, 'file', 'source.pdf', 'ready')
        """,
        (source_id, workspace_id)
    )

    # Add artifact
    artifact_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content)
        VALUES (?, ?, 'user_note', 'Test Note', 'Test content')
        """,
        (artifact_id, workspace_id)
    )

    # Add conversation
    doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, owner_scope, "test.pdf", "openai", "text-embedding-3-small", "application/pdf", "abc123", 10, 1000, "ready", workspace_id)
    )
    conv_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO conversations (id, owner_id, document_id, workspace_id, title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (conv_id, owner_scope, doc_id, workspace_id, "Test Conversation")
    )

    # Delete workspace
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

    # Verify cascade deletion
    workspace = await fetch_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    assert workspace is None

    source = await fetch_one("SELECT * FROM workspace_sources WHERE id = ?", (source_id,))
    assert source is None

    artifact = await fetch_one("SELECT * FROM workspace_artifacts WHERE id = ?", (artifact_id,))
    assert artifact is None

    # Conversations and messages should be cascade deleted (workspace_id set to NULL)
    conv = await fetch_one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    assert conv is not None  # Conversation still exists but workspace_id should be NULL
    assert conv["workspace_id"] is None

    # Clean up remaining data
    await execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
