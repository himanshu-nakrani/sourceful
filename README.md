# Document RAG

A self-hostable document question-answering app with a Next.js frontend, FastAPI API, durable background ingestion jobs, PostgreSQL + pgvector storage, and BYOK support for OpenAI or Google Gemini.

## What Changed

- PostgreSQL + pgvector is now the primary production path.
- Document ingestion is durable and worker-backed instead of `asyncio.create_task` fire-and-forget processing.
- The API separates app access control from provider credentials.
- Documents, jobs, chunks, conversations, and messages are scoped to a stable client session.
- Answers stream with structured citations that include chunk ids, similarity scores, and page references.

## Architecture

- `web`: Next.js 16 app for upload, chat, chunk preview, and conversation management.
- `api`: FastAPI service for document CRUD, chat SSE, jobs, metrics, and readiness.
- `worker`: background process that claims queued jobs, extracts text, builds embeddings, and stores chunks.
- `postgres`: primary production datastore with pgvector.
- SQLite remains available as a local-dev fallback when `DATABASE_URL` is not set.

## Auth Model

The app uses two request headers:

- `X-Provider-Api-Key: <OpenAI or Gemini key>`
Required for ingest, reprocess, and chat because the app is BYOK.
- `X-Client-Session: <stable client id>`
Used to isolate data between browser sessions in self-hosted deployments.

The frontend now generates and stores the client session id automatically.

## Main API Endpoints

- `POST /api/ingest`
Queues a document for ingestion and returns `202` with `document_id`, `job_id`, `status`, and `embedding_model`.
- `GET /api/jobs/{job_id}`
Returns job status, stage, progress, attempts, and timestamps.
- `GET /api/documents`
Lists scoped documents.
- `GET /api/documents/{document_id}/chunks`
Returns a chunk preview for the selected document.
- `POST /api/documents/{document_id}/reprocess`
Queues re-embedding or retry processing.
- `POST /api/chat`
Returns a grounded JSON answer `{conversation_id, message_id, sources, content}` in a single response. Keeps the synchronous contract used by most clients.
- `POST /api/chat/stream`
Streams Server-Sent Events as the model generates. Event order: `sources` (with retrieval stage metadata) → many `token` events → `message_saved` → `done`. On error a single `error` event is emitted and the stream ends.
- `PATCH /api/conversations/{conversation_id}`
Renames a conversation.
- `GET /api/conversations/{conversation_id}/export`
Exports a conversation as Markdown or JSON.

## Local Development

### 1. Backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Worker

```bash
.venv/bin/python -m backend.worker
```

### 3. Frontend

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Docker Compose

```bash
docker compose up --build
```

Services started:

- `postgres` on port `5432`
- `api` on port `8000`
- `worker` for durable ingestion
- `web` on port `3000`

## Environment Variables

See `[.env.example](./.env.example)` for the full list. The most important ones are:

- `DATABASE_URL`
- `RATE_LIMIT_RPM`
- `REQUEST_TIMEOUT_SECONDS`
- `MAX_DOCUMENT_BYTES`
- `CHUNK_SIZE`
- `CHUNK_OVERLAP`
- `RAG_TOP_K`
- `WORKER_POLL_INTERVAL_SECONDS`
- `WORKER_HEARTBEAT_TTL_SECONDS`
- `BACKEND_URL`
- `NEXT_PUBLIC_API_URL`
- `CORS_ORIGINS`

## Quality Gates

```bash
npm run lint
npm run build
pytest -q backend/tests           # unit + integration tests
pytest -m eval backend/tests/eval  # golden-set retrieval benchmark -> docs/eval/last_run.json
```

## Advanced Retrieval (Phase 0/1)

All advanced-retrieval stages are behind feature flags and default OFF so the
baseline behavior is unchanged:

