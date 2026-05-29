"""One-time migration: re-key legacy anonymous owner scopes (Fix #5).

Fix #5 changed how anonymous clients are scoped. Previously the ``owner_id``
was ``anon:<raw X-Client-Session header>``; it is now
``anon:<hmac(header)>``. Any anonymous data created before Fix #5 shipped is
keyed by the old scheme and becomes invisible to its owner until it is
re-keyed.

This script rewrites those rows. It is **opt-in and non-idempotent**: re-signing
an already-signed value would corrupt it, so the script only ever maps
``anon:<raw>`` -> ``anon:<hmac(raw)>`` and refuses to run twice against the same
data. Run it once, during the upgrade that introduces Fix #5.

Usage (from the repo root, with the backend venv active)::

    # Show what would change without writing (default):
    python -m backend.scripts.migrate_anon_scopes

    # Apply the changes:
    python -m backend.scripts.migrate_anon_scopes --apply

The signing secret is read from settings exactly as the running app reads it
(ANON_SESSION_SECRET, then DEFAULT_SUPERUSER_PASSWORD). Make sure the same
secret is configured here as in the deployment before applying.
"""

from __future__ import annotations

import argparse
import asyncio

from backend.database import close_db, execute, fetch_all, init_db
from backend.services.anon_scope import ANON_PREFIX, anon_owner_id

# (table, column) pairs that store an anonymous owner scope.
_OWNER_ID_TABLES: tuple[tuple[str, str], ...] = (
    ("documents", "owner_id"),
    ("document_jobs", "owner_id"),
    ("document_chunks", "owner_id"),
    ("conversations", "owner_id"),
    ("messages", "owner_id"),
    ("workspaces", "owner_scope"),
)


def _is_legacy_anon(value: str) -> bool:
    """True if value looks like the pre-Fix-#5 ``anon:<raw-header>`` form.

    A value is already migrated when the part after ``anon:`` is a 24-char
    lowercase hex digest (the HMAC output). Anything else under the ``anon:``
    prefix is treated as a legacy raw header value that needs re-keying.
    """
    if not value.startswith(ANON_PREFIX):
        return False
    suffix = value[len(ANON_PREFIX):]
    if len(suffix) == 24 and all(c in "0123456789abcdef" for c in suffix):
        # Already an HMAC digest — leave it alone.
        return False
    return True


async def _distinct_scopes(table: str, column: str) -> list[str]:
    rows = await fetch_all(
        f"SELECT DISTINCT {column} AS scope FROM {table} "
        f"WHERE {column} LIKE ?",
        (f"{ANON_PREFIX}%",),
    )
    return [r["scope"] for r in rows if r.get("scope")]


async def migrate(apply: bool) -> int:
    """Re-key legacy anon scopes. Returns the number of (table,row) updates.

    When ``apply`` is False, performs a dry run and only reports the plan.
    """
    await init_db()
    total_updates = 0
    try:
        for table, column in _OWNER_ID_TABLES:
            scopes = await _distinct_scopes(table, column)
            for old_scope in scopes:
                if not _is_legacy_anon(old_scope):
                    continue
                raw_header = old_scope[len(ANON_PREFIX):]
                new_scope = anon_owner_id(raw_header)
                if new_scope == old_scope:
                    continue
                count_rows = await fetch_all(
                    f"SELECT COUNT(*) AS ct FROM {table} WHERE {column} = ?",
                    (old_scope,),
                )
                affected = count_rows[0]["ct"] if count_rows else 0
                action = "WOULD UPDATE" if not apply else "UPDATING"
                print(f"  [{action}] {table}.{column}: {old_scope} -> {new_scope} ({affected} rows)")
                if apply:
                    await execute(
                        f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                        (new_scope, old_scope),
                    )
                total_updates += affected
        mode = "Applied" if apply else "Dry run — no changes written for"
        print(f"\n{mode} {total_updates} row update(s) across {len(_OWNER_ID_TABLES)} table(s).")
        if not apply and total_updates:
            print("Re-run with --apply to write these changes.")
    finally:
        await close_db()
    return total_updates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes. Without this flag the script only reports a plan (dry run).",
    )
    args = parser.parse_args()
    asyncio.run(migrate(apply=args.apply))


if __name__ == "__main__":
    main()
