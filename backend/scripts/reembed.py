"""Re-embed documents whose vectors are not 1536-dimensional.

Schema v16 pins ``document_chunks.embedding`` to ``vector(1536)``. Documents that
were embedded at another size (e.g. 3072-dim Gemini vectors) are flagged with
``documents.reembed_required``; on Postgres their old vectors were copied to
``document_chunk_embeddings_legacy`` and cleared, on SQLite they are left in place
and skipped by retrieval. Chunk text is kept in both cases, so re-embedding only
calls the embedding API (no re-upload, no re-extraction).

This script enqueues a normal reprocess job per flagged document; the worker
(``python -m backend.worker``) then re-embeds it at 1536 dims and clears the flag.
Users can do the same for a single document via
``POST /api/documents/{id}/reprocess``.

Usage (from the repo root, with the backend venv and the deployment's
DATABASE_URL / settings active)::

    # List flagged documents and the model each would be re-embedded with:
    python -m backend.scripts.reembed

    # Enqueue the jobs (keys are read from the environment, never from argv):
    OPENAI_API_KEY=... GEMINI_API_KEY=... python -m backend.scripts.reembed --apply

Documents whose stored model cannot produce 1536 dims (e.g. ``text-embedding-004``)
are moved to the provider default (DEFAULT_EMBEDDING_MODEL_OPENAI / _GEMINI) unless
``--openai-model`` / ``--gemini-model`` is given. Documents for a provider with no key
in the environment are skipped and reported.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from backend.database import close_db, fetch_all, init_db
from backend.services.embedding_spec import is_supported_embedding_model
from backend.settings import settings

_KEY_ENV = {
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _provider_key(provider: str) -> str:
    for name in _KEY_ENV.get(provider, ()):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def target_model(provider: str, current: str, overrides: dict[str, str | None]) -> str | None:
    """Model to re-embed with, or None when the provider has no 1536-dim option."""
    override = overrides.get(provider)
    if override:
        return override if is_supported_embedding_model(provider, override) else None
    if is_supported_embedding_model(provider, current):
        return current
    default = {
        "openai": settings.default_embedding_model_openai,
        "gemini": settings.default_embedding_model_gemini,
    }.get(provider)
    return default if default and is_supported_embedding_model(provider, default) else None


async def find_flagged_documents() -> list[dict]:
    return await fetch_all(
        """
        SELECT id, owner_id, filename, provider, embedding_model, status
        FROM documents
        WHERE reembed_required = TRUE
        ORDER BY created_at ASC
        """
    )


async def run(*, apply: bool, overrides: dict[str, str | None]) -> dict[str, int]:
    from backend.services.jobs import enqueue_reprocess_job

    await init_db()  # also runs the v16 migration that sets the flags
    stats = {"flagged": 0, "enqueued": 0, "skipped": 0}
    try:
        documents = await find_flagged_documents()
        stats["flagged"] = len(documents)
        for doc in documents:
            provider = doc["provider"]
            model = target_model(provider, doc["embedding_model"], overrides)
            label = f"{doc['id']} ({doc['filename']}) {provider}:{doc['embedding_model']}"
            if model is None:
                print(f"SKIP  {label}: no model for this provider can produce 1536 dims")
                stats["skipped"] += 1
                continue
            if doc["status"] in {"queued", "processing"}:
                print(f"SKIP  {label}: already {doc['status']}")
                stats["skipped"] += 1
                continue
            key = _provider_key(provider)
            if apply and not key:
                names = " or ".join(_KEY_ENV.get(provider, ("<provider key>",)))
                print(f"SKIP  {label}: set {names} to re-embed")
                stats["skipped"] += 1
                continue
            if not apply:
                print(f"WOULD {label} -> {model}")
                continue
            await enqueue_reprocess_job(
                owner_id=doc["owner_id"],
                document_id=doc["id"],
                provider_api_key=key,
                embedding_model=model,
            )
            print(f"QUEUED {label} -> {model}")
            stats["enqueued"] += 1
    finally:
        await close_db()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="enqueue jobs (default: dry run)")
    parser.add_argument("--openai-model", help="override target model for OpenAI documents")
    parser.add_argument("--gemini-model", help="override target model for Gemini documents")
    args = parser.parse_args(argv)
    stats = asyncio.run(
        run(apply=args.apply, overrides={"openai": args.openai_model, "gemini": args.gemini_model})
    )
    mode = "applied" if args.apply else "dry run"
    print(
        f"[{mode}] flagged={stats['flagged']} enqueued={stats['enqueued']} skipped={stats['skipped']}"
        + ("" if args.apply else "  (re-run with --apply; the worker must be running)")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
