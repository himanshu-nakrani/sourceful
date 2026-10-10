"""Worker entrypoint lifecycle (backend.worker) with the DB and job loop mocked."""

from __future__ import annotations

import asyncio

import pytest

import backend.worker as worker


@pytest.fixture
def lifecycle(monkeypatch):
    events: list[str] = []
    state = {"heartbeat_in_flight": False}

    async def init_db():
        events.append("init_db")

    async def require_current_schema():
        events.append("schema")

    async def record_heartbeat(name):
        assert name == "worker"
        state["heartbeat_in_flight"] = True
        events.append("heartbeat")
        try:
            await asyncio.sleep(0.05)  # a slow DB write still in progress at shutdown
        finally:
            state["heartbeat_in_flight"] = False

    async def close_db():
        # Closing the pool under an in-flight heartbeat would break that write.
        events.append("close_db" + ("(heartbeat in flight!)" if state["heartbeat_in_flight"] else ""))

    monkeypatch.setattr(worker, "init_db", init_db)
    monkeypatch.setattr(worker, "require_current_schema", require_current_schema)
    monkeypatch.setattr(worker, "record_heartbeat", record_heartbeat)
    monkeypatch.setattr(worker, "close_db", close_db)
    return events


def test_main_runs_loop_then_shuts_down_cleanly(monkeypatch, lifecycle):
    seen = {}

    async def worker_forever(stop_event):
        seen["stop_event"] = stop_event
        await asyncio.sleep(0.01)  # heartbeat starts and is mid-write
        assert not stop_event.is_set()

    monkeypatch.setattr(worker, "worker_forever", worker_forever)
    asyncio.run(worker.main())
    assert lifecycle[:3] == ["init_db", "schema", "heartbeat"]
    assert lifecycle[-1] == "close_db"  # heartbeat finished/cancelled before the pool closed
    assert seen["stop_event"].is_set()


def test_main_closes_db_even_when_loop_crashes(monkeypatch, lifecycle):
    async def worker_forever(stop_event):
        await asyncio.sleep(0.01)
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "worker_forever", worker_forever)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(worker.main())
    assert lifecycle[-1] == "close_db"


def test_heartbeat_loop_stops_when_event_set(monkeypatch):
    calls = []

    async def record_heartbeat(name):
        calls.append(name)

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        stop.set()

    monkeypatch.setattr(worker, "record_heartbeat", record_heartbeat)
    monkeypatch.setattr(worker.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(worker.settings, "worker_heartbeat_ttl_seconds", 3)
    stop = asyncio.Event()
    asyncio.run(worker._heartbeat_loop(stop))
    assert calls == ["worker"] and sleeps == [5]  # interval floors at 5s
