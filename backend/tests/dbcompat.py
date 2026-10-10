"""Helpers for tests that seed raw rows on both SQLite and Postgres."""

from __future__ import annotations

import json
from collections.abc import Sequence

from backend.settings import settings

# document_chunks stores vectors as JSON text on SQLite and as pgvector
# ``vector(1536)`` on Postgres.
VECTOR_COLUMN = "embedding" if settings.using_postgres else "embedding_json"


def vector_value(vector: Sequence[float] | None) -> str | None:
    """Parameter for VECTOR_COLUMN; JSON text parses as a pgvector literal.

    ``None``/empty means "no embedding": SQLite rows use ``'[]'``, Postgres
    rows use NULL (an empty vector is not a valid ``vector(1536)``).
    """
    if not vector:
        return None if settings.using_postgres else "[]"
    return json.dumps(list(vector))
