from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from backend.database import execute, fetch_one


def _ts(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%d %H:%M:%S")


def login_admin(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert response.status_code == 200
    return response.json()


async def _seed_overview_rows() -> None:
    admin = await fetch_one("SELECT id FROM users WHERE email = ?", ("admin@example.com",))
    assert admin is not None
    admin_id = admin["id"]

    old_user_id = str(uuid.uuid4())
    recent_user_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, is_verified, created_at)
        VALUES (?, 'old-user@example.com', 'x', 'user', TRUE, FALSE, ?)
        """,
        (old_user_id, _ts(timedelta(days=-10))),
    )
    await execute(
        """
        INSERT INTO users (id, email, password_hash, role, is_active, is_verified, created_at)
        VALUES (?, 'recent-user@example.com', 'x', 'user', TRUE, FALSE, ?)
        """,
        (recent_user_id, _ts(timedelta(days=-2))),
    )

    old_doc_id = str(uuid.uuid4())
    recent_doc_id = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status, created_at)
        VALUES (?, ?, 'old.txt', 'openai', 'text-embedding-3-small', 'text/plain',
                'chk-old', 3, 10, 'ready', ?)
        """,
        (old_doc_id, admin_id, _ts(timedelta(days=-10))),
    )
    await execute(
        """
        INSERT INTO documents
            (id, owner_id, filename, provider, embedding_model, mime_type,
             checksum, chunk_count, file_size, status, created_at)
        VALUES (?, ?, 'recent.txt', 'gemini', 'text-embedding-004', 'text/plain',
                'chk-recent', 2, 10, 'queued', ?)
        """,
        (recent_doc_id, admin_id, _ts(timedelta(hours=-12))),
    )

    conversation_id = str(uuid.uuid4())
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, title) VALUES (?, ?, ?, 'seeded')",
        (conversation_id, admin_id, recent_doc_id),
    )
    await execute(
        """
        INSERT INTO messages (id, owner_id, conversation_id, role, content, created_at)
        VALUES (?, ?, ?, 'user', 'old question', ?)
        """,
        (str(uuid.uuid4()), admin_id, conversation_id, _ts(timedelta(days=-3))),
    )
    await execute(
        """
        INSERT INTO messages (id, owner_id, conversation_id, role, content, created_at)
        VALUES (?, ?, ?, 'user', 'new question', ?)
        """,
        (str(uuid.uuid4()), admin_id, conversation_id, _ts(timedelta(hours=-1))),
    )
    await execute(
        """
        INSERT INTO messages (id, owner_id, conversation_id, role, content, created_at)
        VALUES (?, ?, ?, 'assistant', 'not a question', ?)
        """,
        (str(uuid.uuid4()), admin_id, conversation_id, _ts(timedelta(hours=-1))),
    )

    await execute(
        """
        INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, revoked, created_at)
        VALUES (?, ?, 'hash-old', ?, FALSE, ?)
        """,
        (str(uuid.uuid4()), old_user_id, _ts(timedelta(days=1)), _ts(timedelta(days=-10))),
    )
    await execute(
        """
        INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, revoked, created_at)
        VALUES (?, ?, 'hash-revoked', ?, TRUE, ?)
        """,
        (str(uuid.uuid4()), recent_user_id, _ts(timedelta(days=1)), _ts(timedelta(hours=-1))),
    )
    await execute(
        """
        INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, revoked, created_at)
        VALUES (?, ?, 'hash-recent', ?, FALSE, ?)
        """,
        (str(uuid.uuid4()), recent_user_id, _ts(timedelta(days=1)), _ts(timedelta(hours=-2))),
    )


def test_analytics_overview_requires_admin(client):
    response = client.get("/api/analytics/overview")
    assert response.status_code == 401

    client.post(
        "/api/auth/signup",
        json={"email": "member@example.com", "password": "strong-pass-123"},
    )
    forbidden = client.get("/api/analytics/overview")
    assert forbidden.status_code == 403


def test_analytics_overview_uses_sql_time_windows(client):
    login_admin(client)
    asyncio.run(_seed_overview_rows())

    response = client.get("/api/analytics/overview")
    assert response.status_code == 200
    payload = response.json()

    # Seeded admin + old user + recent user.
    assert payload["totals"]["users"] == 3
    # Admin login session + recent_user recent session. Old session and revoked session excluded.
    assert payload["totals"]["active_users_7d"] == 2
    assert payload["totals"]["documents"] == 2
    assert payload["totals"]["ready_documents"] == 1
    assert payload["totals"]["conversations"] == 1
    assert payload["totals"]["messages"] == 3
    assert payload["totals"]["chunks"] == 5

    # Admin (now) + recent user; old user is outside 7d.
    assert payload["recent"]["signups_7d"] == 2
    # Only the recent document.
    assert payload["recent"]["uploads_7d"] == 1
    # Only the recent user-role message; old question and assistant message excluded.
    assert payload["recent"]["questions_24h"] == 1
    # Admin login + recent_user recent session; old and revoked excluded.
    assert payload["recent"]["sessions_24h"] == 2

    by_provider = {row["provider"]: row for row in payload["provider_breakdown"]}
    assert by_provider["openai"]["documents"] == 1
    assert by_provider["openai"]["ready_documents"] == 1
    assert by_provider["gemini"]["documents"] == 1
    assert by_provider["gemini"]["ready_documents"] == 0
