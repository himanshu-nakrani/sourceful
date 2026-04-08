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
The app supports two modes:

- Cookie-based optional login (`/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`).
- Legacy anonymous mode with `X-Client-Session` for session-scoped data.

For BYOK provider calls, `X-Provider-Api-Key: <OpenAI or Gemini key>` is still required for ingest, reprocess, and chat.

Admin user management endpoints:
- `GET /api/users`
- `PATCH /api/users/{user_id}`

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
  Streams SSE events: `sources`, `token`, `message_saved`, `done`, and `error`.
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
See [`.env.example`](./.env.example) for the full list. The most important ones are:
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
pytest -q backend/tests
```

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
