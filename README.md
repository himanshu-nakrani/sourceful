# Document RAG

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-20%2B-339933?logo=node.js)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)

A **self-hostable, production-ready document question-answering (RAG) application** that lets you upload documents, ask questions in natural language, and receive grounded, cited answers powered by your own OpenAI or Google Gemini API key.

### Key Highlights

- **Bring Your Own Key (BYOK)** — works with OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) or Google Gemini (`gemini-2.0-flash`, `gemini-embedding-001`). No vendor lock-in.
- **Streaming answers with citations** — responses stream via Server-Sent Events and include chunk IDs, similarity scores, and page references for full traceability.
- **Durable ingestion pipeline** — documents are processed by a background worker with job tracking, retries, and progress stages; no fire-and-forget.
- **Multi-format document support** — ingest PDF, DOCX, TXT, Markdown, CSV, XLSX, PPTX, and HTML files.
- **Advanced retrieval (optional)** — hybrid dense + lexical search (RRF), cross-encoder reranking, GraphRAG entity traversal, agentic planner-tool loop, and rolling conversation memory — all behind feature flags, off by default.
- **Multi-tenant workspaces** — RBAC roles (owner / admin / editor / viewer), shareable links, and per-workspace usage quotas.
- **Cloud connectors** — sync from Google Drive, Notion, Confluence, and S3 on a schedule.
- **Notebook UX** — split-pane PDF viewer with click-through citations and inline chat.
- **Production-ready** — PostgreSQL + pgvector, Prometheus metrics, health/readiness endpoints, and full Docker Compose orchestration.

## Table of Contents

1. [Features](#features)
2. [Tech Stack](#tech-stack)
3. [Architecture](#architecture)
4. [Prerequisites](#prerequisites)
5. [Supported File Types](#supported-file-types)
6. [Auth Model](#auth-model)
7. [Main API Endpoints](#main-api-endpoints)
8. [Local Development](#local-development)
9. [Docker Compose](#docker-compose)
10. [Environment Variables](#environment-variables)
11. [Quality Gates](#quality-gates)
12. [Advanced Retrieval (Phase 0/1)](#advanced-retrieval-phase-01)
13. [Agentic Retrieval & Memory (Phase 3)](#agentic-retrieval--memory-phase-3)
14. [Cloud Connectors (Phase 4)](#cloud-connectors-phase-4)
15. [Notebook UX (Phase 4)](#notebook-ux-phase-4)
16. [Workspaces & RBAC (Phase 4)](#workspaces--rbac-phase-4)
17. [Usage Metering & Quotas (Phase 4)](#usage-metering--quotas-phase-4)
18. [Production Operations](#production-operations)
19. [CI](#ci)

## Features

| Category | What's included |
|---|---|
| **Document ingestion** | Upload via UI or API; background worker with job status tracking, retries, and per-stage progress |
| **Retrieval** | Dense vector search (pgvector), optional hybrid BM25+dense (RRF), optional cross-encoder reranking, optional GraphRAG traversal |
| **Chat** | Single-response JSON or streaming SSE; structured citations with chunk ID, score, and page; multi-turn conversation history |
| **AI providers** | OpenAI (GPT-4o, GPT-4o-mini, text-embedding-3-small/large) · Google Gemini (gemini-2.0-flash, gemini-embedding-001) |
| **Storage** | PostgreSQL + pgvector (production) · SQLite (local dev fallback) |
| **Auth** | Session-scoped data isolation; BYOK per request; workspace RBAC |
| **Observability** | Prometheus metrics (`/metrics`), health (`/health`), readiness (`/ready`), optional Langfuse tracing |
| **Cloud sync** | Google Drive · Notion · Confluence · S3 |
| **Frontend** | Next.js 16 app with upload, chat, chunk preview, notebook PDF viewer, and conversation management |

## Tech Stack

**Frontend**
- [Next.js 16](https://nextjs.org) (App Router, React 19, TypeScript)
- [Tailwind CSS v4](https://tailwindcss.com) for styling
- [Framer Motion](https://www.framer.com/motion/) for animations
- [react-pdf](https://github.com/wojtekmaj/react-pdf) for the notebook PDF viewer
- [react-markdown](https://github.com/remarkjs/react-markdown) + `remark-gfm` for rendered answers

**Backend**
- [FastAPI](https://fastapi.tiangolo.com) (Python 3.12) with async request handling
- [Uvicorn](https://www.uvicorn.org) ASGI server
- [OpenAI Python SDK](https://github.com/openai/openai-python) and [Google Generative AI SDK](https://github.com/google/generative-ai-python)
- [pypdf](https://github.com/py-pdf/pypdf) + [python-docx](https://python-docx.readthedocs.io) for document parsing
- [sse-starlette](https://github.com/sysid/sse-starlette) for streaming responses
- [psycopg 3](https://www.psycopg.org) for PostgreSQL; [aiosqlite](https://github.com/omnilib/aiosqlite) for local dev

**Storage**
- [PostgreSQL 17](https://www.postgresql.org) + [pgvector](https://github.com/pgvector/pgvector) for production vector storage
- SQLite as a zero-config local development fallback

## Architecture

- `web`: Next.js 16 app for upload, chat, chunk preview, and conversation management.
- `api`: FastAPI service for document CRUD, chat SSE, jobs, metrics, and readiness.
- `worker`: background process that claims queued jobs, extracts text, builds embeddings, and stores chunks.
- `postgres`: primary production datastore with pgvector.
- SQLite remains available as a local-dev fallback when `DATABASE_URL` is not set.

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Node.js | 20 | 22 recommended (used in CI) |
| Python | 3.11 | 3.12 recommended (used in CI) |
| Docker & Docker Compose | any recent version | Required for the full-stack container workflow |
| OpenAI **or** Gemini API key | — | Passed per-request via `X-Provider-Api-Key`; not stored server-side |
| PostgreSQL + pgvector | pg 15+ | Only for production; SQLite is used automatically in local dev when `DATABASE_URL` is unset |

## Supported File Types

The following document formats are accepted for ingestion (configurable via `ALLOWED_FILE_TYPES`):

| Format | Extension |
|---|---|
| PDF | `.pdf` |
| Word document | `.docx` |
| Plain text | `.txt` |
| Markdown | `.md` |
| CSV | `.csv` |
| Excel spreadsheet | `.xlsx` |
| PowerPoint presentation | `.pptx` |
| HTML | `.html`, `.htm` |

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

