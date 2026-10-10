"""Workspace analytics + activity endpoints (backend.routers.analytics)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.database import execute

HEADERS = {"X-Client-Session": "ws-analytics"}
OWNER = f"anon:{HEADERS['X-Client-Session']}"
NOW = datetime.now(timezone.utc)
OLD = (NOW - timedelta(days=30)).isoformat()


def _ts(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def _ws(client) -> str:
    return client.get("/api/workspaces", headers=HEADERS).json()["workspaces"][0]["id"]


async def _seed(ws: str) -> dict:
    doc = str(uuid.uuid4())
    await execute(
        "INSERT INTO documents (id, owner_id, filename, provider, embedding_model, mime_type, checksum,"
        " chunk_count, file_size, status, workspace_id) VALUES (?, ?, 'a.txt', 'openai',"
        " 'text-embedding-3-small', 'text/plain', 'c', 1, 1, 'ready', ?)",
        (doc, OWNER, ws),
    )
    for sid, stype, status, ts in [("s1", "file", "ready", _ts(5)), ("s2", "url", "error", _ts(1)), ("s3", "url", "ready", OLD)]:
        await execute(
            "INSERT INTO workspace_sources (id, workspace_id, source_type, source_title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"{ws}-{sid}", ws, stype, f"title {sid}", status, ts, ts),
        )
    for aid, atype, ts in [("a1", "user_note", _ts(3)), ("a2", "saved_answer", OLD)]:
        await execute(
            "INSERT INTO workspace_artifacts (id, workspace_id, artifact_type, title, content, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'body', ?, ?)",
            (f"{ws}-{aid}", ws, atype, f"art {aid}", ts, ts),
        )
    conv = str(uuid.uuid4())
    await execute(
        "INSERT INTO conversations (id, owner_id, document_id, workspace_id, title) VALUES (?, ?, ?, ?, 'Chat A')",
        (conv, OWNER, doc, ws),
    )
    long_text = "x" * 250
    for mid, role, ts, content in [("m1", "user", _ts(2), long_text), ("m2", "assistant", _ts(0), "hi"), ("m3", "user", OLD, "old")]:
        await execute(
            "INSERT INTO messages (id, owner_id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"{ws}-{mid}", OWNER, conv, role, content, ts),
        )
    return {"doc": doc, "conv": conv}


@pytest.mark.asyncio
async def test_workspace_analytics_totals_breakdown_and_recent(client):
    ws = _ws(client)
    await _seed(ws)
    body = client.get(f"/api/workspaces/{ws}/analytics", headers=HEADERS).json()
    assert body["totals"] == {"sources": 3, "ready_sources": 2, "artifacts": 2, "conversations": 1, "messages": 3}
    assert sorted((r["type"], r["count"]) for r in body["breakdown"]["sources_by_type"]) == [("file", 1), ("url", 2)]
    assert sorted((r["type"], r["count"]) for r in body["breakdown"]["artifacts_by_type"]) == [("saved_answer", 1), ("user_note", 1)]
    # 30-day-old rows fall outside the 7-day window.
    assert body["recent"] == {"messages_7d": 2, "artifacts_7d": 1}


@pytest.mark.asyncio
async def test_workspace_activity_merges_sorts_and_limits(client):
    ws = _ws(client)
    await _seed(ws)
    feed = client.get(f"/api/workspaces/{ws}/activity", headers=HEADERS).json()["activities"]
    assert [(a["type"], a["id"].rsplit("-", 1)[-1]) for a in feed[:5]] == [
        ("message", "m2"), ("source_update", "s2"), ("message", "m1"), ("artifact", "a1"), ("source_update", "s1"),
    ]
    m1 = next(a for a in feed if a["id"].endswith("-m1"))
    assert len(m1["content_preview"]) == 100 and m1["conversation_title"] == "Chat A"
    assert len(feed) == 8

    limited = client.get(f"/api/workspaces/{ws}/activity?limit=2", headers=HEADERS).json()["activities"]
    assert [a["id"].rsplit("-", 1)[-1] for a in limited] == ["m2", "s2"]


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_workspace_activity_rejects_out_of_range_limit(client, limit):
    ws = _ws(client)
    resp = client.get(f"/api/workspaces/{ws}/activity?limit={limit}", headers=HEADERS)
    assert resp.status_code == 422


@pytest.mark.parametrize("path", ["analytics", "activity"])
def test_workspace_analytics_denies_other_users(client, path):
    ws = _ws(client)
    resp = client.get(f"/api/workspaces/{ws}/{path}", headers={"X-Client-Session": "intruder"})
    assert resp.status_code in (403, 404)


def test_empty_workspace_analytics_is_all_zero(client):
    ws = _ws(client)
    body = client.get(f"/api/workspaces/{ws}/analytics", headers=HEADERS).json()
    assert body["totals"] == {"sources": 0, "ready_sources": 0, "artifacts": 0, "conversations": 0, "messages": 0}
    assert client.get(f"/api/workspaces/{ws}/activity", headers=HEADERS).json() == {"activities": []}
