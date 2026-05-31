# Changelog

All notable changes to **Sourceful** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-01

First public release of **Sourceful** — a self-hostable, production-oriented RAG platform for grounded, cited document Q&A. Bring your own OpenAI or Google Gemini key; Sourceful handles ingestion, retrieval, and streaming answers with citations.

### Highlights

- Next.js 16 dashboard + FastAPI backend with a durable background worker for ingestion.
- PostgreSQL + pgvector in production; SQLite fallback for local development.
- Workspaces with role-based access control (owner / admin / editor / viewer).
- Streaming chat with citation objects (chunk id, score, page, excerpt).
- Notebook UX with split-pane PDF viewer and click-through citations.
- Optional advanced RAG lanes behind feature flags: hybrid search, reranking, MMR, query transforms, GraphRAG, agentic retrieval.

### Features

- Durable document ingestion pipeline: upload returns `202`, worker advances `queued → extracting → chunking → embedding → storing → ready`.
- Multi-source workspaces with shared knowledge bases and RBAC enforcement.
- Grounded chat with JSON (`POST /api/chat`) and SSE streaming (`POST /api/chat/stream`).
- Analysis modes: `ask`, `compare`, `extract`, `brief`.
- Conversation persistence and export as Markdown / JSON.
- Notebook view with PDF viewer and citation deep-linking.
- Google OAuth sign-in alongside email/password auth.
- Insights dashboard with trust analytics and workspace metrics.
- User Management, Model Management, and Insights as separate pages.
- Provider key management — keys travel per-request via `X-Provider-Api-Key` and are scoped to queued jobs only.
- Background job worker (`backend/worker.py`) with retries and concurrent-claim safety.
- Multi-doc chat, dynamic model listing, retrieval tuning.
- Connectors for URL ingestion, Notion, and Confluence.
- Eval harness for retrieval recall and answer quality.

### Performance

- Vector search N+1 query eliminated; chunk queries batched for graph traversal.
- Hybrid search lanes executed concurrently with `asyncio.gather`.
- `query_similar_multi` refactored to a single batched database query.
- Document comparison parallelized in agent tools.
- High-frequency SSE token serialization optimized.
- Bulk message inserts use `execute_many` during chat rerun.
- Transformed query embeddings executed concurrently.
- Vectorstore inserts batched during chunking.
- CPU-bound vector similarity offloaded to a thread pool.
- JSON parsing/serialization optimized with Pydantic `TypeAdapter` and `orjson`.
- Trust analytics computation cached and short-circuited.
- React: `NotebookMessageBubble` and chat components wrapped in `React.memo`.
- Deferred imports (`numpy`, `pypdf`) to speed up cold starts.

### Security

- Fixed multiple SSRF vulnerabilities in URL ingestion, auth/models routers, reranker, Notion and Confluence connectors, and `UrlSourceAdapter`.
- Fixed SQL injection in SQLite `PRAGMA` handling.
- Fixed broken function-level authorization on analytics endpoint.
- Removed hardcoded superuser credentials.
- Fixed rate-limit bypass in middleware.
- Added security headers middleware.
- Hardened Google OAuth: explicit token-exchange timeout, deactivated-user checks, verification fixes.
- Disabled server-side prepared statements for Postgres transaction-pooler compatibility.
- Anonymous session persistence and scope hardening.
- Postgres `auth_sessions.revoked` boolean migration.

### UX & Accessibility

- Editorial design system refresh with landing page redesign and global theme overhaul.
- Design audit pass (P0 + P1 + P2): toasts, skeletons, streaming state, research source rail, command palette hints.
- Deep Zinc SaaS theme; dark-glass aesthetic.
- Mobile-responsive layouts across the app.
- Extensive ARIA labels: ChatArea icon buttons, layout toggles, WorkspaceSwitcher, WorkspaceMembersPanel, WorkspaceNotesPanel, SettingsPanel, NotebookView.
- Focus-visible rings added to inputs and AuthScreen buttons.
- `useId()` for programmatic input labels in SettingsPanel.
- `aria-expanded` for collapsible sections, `required` on auth form inputs, `type="email"` on email fields.
- Fixed hydration mismatches, nested buttons, and chat error reporting.

### Documentation

- Comprehensive README with architecture diagrams, API docs, env variables, deployment notes, and security guidance.
- Expanded `.env.example` covering provider keys, OAuth, database, and feature flags.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `AGENTS.md` added.
- Next-phase stabilization plan and advanced-RAG roadmap under `docs/`.
- Docstrings added across RAG modules; CI enforces docstring coverage via interrogate.

### Infrastructure

- Renamed project to **Sourceful**.
- Apache-2.0 license.
- Repo prepared for open-source release.
- Supabase migration; Heroku + Vercel deployment paths documented.
- Structured logging, Prometheus metrics, and automated database migrations.
- Thread-safe database initialization with improved lifespan error handling.
- Backend test suite with integration tests for concurrent job claims.
- Docker / docker-compose setup.

[0.1.0]: https://github.com/himanshu-nakrani/sourceful/releases/tag/v0.1.0
