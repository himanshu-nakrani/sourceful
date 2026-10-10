"""``?`` -> ``%s`` translation used for every Postgres query."""

from __future__ import annotations

import pytest

from backend.database import _to_pyformat


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("SELECT * FROM t WHERE a = ? AND b = ?", "SELECT * FROM t WHERE a = %s AND b = %s"),
        # A '?' inside a string literal is data, not a placeholder.
        ("INSERT INTO m (id, content) VALUES (?, 'question?')", "INSERT INTO m (id, content) VALUES (%s, 'question?')"),
        ("SELECT 'it''s?' , ?", "SELECT 'it''s?' , %s"),
        # Literal % must be escaped for psycopg when params are passed.
        ("SELECT * FROM t WHERE name LIKE 'a%' AND id = ?", "SELECT * FROM t WHERE name LIKE 'a%%' AND id = %s"),
        ("SELECT 5 % 2", "SELECT 5 %% 2"),
    ],
)
def test_to_pyformat(query, expected):
    assert _to_pyformat(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM t WHERE a = ? AND b LIKE 'x%' AND c = 'why?'",
        "UPDATE t SET a = %s WHERE b = %s",
    ],
)
def test_to_pyformat_is_idempotent(query):
    once = _to_pyformat(query)
    assert _to_pyformat(once) == once
