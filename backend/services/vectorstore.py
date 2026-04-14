"""Vector persistence and retrieval for PostgreSQL + pgvector and SQLite fallback."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from pydantic import TypeAdapter
from backend.database import execute, execute_many, fetch_all
from backend.services.chunking import ChunkPayload
from backend.settings import settings

try:
    import orjson
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    orjson = None

# ⚡ BOLT OPTIMIZATION:
# Pre-compile the TypeAdapter for list[float] to avoid runtime overhead.
# This uses Pydantic's underlying Rust-based JSON parser directly via dump_json(),
# skipping the standard library's json.dumps() when orjson is not available.
_embedding_adapter = TypeAdapter(list[float])

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

    if not chunks:
        return

    if settings.using_postgres:
        params_list = [
            (
                f"{document_id}:{chunk.chunk_index}",
                document_id,
                owner_id,
                chunk.chunk_index,
                chunk.content,
                chunk.page_number,
                _vector_literal(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        await execute_many(
            """
            INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, page_number, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?::vector)
            """,
            params_list,
        )
    else:
        params_list = [
            (
                f"{document_id}:{chunk.chunk_index}",
                document_id,
                owner_id,
                chunk.chunk_index,
                chunk.content,
                chunk.page_number,
                orjson.dumps(embedding).decode("utf-8") if orjson is not None else _embedding_adapter.dump_json(embedding).decode("utf-8"),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        await execute_many(
            """
            INSERT INTO document_chunks (id, document_id, owner_id, chunk_index, content, page_number, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params_list,
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
    """
    Parse a JSON-encoded embedding payload into a list of floats.
    
    Parameters:
    	payload (str | bytes): JSON text or UTF-8 bytes containing an array of numeric embedding values.
    
    Returns:
    	embedding (list[float]): The decoded embedding vector.
    """
    if orjson is not None:
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return orjson.loads(payload)
    return json.loads(payload)


def _compute_similarities_sqlite(rows: list[dict], query_embedding: list[float], top_k: int, min_score: float = 0.0) -> list[RetrievedChunk]:

    """
    Compute cosine similarity between a query embedding and a set of stored embeddings (SQLite fallback) and return the top-matching chunks.
    
    Parses each row's JSON-encoded embedding, normalizes vectors, computes cosine similarity with the query, and returns up to `top_k` RetrievedChunk entries whose similarity is greater than or equal to `min_score`, ordered by descending similarity.
    
    Parameters:
        rows (list[dict]): Rows containing at least `id`, `document_id`, `content`, and `embedding_json`; may include `page_number`.
        query_embedding (list[float]): Embedding vector for the query.
        top_k (int): Maximum number of results to return.
        min_score (float, optional): Minimum similarity score (inclusive) required for a result to be included. Defaults to 0.0.
    
    Returns:
        list[RetrievedChunk]: Retrieved chunks sorted by descending similarity. Each item's `score` is the cosine similarity between the stored embedding and `query_embedding`.
    
    Raises:
        ValueError: If NumPy is not available (required for similarity computation).
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError("numpy is required for SQLite vector similarity search.") from exc


    matrix = np.asarray([_load_embedding_json(row["embedding_json"]) for row in rows], dtype=np.float32)
    query = np.asarray(query_embedding, dtype=np.float32)
    query = query / (np.linalg.norm(query) + 1e-9)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    scores = matrix @ query
    indices = np.argsort(-scores)[:top_k]
    result: list[RetrievedChunk] = []
    for index in indices:
        score = float(scores[int(index)])
        if score < min_score:
            continue
        row = rows[int(index)]
        result.append(
            RetrievedChunk(
                chunk_id=row["id"],
                document_id=row["document_id"],
                excerpt=row["content"],
                score=score,
                page_number=row.get("page_number"),
            )
        )
    return result


async def query_similar(
    document_id: str,
    owner_id: str,
    query_embedding: list[float],
    top_k: int,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """
    Retrieve the most similar chunks for a single document using the provided query embedding.
    
    Parameters:
        document_id (str): ID of the document to search within.
        owner_id (str): ID of the owner/namespace for the document.
        query_embedding (list[float]): Embedding vector representing the query.
        top_k (int): Maximum number of results to return.
        min_score (float): Minimum similarity score required for a result to be included.
    
    Returns:
        list[RetrievedChunk]: Retrieved chunks meeting `min_score`, sorted by similarity descending and limited to `top_k`.
    """
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
            if float(row["score"] or 0.0) >= min_score
        ]

    rows = await fetch_all(
        "SELECT id, document_id, content, page_number, embedding_json FROM document_chunks WHERE document_id = ? AND owner_id = ?",
        (document_id, owner_id),
    )
    if not rows:
        return []

    return await asyncio.to_thread(_compute_similarities_sqlite, rows, query_embedding, top_k, min_score)


async def query_similar_multi(
    document_ids: list[str],
    owner_id: str,
    query_embedding: list[float],
    top_k: int,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """
    Search multiple documents for chunks similar to a query embedding and return the highest-scoring matches.
    
    Runs per-document similarity searches, merges all retrieved chunks, filters by `min_score`, sorts by score descending, and returns up to `top_k` results.
    
    Parameters:
        document_ids (list[str]): Document IDs to search.
        owner_id (str): Owner ID that scopes the document search.
        query_embedding (list[float]): Embedding vector representing the query.
        top_k (int): Maximum number of results to return across all documents.
        min_score (float, optional): Minimum similarity score required for a result to be included. Defaults to 0.0.
    
    Returns:
        list[RetrievedChunk]: Retrieved chunks across the given documents, sorted by descending `score`, limited to `top_k`.
    """
    tasks = [
        query_similar(doc_id, owner_id, query_embedding, top_k, min_score)
        for doc_id in document_ids
    ]
    results_per_doc = await asyncio.gather(*tasks)
    merged: list[RetrievedChunk] = []
    for chunks in results_per_doc:
        merged.extend(chunks)
    merged.sort(key=lambda c: c.score, reverse=True)
    return merged[:top_k]


# async def query_vertex_search(document_id: str, question: str, top_k: int) -> list[RetrievedChunk]:
#     """Query Vertex AI Search instead of local vector similarity."""
#     from backend.services.vertex_search import search as vertex_search
#
#     return await asyncio.to_thread(vertex_search, question, document_id, top_k)
