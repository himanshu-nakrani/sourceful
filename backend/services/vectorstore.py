"""Vector persistence and retrieval for PostgreSQL + pgvector and SQLite fallback."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from backend.database import execute, fetch_all
from backend.services.chunking import ChunkPayload
from backend.settings import settings

try:
    import orjson
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    orjson = None


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    excerpt: str
    score: float
    page_number: int | None = None



def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in embedding) + "]"


async def replace_chunks(
    document_id: str,
    owner_id: str,
    chunks: list[ChunkPayload],
    embeddings: list[list[float]],
) -> None:
    await execute("DELETE FROM document_chunks WHERE document_id = ? AND owner_id = ?", (document_id, owner_id))
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        if settings.using_postgres:
            await execute(
                """
                INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, page_number, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?::vector)
                """,
                (
                    f"{document_id}:{chunk.chunk_index}",
                    document_id,
                    owner_id,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.page_number,
                    _vector_literal(embedding),
                ),
            )
        else:
            await execute(
                """
                INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, page_number, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{document_id}:{chunk.chunk_index}",
                    document_id,
                    owner_id,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.page_number,
                    json.dumps(embedding),
                ),
            )


async def preview_chunks(document_id: str, owner_id: str, limit: int = 8) -> list[dict]:
    return await fetch_all(
        """
        SELECT id AS chunk_id, document_id, content, page_number, chunk_index
        FROM document_chunks
        WHERE document_id = ? AND owner_id = ?
        ORDER BY chunk_index ASC
        LIMIT ?
        """,
        (document_id, owner_id, limit),
    )


def _load_embedding_json(payload: str) -> list[float]:
    if orjson is not None:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return orjson.loads(payload)
    return json.loads(payload)


def _compute_similarities_sqlite(rows: list[dict], query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
    import numpy as np

    matrix = np.asarray([_load_embedding_json(row["embedding_json"]) for row in rows], dtype=np.float32)
    query = np.asarray(query_embedding, dtype=np.float32)
    query = query / (np.linalg.norm(query) + 1e-9)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    scores = matrix @ query
    indices = np.argsort(-scores)[:top_k]
    result: list[RetrievedChunk] = []
    for index in indices:
        row = rows[int(index)]
        result.append(
            RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                excerpt=row["content"],
                score=float(scores[int(index)]),
                page_number=row.get("page_number"),
            )
        )
    return result


async def query_similar(document_id: str, owner_id: str, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
    if settings.using_postgres:
        rows = await fetch_all(
            """
            SELECT id, document_id, content, page_number,
                   1 - (embedding <=> ?::vector) AS score
            FROM document_chunks
            WHERE document_id = ? AND owner_id = ?
            ORDER BY embedding <=> ?::vector
            LIMIT ?
            """,
            (_vector_literal(query_embedding), document_id, owner_id, _vector_literal(query_embedding), top_k),
        )
        return [
            RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                excerpt=row["content"],
                score=float(row["score"] or 0.0),
                page_number=row.get("page_number"),
            )
            for row in rows
        ]

    rows = await fetch_all(
        "SELECT id, document_id, content, page_number, embedding_json FROM document_chunks WHERE document_id = ? AND owner_id = ?",
        (document_id, owner_id),
    )
    if not rows:
        return []

    return await asyncio.to_thread(_compute_similarities_sqlite, rows, query_embedding, top_k)
