"""Vertex AI Search integration for document indexing and retrieval."""

from __future__ import annotations

import logging
from typing import Any

from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings

logger = logging.getLogger("ragapp.vertex_search")

_client_cache: dict[str, Any] = {}


def _get_search_client():
    from google.cloud import discoveryengine

    key = "search"
    if key not in _client_cache:
        _client_cache[key] = discoveryengine.SearchServiceClient()
    return _client_cache[key]


def _get_document_client():
    from google.cloud import discoveryengine

    key = "document"
    if key not in _client_cache:
        _client_cache[key] = discoveryengine.DocumentServiceClient()
    return _client_cache[key]


def _serving_config_path() -> str:
    client = _get_search_client()
    return client.serving_config_path(
        project=settings.vertex_search_project,
        location=settings.vertex_search_location,
        data_store=settings.vertex_search_datastore_id,
        serving_config="default_config",
    )


def _document_parent_path() -> str:
    client = _get_document_client()
    return client.branch_path(
        settings.vertex_search_project,
        settings.vertex_search_location,
        settings.vertex_search_datastore_id,
        "default_branch",
    )


def upload_document(
    document_id: str,
    filename: str,
    raw: bytes,
    mime_type: str,
) -> str:
    """Upload a document to the Vertex AI Search datastore.

    Extracts text from the document and uploads it as structured data.
    Returns the Vertex document ID.
    """
    from google.cloud import discoveryengine
    from google.protobuf import struct_pb2

    from backend.services.extract import extract_document

    client = _get_document_client()
    parent = _document_parent_path()

    extracted = extract_document(filename=filename, raw=raw)
    text_content = "\n\n".join(
        section.text for section in extracted.sections if section.text.strip()
    )

    from datetime import datetime, timezone
    struct_data = struct_pb2.Struct()
    struct_data.update({
        "title": filename,
        "uri": filename,
        "categories": ["General"],
        "available_time": datetime.now(timezone.utc).isoformat(),
        "content": text_content[:100_000],
        "mime_type": mime_type,
        "document_id": document_id,
    })

    document = discoveryengine.Document(
        name=f"{parent}/documents/{document_id}",
        id=document_id,
        struct_data=struct_data,
    )

    request = discoveryengine.UpdateDocumentRequest(
        document=document,
        allow_missing=True,
    )

    response = client.update_document(request=request)
    logger.info("vertex_search_upload_ok document_id=%s", document_id)
    return response.id if response.id else document_id


def search(
    query: str,
    document_id: str | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Search the Vertex AI Search datastore and return results as RetrievedChunk objects."""
    from google.cloud import discoveryengine

    client = _get_search_client()
    serving_config = _serving_config_path()

    filter_str = f'document_id: ANY("{document_id}")' if document_id else None

    # If we are strictly querying a single document, pass an empty query to 
    # bypass standard edition's conversational relevance filter, which drops results 
    # for questions like 'summarize this' because it doesn't map to text exactly.
    actual_query = "" if document_id else query

    request = discoveryengine.SearchRequest(
        query=actual_query,
        serving_config=serving_config,
        page_size=top_k,
        filter=filter_str,
    )

    response = client.search(request=request)

    chunks: list[RetrievedChunk] = []
    for i, result in enumerate(response):
        if i >= top_k:
            break
        doc = result.document
        doc_id = doc.id if hasattr(doc, "id") else str(i)

        excerpt = ""
        page_number = None

        if hasattr(doc, "derived_struct_data") and doc.derived_struct_data:
            struct = dict(doc.derived_struct_data)
            snippets = struct.get("snippets", [])
            if snippets:
                excerpt = snippets[0].get("snippet", "")
            elif struct.get("content"):
                excerpt = struct.get("content", "")

        if hasattr(doc, "struct_data") and doc.struct_data:
            base_struct = dict(doc.struct_data)
            if base_struct.get("content") and not excerpt:
                excerpt = base_struct.get("content", "")

        if hasattr(doc, "content") and doc.content:
            if hasattr(doc.content, "raw_bytes") and doc.content.raw_bytes and not excerpt:
                mime = getattr(doc.content, "mime_type", "")
                if mime in ("text/plain", "text/markdown", "text/csv"):
                    excerpt = doc.content.raw_bytes.decode("utf-8", errors="replace")[:2000]
            if hasattr(doc.content, "mime_type") and doc.content.mime_type == "application/pdf":
                page_number = 1

        score = float(result.relevance_score) if hasattr(result, "relevance_score") and result.relevance_score else 0.0

        if not excerpt:
            continue

        chunks.append(
            RetrievedChunk(
                chunk_id=f"vertex:{doc_id}:{i}",
                document_id=document_id or doc_id,
                excerpt=excerpt,
                score=score,
                page_number=page_number,
            )
        )

    logger.info("vertex_search_results query=%r count=%d", query[:80], len(chunks))
    return chunks[:top_k]


def delete_document(document_id: str) -> None:
    """Delete a document from the Vertex AI Search datastore."""

    client = _get_document_client()
    parent = _document_parent_path()
    doc_name = f"{parent}/documents/{document_id}"

    try:
        client.delete_document(name=doc_name)
        logger.info("vertex_search_delete_ok document_id=%s", document_id)
    except Exception:
        logger.warning("vertex_search_delete_failed document_id=%s", document_id, exc_info=True)
