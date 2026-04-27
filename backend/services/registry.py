"""Persist document metadata — now a thin compatibility layer over SQLite.

The async database module (backend.database) is the primary store.
These sync functions are kept for any legacy / migration paths.
"""

import json
import os
from pathlib import Path
from typing import Any


def _ensure_parent(path: Path) -> None:
    """Ensure the parent directory of a path exists.

    Args:
        path: The path whose parent directory should exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def load_registry(path: str) -> dict[str, Any]:
    """Load a document registry from a JSON file.

    Args:
        path: Path to the registry JSON file.

    Returns:
        The registry dict, or an empty dict if the file doesn't exist.
    """
    p = Path(path)
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_registry(path: str, data: dict[str, Any]) -> None:
    """Save a document registry to a JSON file atomically.

    Writes to a temporary file first, then renames to avoid corruption.

    Args:
        path: Path to the registry JSON file.
        data: The registry dict to save.
    """
    p = Path(path)
    _ensure_parent(p)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=0)
    os.replace(tmp, p)


def register_document(
    path: str,
    document_id: str,
    *,
    provider: str,
    embedding_model: str,
    chunk_count: int,
) -> None:
    """Register a document in the registry.

    Args:
        path: Path to the registry JSON file.
        document_id: The document ID to register.
        provider: The embedding provider used.
        embedding_model: The embedding model used.
        chunk_count: Number of chunks in the document.
    """
    reg = load_registry(path)
    reg[document_id] = {
        "provider": provider,
        "embedding_model": embedding_model,
        "chunk_count": chunk_count,
    }
    save_registry(path, reg)


def get_document(path: str, document_id: str) -> dict[str, Any] | None:
    """Retrieve a document entry from the registry.

    Args:
        path: Path to the registry JSON file.
        document_id: The document ID to retrieve.

    Returns:
        The document entry dict, or None if not found.
    """
    reg = load_registry(path)
    entry = reg.get(document_id)
    return entry if isinstance(entry, dict) else None


def unregister_document(path: str, document_id: str) -> None:
    """Remove a document from the registry.

    Args:
        path: Path to the registry JSON file.
        document_id: The document ID to remove.
    """
    reg = load_registry(path)
    if document_id in reg:
        del reg[document_id]
        save_registry(path, reg)
