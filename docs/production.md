# Production Notes

## Deployment shape
Recommended deployment for self-hosted usage:
- `web` exposed to users
- `api` internal or reverse-proxied
- `worker` always on
- `postgres` with persistent storage

## Operational checklist
- Set `DATABASE_URL` to PostgreSQL in production.
- Run at least one `worker` instance.
- Back up PostgreSQL regularly.
- Monitor `/ready` and `/metrics`.

## Upgrades
1. Pull the new release.
2. Rebuild images.
3. Restart `api` and `worker` so schema startup checks run against the latest code.
4. Verify `/ready` before opening traffic.

### One-time: anonymous session re-keying (Fix #5)

Releases that introduce signed anonymous sessions change how anonymous data is
scoped. Previously the owner key was `anon:<X-Client-Session header>`; it is now
`anon:<hmac(header)>`, signed with `ANON_SESSION_SECRET`. This secret is
**required in production** (when `DATABASE_URL` is set) — the API refuses to
start without it. Local SQLite dev falls back to `DEFAULT_SUPERUSER_PASSWORD`.
Anonymous data created before this release stays keyed by the old scheme and is
invisible to its owner until re-keyed.

If you have existing anonymous data to preserve:

1. Set `ANON_SESSION_SECRET` to its final production value first (changing it
   later re-scopes anonymous data again).
2. Dry-run the migration to review the plan:
   `python -m backend.scripts.migrate_anon_scopes`
3. Apply it once: `python -m backend.scripts.migrate_anon_scopes --apply`

The script is safe to re-run — already-signed scopes are skipped. If you do not
need to preserve anonymous data, skip this; old rows simply become orphaned.

### One-time: 1536-dim embeddings + HNSW index (schema v16)

All embeddings are now stored at exactly **1536 dimensions** so Postgres can use
a typed `vector(1536)` column with an HNSW cosine index (pgvector cannot index
an undimensioned `vector` column; before v16 the index build always failed and
every query was a sequential scan). Models are asked for 1536 explicitly:

| Provider | Model | How 1536 is produced |
|----------|-------|----------------------|
| OpenAI | `text-embedding-3-small` | `dimensions=1536` (native size) |
| OpenAI | `text-embedding-3-large` | `dimensions=1536` (shortened from 3072) |
| OpenAI | `text-embedding-ada-002` | fixed 1536 (no `dimensions` parameter) |
| Gemini | `models/gemini-embedding-001` | `output_dimensionality=1536`, then L2-normalized (truncated outputs are not unit-length) |

Any other model (e.g. `models/text-embedding-004`, `models/embedding-001`, max
768 dims) is rejected with `UNSUPPORTED_EMBEDDING_MODEL` at upload/reprocess
time, and `/api/models` only lists supported models. The constant lives in
`backend/services/embedding_spec.py`.

**What the migration does on startup** (idempotent; safe to restart mid-way):

1. Adds `documents.reembed_required` (default false).
2. If `document_chunks.embedding` is not yet `vector(1536)`, in one transaction:
   copies every non-1536 vector verbatim into `document_chunk_embeddings_legacy`
   (chunk id, document id, dims, vector), sets those chunks' `embedding` to
   NULL, flags the owning documents (`reembed_required = true`, explanatory
   `last_error`), then changes the column to `vector(1536)`. Chunk text is kept,
   and 1536-dim rows are not touched.
3. Builds `idx_document_chunks_embedding_hnsw` (`vector_cosine_ops`, matching
   the `<=>` operator used by retrieval) if it does not exist; IVFFlat on
   pgvector < 0.5.

The column rewrite and index build take an exclusive lock on `document_chunks`
proportional to its size; on large corpora run the upgrade in a maintenance
window. Flagged documents stay listed but chat on them returns
`409 DOCUMENT_REEMBED_REQUIRED` until re-embedded (multi-document retrieval
skips their chunks). SQLite keeps legacy JSON vectors in place, flags the same
documents, and skips mismatched rows at query time.

**Re-embed flagged documents** (needs the worker running and a provider key):

```bash
python -m backend.scripts.reembed                      # dry run: list + target model
OPENAI_API_KEY=... GEMINI_API_KEY=... python -m backend.scripts.reembed --apply
```

This enqueues one normal reprocess job per document; it re-embeds the stored
chunk text (no re-upload) and clears the flag on success. Documents whose model
cannot do 1536 move to `DEFAULT_EMBEDDING_MODEL_OPENAI` / `_GEMINI` unless you
pass `--openai-model` / `--gemini-model`. Users can also re-embed one document
via `POST /api/documents/{id}/reprocess` (optionally `?embedding_model=...`).
After everything is re-embedded and verified, the archive table can be dropped:
`DROP TABLE document_chunk_embeddings_legacy;`.

**Filtered search recall:** pooled connections run
`SET hnsw.iterative_scan = strict_order` (pgvector >= 0.8) so HNSW keeps
scanning until enough rows pass the document/owner filter. Without it, a
moderately selective filter could return fewer than `top_k` chunks. Behind a
transaction-mode pooler (PgBouncer) session `SET`s may not persist; set it at
the database level instead: `ALTER DATABASE <db> SET hnsw.iterative_scan = strict_order;`.

## Compatibility notes
- SQLite remains supported for local development only.
- Reprocessing a completed document reuses stored chunks unless the latest failed job still has original payload bytes.
- BYOK keys are provided per request. Queued jobs temporarily store the provider key until the worker completes the job.
