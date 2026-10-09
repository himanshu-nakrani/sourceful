"""Regression tests for boolean-column SQL portability (SQLite vs Postgres).

``get_default_workspace`` used ``is_default = 1 OR is_default = TRUE``. On
Postgres ``is_default`` is BOOLEAN and ``boolean = integer`` raises
``UndefinedFunction``, which broke ``POST /api/ingest`` (via
``ensure_default_workspace``) on every Postgres deployment.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from backend.database import close_db, fetch_one
from backend.services import workspace_service

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_default_workspace_lookup_is_idempotent():
    """The default workspace is created once and found again by the boolean filter.

    Runs against whichever backend DATABASE_URL selects (SQLite in CI; the
    same test passes against Postgres + pgvector locally).
    """

    async def scenario() -> None:
        owner_scope = f"anon:test-{uuid.uuid4().hex[:12]}"
        try:
            assert await workspace_service.get_default_workspace(owner_scope) is None
            first = await workspace_service.ensure_default_workspace(owner_scope)
            assert first["is_default"] is True
            found = await workspace_service.get_default_workspace(owner_scope)
            assert found is not None and found["id"] == first["id"]
            second = await workspace_service.ensure_default_workspace(owner_scope)
            assert second["id"] == first["id"]
            row = await fetch_one(
                "SELECT COUNT(*) AS n FROM workspaces WHERE owner_scope = ?",
                (owner_scope,),
            )
            assert int(row["n"]) == 1
        finally:
            await close_db()

    asyncio.run(scenario())


def _postgres_boolean_columns() -> set[str]:
    ddl = (BACKEND_DIR / "migrations.py").read_text() + (BACKEND_DIR / "database.py").read_text()
    return set(re.findall(r"\b([a-z_]+)\s+BOOLEAN\b", ddl))


# SQL that only ever runs on SQLite (INTEGER 0/1 columns), keyed by file.
_SQLITE_ONLY_ALLOWLIST = {
    # workspace_service.list_workspaces: SQLite branch of a using_postgres conditional.
    "services/workspace_service.py": ["archived = 0 OR archived IS NULL OR archived = FALSE"],
    # database.py: SQLite-only workspace backfill (_backfill_sqlite_*).
    "database.py": ["is_default = 1 LIMIT 1"],
}


def test_no_integer_literal_comparisons_on_postgres_boolean_columns():
    """Fail on ``<boolean column> = 0/1`` in backend SQL (breaks on Postgres).

    Use ``= TRUE`` / ``= FALSE`` (valid on SQLite >= 3.23 and Postgres) or pass a
    Python ``bool`` parameter instead.
    """
    columns = _postgres_boolean_columns()
    assert {"is_default", "archived", "revoked", "terminal"} <= columns
    pattern = re.compile(
        r"\b(" + "|".join(sorted(columns)) + r")\s*(=|!=|<>)\s*[01]\b"
    )
    offenders = []
    for path in BACKEND_DIR.rglob("*.py"):
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if rel.startswith("tests/") or rel == "migrations.py":
            continue
        allowed = _SQLITE_ONLY_ALLOWLIST.get(rel, [])
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line) and not any(a in line for a in allowed):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, "Integer comparison on BOOLEAN column:\n" + "\n".join(offenders)
