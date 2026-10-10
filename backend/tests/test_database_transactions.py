"""Regression coverage for database transaction helpers."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from backend import database
from backend.database import execute, fetch_all, transaction


def test_postgres_transaction_uses_native_context_manager():
    """Postgres transactions must not mutate async connection autocommit state."""
    source = inspect.getsource(database.transaction)
    assert "conn.autocommit" not in source
    assert "conn.transaction()" in source


@pytest.mark.asyncio
async def test_sqlite_transaction_is_isolated_from_plain_execute():
    """A concurrent autocommit write must not be rolled back with another transaction."""
    await execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_regression (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL
        )
        """
    )
    await execute("DELETE FROM transaction_regression")

    tx_started = asyncio.Event()

    async def failing_transaction() -> None:
        async with transaction() as conn:
            await conn.execute(
                "INSERT INTO transaction_regression (id, label) VALUES (?, ?)",
                ("rolled-back", "transactional"),
            )
            tx_started.set()
            await asyncio.sleep(0.05)
            raise RuntimeError("force rollback")

    async def plain_write() -> None:
        # Bounded wait: if the transaction fails before signalling, fail fast
        # instead of hanging the whole suite.
        await asyncio.wait_for(tx_started.wait(), timeout=10)
        await execute(
            "INSERT INTO transaction_regression (id, label) VALUES (?, ?)",
            ("survives", "plain execute"),
        )

    results = await asyncio.gather(failing_transaction(), plain_write(), return_exceptions=True)
    assert isinstance(results[0], RuntimeError)
    assert results[1] is None

    rows = await fetch_all("SELECT id FROM transaction_regression ORDER BY id")
    assert [row["id"] for row in rows] == ["survives"]


@pytest.mark.asyncio
async def test_transaction_cursor_percent_and_literal_question_mark():
    """Literal % and '?' survive the transaction cursor, with or without params."""
    async with transaction() as cur:
        # Portable on both backends: execute() returns something with fetchone().
        row = await (await cur.execute("SELECT '100%' AS pct, 5 % 2 AS modulo, 'why?' AS q")).fetchone()
        row2 = await (await cur.execute("SELECT ? AS v, 'a%' AS lit", ("x",))).fetchone()
    row, row2 = dict(row), dict(row2)
    assert (row["pct"], row["modulo"], row["q"]) == ("100%", 1, "why?")
    assert (row2["v"], row2["lit"]) == ("x", "a%")
