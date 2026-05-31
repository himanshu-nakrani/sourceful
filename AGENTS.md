# AGENTS.md

> **Audience:** contributors and AI coding agents working on this repo. This is
> internal developer guidance — code layout, run commands, and testing
> expectations. End-user setup and usage docs live in `README.md`.

## Repository overview

- This repo is a self-hostable document QA/RAG app with a Next.js frontend at the repo root and a FastAPI backend in `backend/`.
- Durable ingestion depends on the background worker in `backend/worker.py`; chat and document upload flows are not fully exercised unless the API and worker are both running.
- PostgreSQL + pgvector is the primary production path, but local development can fall back to SQLite when `DATABASE_URL` is unset.
- `legacy/` contains an older Streamlit prototype. Do not modify it unless the task explicitly targets that app.

## Code map

- `app/`: Next.js App Router pages, layout, global styles, and frontend entrypoints.
- `app/components/`: UI components.
- `app/lib/`: frontend helpers and shared client-side utilities.
- `backend/main.py`: FastAPI entrypoint.
- `backend/routers/`: HTTP routes.
- `backend/services/`: ingestion, chat, storage, and job logic.
- `backend/tests/`: pytest coverage for backend behavior.
- `docs/production.md`: deployment and production-operation notes.
- `docker-compose.yml`: local full-stack orchestration for `web`, `api`, `worker`, and `postgres`.

## Toolchain and setup

- Use Node.js 20+ locally; CI runs Node 22.
- Use Python 3.12 when possible; CI runs Python 3.12.
- Frontend install:
  - `npm ci`
- Backend install for development and tests:
  - `python3 -m venv .venv`
  - .venv/bin/pip install -r backend/requirements.txt
- Copy values from `.env.example` when a task needs explicit local configuration.

## Run commands

- Frontend dev server: `npm run dev`
- Frontend production build: `npm run build`
- Frontend lint: `npm run lint`
- Backend API: `.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
- Background worker: `.venv/bin/python -m backend.worker`
- Full stack via containers: `docker compose up --build`

## Environment notes

- Main frontend/backend wiring uses:
  - `NEXT_PUBLIC_API_URL`
  - `BACKEND_URL`
  - `CORS_ORIGINS`
- Local fallback storage uses:
  - `DATABASE_PATH`
  - `VECTOR_STORE_DIRECTORY`
  - `DOCUMENT_REGISTRY_PATH`
- Production storage should use `DATABASE_URL`.
- Ingest/reprocess/chat requests require a provider key via `X-Provider-Api-Key` (except `vertex_search` ingest + reprocess, which use service-side credentials).
- Data is scoped by `X-Client-Session`; the frontend generates and persists this automatically.

## Testing expectations

- Prefer targeted tests first, then broaden only when the touched code crosses subsystem boundaries.
- Frontend-only changes:
  - Run `npm run lint`.
  - Run `npm run build` if you changed routing, rendering, shared UI primitives, or TypeScript types.
  - Manually verify in the browser for non-trivial UI changes.
- Backend-only changes:
  - Run the most relevant pytest module(s) in `backend/tests/` first.
  - Run `pytest -q backend/tests` before finishing if you changed shared backend behavior, request/response models, ingestion flow, or persistence logic.
- Docker or deployment changes:
  - Run `docker compose config`.
- Full-stack changes affecting upload, ingestion, jobs, or chat:
  - Start the API, worker, and frontend together, or use `docker compose up --build`.
  - Verify the end-to-end flow that exercises the changed code path.

## Change guidance

- Keep fixes scoped; avoid incidental refactors unless they materially reduce risk.
- Preserve the repo's current split between frontend code in the root app and backend code in `backend/`.
- Do not assume chat/upload behavior works from API startup alone; the worker must be running for ingestion progress and durable job handling.
- Avoid committing generated local data unless the task explicitly requires fixture updates.

## Cursor Cloud specific instructions

- Before starting long-running services, check existing terminal sessions so you can reuse an already-running frontend, API, or worker when possible.
- Use tmux-backed sessions for `npm run dev`, `uvicorn`, worker processes, and `docker compose up`.
- For UI changes, perform manual browser testing and capture a demo video artifact.
- For terminal-only changes, include high-signal command output in the final summary.
- Leave dev servers running after testing unless cleanup is required to continue.