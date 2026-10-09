"""Single source of truth for embedding dimensionality.

Every stored embedding is exactly ``EMBEDDING_DIMENSIONS`` (1536) floats so the
Postgres column can be ``vector(1536)`` with an HNSW index. Providers are asked
for that size explicitly and models that cannot produce it are rejected:

* OpenAI ``text-embedding-3-*``: ``dimensions=1536`` (native 1536 for -small,
  shortened from 3072 for -large).
* OpenAI ``text-embedding-ada-002``: fixed 1536; it rejects ``dimensions``.
* Gemini ``gemini-embedding-*``: ``output_dimensionality=1536``. Truncated
  ``gemini-embedding-001`` outputs are not unit-length, so they are
  L2-normalized (per the Gemini embeddings docs).
* Anything else (e.g. ``text-embedding-004``, ``embedding-001``, max 768 dims)
  raises :class:`UnsupportedEmbeddingModelError`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

EMBEDDING_DIMENSIONS = 1536

_OPENAI_FIXED_1536 = {"text-embedding-ada-002"}
_OPENAI_SHORTENABLE_PREFIX = "text-embedding-3-"
_GEMINI_FLEXIBLE_PREFIX = "gemini-embedding-"


class UnsupportedEmbeddingModelError(ValueError):
    """The provider/model cannot produce ``EMBEDDING_DIMENSIONS``-dim vectors."""


class EmbeddingDimensionError(ValueError):
    """A provider returned vectors of the wrong size."""


def _bare_model(model: str) -> str:
    name = (model or "").strip()
    return name.split("/", 1)[1] if name.startswith("models/") else name


def embedding_request_options(provider: str, model: str) -> dict[str, Any]:
    """Return the extra request kwargs that make ``model`` emit 1536 dims.

    Raises:
        UnsupportedEmbeddingModelError: if the model cannot produce 1536 dims.
    """
    bare = _bare_model(model)
    if provider == "openai":
        if bare in _OPENAI_FIXED_1536:
            return {}
        if bare.startswith(_OPENAI_SHORTENABLE_PREFIX):
            return {"dimensions": EMBEDDING_DIMENSIONS}
    elif provider == "gemini":
        if bare.startswith(_GEMINI_FLEXIBLE_PREFIX):
            return {"output_dimensionality": EMBEDDING_DIMENSIONS}
    raise UnsupportedEmbeddingModelError(
        f"Embedding model {model!r} (provider {provider!r}) cannot produce "
        f"{EMBEDDING_DIMENSIONS}-dimensional embeddings. Supported: OpenAI "
        "text-embedding-3-small / text-embedding-3-large / text-embedding-ada-002, "
        "Gemini models/gemini-embedding-001."
    )


def is_supported_embedding_model(provider: str, model: str) -> bool:
    """True when ``model`` can be configured to emit 1536-dim vectors."""
    try:
        embedding_request_options(provider, model)
    except UnsupportedEmbeddingModelError:
        return False
    return True


def l2_normalize(vector: Sequence[float]) -> list[float]:
    """Scale ``vector`` to unit length (returned unchanged if all zeros)."""
    norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    if norm == 0.0:
        return [float(v) for v in vector]
    return [float(v) / norm for v in vector]


def ensure_dimensions(vectors: Sequence[Sequence[float]], *, model: str) -> None:
    """Raise if any vector is not exactly ``EMBEDDING_DIMENSIONS`` long."""
    for index, vector in enumerate(vectors):
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise EmbeddingDimensionError(
                f"Embedding model {model!r} returned {len(vector)} dimensions for "
                f"item {index}; expected {EMBEDDING_DIMENSIONS}."
            )
