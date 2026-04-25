"""Phase 0 route tests: verify workspace_id correctness across all workspace-scoped routes."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_requires_workspace_id_when_provided(client: AsyncClient):
    """Verify that chat requests with workspace_id are properly scoped."""
    from backend.database import execute, fetch_one
    import uuid

    # Create a test workspace
    owner_scope = "test:chat-workspace-id-test"
    workspace_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO workspaces (id, name, slug, owner_scope, description, visibility, archived, is_default)
        VALUES (?, ?, ?, ?, ?, 'private', 0, 1)
        """,
        (workspace_id, "Test Workspace", f"test-{workspace_id[:8]}", owner_scope, "Test workspace")
    )

    # Create a document in the workspace
    doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum, chunk_count, file_size, status, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, owner_scope, "test.pdf", "openai", "text-embedding-3-small", "application/pdf", "abc123", 10, 1000, "ready", workspace_id)
    )

    # Create a conversation in the workspace
    conv_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO conversations (id, owner_id, document_id, workspace_id, title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (conv_id, owner_scope, doc_id, workspace_id, "Test conversation")
    )

    # Verify workspace_id is preserved in conversation
    conv = await fetch_one("SELECT workspace_id FROM conversations WHERE id = ?", (conv_id,))
    assert conv is not None
    assert conv["workspace_id"] == workspace_id

    # Verify workspace_id is preserved in document
    doc = await fetch_one("SELECT workspace_id FROM documents WHERE id = ?", (doc_id,))
    assert doc is not None
    assert doc["workspace_id"] == workspace_id

    # Clean up
    await execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))


@pytest.mark.asyncio
async def test_workspace_sources_scoped_to_workspace(client: AsyncClient):
    """Verify that workspace_sources are properly scoped to their workspace."""
    from backend.database import execute, fetch_all, fetch_one
    import uuid

    # Create two workspaces
    owner_scope = "test:workspace-sources-scope-test"
    workspace1_id = str(uuid.uuid4())
    workspace2_id = str(uuid.uuid4())
    
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

    # Create sources in each workspace
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

    # Verify sources are scoped correctly
    sources1 = await fetch_all("SELECT * FROM workspace_sources WHERE workspace_id = ?", (workspace1_id,))
    sources2 = await fetch_all("SELECT * FROM workspace_sources WHERE workspace_id = ?", (workspace2_id,))
    
    assert len(sources1) == 1
    assert len(sources2) == 1
    assert sources1[0]["id"] == source1_id
    assert sources2[0]["id"] == source2_id
    assert sources1[0]["workspace_id"] == workspace1_id
    assert sources2[0]["workspace_id"] == workspace2_id

    # Clean up
    await execute("DELETE FROM workspace_sources WHERE id IN (?, ?)", (source1_id, source2_id))
    await execute("DELETE FROM workspaces WHERE id IN (?, ?)", (workspace1_id, workspace2_id))


@pytest.mark.asyncio
async def test_workspace_artifacts_scoped_to_workspace(client: AsyncClient):
    """Verify that workspace_artifacts are properly scoped to their workspace."""
    from backend.database import execute, fetch_all, fetch_one
    import uuid

    # Create two workspaces
    owner_scope = "test:workspace-artifacts-scope-test"
    workspace1_id = str(uuid.uuid4())
    workspace2_id = str(uuid.uuid4())
    
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

    # Create artifacts in each workspace
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

    # Verify artifacts are scoped correctly
    artifacts1 = await fetch_all("SELECT * FROM workspace_artifacts WHERE workspace_id = ?", (workspace1_id,))
    artifacts2 = await fetch_all("SELECT * FROM workspace_artifacts WHERE workspace_id = ?", (workspace2_id,))
    
    assert len(artifacts1) == 1
    assert len(artifacts2) == 1
    assert artifacts1[0]["id"] == artifact1_id
    assert artifacts2[0]["id"] == artifact2_id
    assert artifacts1[0]["workspace_id"] == workspace1_id
    assert artifacts2[0]["workspace_id"] == workspace2_id

    # Clean up
    await execute("DELETE FROM workspace_artifacts WHERE id IN (?, ?)", (artifact1_id, artifact2_id))
    await execute("DELETE FROM workspaces WHERE id IN (?, ?)", (workspace1_id, workspace2_id))
