"""Tests for the Fix #5 anonymous-scope re-keying migration script."""

import uuid

import pytest

from backend.database import execute, fetch_one
from backend.scripts.migrate_anon_scopes import _is_legacy_anon, migrate
from backend.services.anon_scope import anon_owner_id


def test_is_legacy_anon_detects_raw_header():
    # Legacy raw header value under the anon: prefix.
    assert _is_legacy_anon("anon:my-client-session") is True


def test_is_legacy_anon_ignores_already_signed():
    # An already-migrated 24-char hex digest must not be re-signed.
    signed = anon_owner_id("my-client-session")
    assert _is_legacy_anon(signed) is False


def test_is_legacy_anon_ignores_user_scopes():
    assert _is_legacy_anon("user:abc123") is False


async def _seed_legacy_document(raw_session: str) -> str:
    doc_id = str(uuid.uuid4())
    legacy_owner = f"anon:{raw_session}"
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status)
        VALUES (?, ?, 'legacy.pdf', 'openai', 'text-embedding-3-small',
                'application/pdf', ?, 1, 100, 'ready')
        """,
        (doc_id, legacy_owner, f"chk-{doc_id}"),
    )
    return doc_id


@pytest.mark.asyncio
async def test_dry_run_does_not_modify_rows():
    raw_session = "dry-run-session"
    doc_id = await _seed_legacy_document(raw_session)
    try:
        await migrate(apply=False)
        doc = await fetch_one("SELECT owner_id FROM documents WHERE id = ?", (doc_id,))
        # Untouched: still in the legacy format.
        assert doc["owner_id"] == f"anon:{raw_session}"
    finally:
        await execute("DELETE FROM documents WHERE id = ?", (doc_id,))


@pytest.mark.asyncio
async def test_apply_rekeys_legacy_scope_to_hmac():
    raw_session = "apply-session"
    doc_id = await _seed_legacy_document(raw_session)
    try:
        await migrate(apply=True)
        doc = await fetch_one("SELECT owner_id FROM documents WHERE id = ?", (doc_id,))
        assert doc["owner_id"] == anon_owner_id(raw_session)
    finally:
        await execute("DELETE FROM documents WHERE id = ?", (doc_id,))


@pytest.mark.asyncio
async def test_apply_is_safe_to_run_twice():
    """Second run must be a no-op: already-signed scopes are not re-signed."""
    raw_session = "twice-session"
    doc_id = await _seed_legacy_document(raw_session)
    try:
        await migrate(apply=True)
        first = await fetch_one("SELECT owner_id FROM documents WHERE id = ?", (doc_id,))
        await migrate(apply=True)
        second = await fetch_one("SELECT owner_id FROM documents WHERE id = ?", (doc_id,))
        assert first["owner_id"] == second["owner_id"] == anon_owner_id(raw_session)
    finally:
        await execute("DELETE FROM documents WHERE id = ?", (doc_id,))