- `RETRIEVAL_HYBRID_ENABLED=true` — adds a Postgres `tsvector` lexical lane
fused with the dense lane via Reciprocal Rank Fusion (RRF). Postgres-only.
- `RETRIEVAL_RERANKER_ENABLED=true` — over-fetches `top_k * RERANKER_OVERFETCH_FACTOR`
candidates and reorders them with a cross-encoder reranker. Providers:
`cohere`, `jina`, `bge-local` (requires `sentence-transformers`), `noop`.
- Optional tracing: set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` to export
per-stage spans; otherwise tracing is a zero-cost no-op.

Schema migration v5 adds a generated `content_tsv` column plus a GIN index, and
an HNSW index on `document_chunks.embedding` (IVFFlat fallback on older pgvector).

## Agentic Retrieval & Memory (Phase 3)

Phase 3 ships a planner-tool loop, a rolling conversation memory, per-message
feedback, and a low-confidence hint. Every feature is additive and flag-gated;
defaults keep the Phase-0/1/2 behavior unchanged.

- `RETRIEVAL_AGENT_ENABLED=true` routes `/api/chat` and `/api/chat/stream`
through a planner LLM that iteratively calls tools (`search_chunks`,
`get_document_summary`, `list_documents`, `compare_documents`) until it has
enough grounded chunks — capped by `RETRIEVAL_AGENT_MAX_ITERATIONS`,
`RETRIEVAL_AGENT_MAX_CHUNKS`, and `RETRIEVAL_AGENT_MAX_TOOL_CALLS`. Tool
calls and planner decisions are visible in the existing `stages` payload
and in Langfuse when configured. Cross-document synthesis comes with
`per_document_confidence` per response.
- `MEMORY_ENABLED=true` replaces the last-N chat history slice with a
rolling summary persisted per conversation. Only turns older than
`MEMORY_RECENT_TURNS` are summarized; recent turns stay verbatim. The
summary is injected as a second system message after the primary prompt.
- `POST /api/feedback` records thumbs-up/down + optional comment per
assistant message; `GET /api/feedback/summary` returns counts + recent
rows scoped to the caller. The eval harness can read this table to
incorporate online signal.
- `ACTIVE_LEARNING_HINT_ENABLED=true` (default) surfaces a
`stages.active_learning_hint` payload when retrieval confidence is below
`ACTIVE_LEARNING_SCORE_FLOOR` or the agent abstains, so the UI can render
a “try rephrasing / expand search” nudge.
- `RETRIEVAL_GRAPH_ENABLED=true` turns on the GraphRAG ingestion stack.
After chunk embeddings land, the worker runs an LLM entity/relation
extractor over each document's chunks (with a lexical fallback when
no BYOK key is present), persists to `graph_entities` /
`graph_relations`, then detects communities (Leiden when
`leidenalg`+`python-igraph` are installed, otherwise weakly-connected
components) and writes one-paragraph summaries per community into
`graph_communities`.
- `RETRIEVAL_GRAPH_TRAVERSAL_ENABLED=true` (requires the graph ingest
flag above) adds a third retrieval lane to `/api/chat`. It matches
seed entities in the user's question, expands `RETRIEVAL_GRAPH_HOPS`
hops over `graph_relations`, fetches the chunks that mention the
expanded entities, and RRF-fuses those results with the dense + FTS
lanes. Useful for multi-hop "who / how / why" questions that don't
share keywords with the target chunks.

Schema migration v8 adds `feedback`, `conversation_memory`,
`graph_entities`, and `graph_relations`; migration v9 adds
`graph_communities` + `community_entities`; migration v10 adds
`workspaces`, `workspace_members`, `usage_records`, `prompts`,
`share_links`, and `connectors`.

## Cloud Connectors (Phase 4)

Sync documents from external sources with automatic background polling:

- **Google Drive**: OAuth2 or service account; exports Google Workspace files to Office formats.
- **Notion**: Page export to markdown with block rendering.
- **Confluence**: Space/page sync with HTML export.
- **S3**: Bucket sync with path filtering.

Configure via `POST /api/workspaces/{id}/connectors` with encrypted credentials.
Set `sync_interval_minutes` for automatic polling or trigger manual sync via `POST /api/connectors/{id}/sync`.

## Notebook UX (Phase 4)

Split-pane document viewer with integrated chat:
- PDF rendering with react-pdf
- Resizable panes with drag-to-resize
- Click-through citations jump to page
- Highlight-on-hover for active citations

Access via `/app/documents/{id}/notebook`

## Workspaces & RBAC (Phase 4)

Multi-tenant organization with role-based access:
- **owner**: Full control, can delete workspace
- **admin**: Manage members, edit documents
- **editor**: Upload, edit, delete documents
- **viewer**: Read-only, can chat with documents

Shareable links with token-based access and expiration:
- `POST /api/share` creates shareable link
- Supports document, conversation, or workspace-level sharing
- Permission inheritance: viewer/editor/admin

## Usage Metering & Quotas (Phase 4)

Per-workspace resource tracking:
- Token consumption (input/output)
- Storage bytes used
- API call counts
- Search operations

Quota enforcement:
- `max_storage_bytes` (default 1GB)
- `max_tokens_per_month` (default 1M)
- `max_documents` (default 100)
- `max_members` (default 10)

View usage via `GET /api/workspaces/{id}/usage`

## Production Operations

### Health and readiness

- `GET /health` checks basic process liveness.
- `GET /ready` verifies schema readiness and recent worker heartbeat.
- `GET /metrics` exposes Prometheus-style counters and timing metrics.

### Backup and restore

Example PostgreSQL backup:

```bash
docker compose exec postgres pg_dump -U document_rag document_rag > backup.sql
```

Example restore:

```bash
cat backup.sql | docker compose exec -T postgres psql -U document_rag -d document_rag
```

### Reverse proxy notes

Run the Next.js `web` container behind your reverse proxy and proxy `/api`, `/health`, `/ready`, and `/metrics` to the API service if you expose them separately.

## CI

A GitHub Actions workflow is included to run:

- frontend lint
- frontend production build
- backend tests
- Docker Compose validation
- Docker image smoke builds

