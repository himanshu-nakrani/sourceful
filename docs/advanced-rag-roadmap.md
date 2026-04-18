# Advanced RAG Roadmap

> Living plan for upgrading this repo from a well-engineered single-doc RAG app
> into a **state-of-the-art, showcase-quality** agentic document intelligence
> platform. Each phase lands as an independently reviewable PR gated on the
> golden-set eval suite in `backend/tests/eval/`.
>
> **Status legend:** ✅ done · 🚧 in progress · ⏳ pending · ➖ deferred / out of scope

---

## Guiding principles

1. **Measurable quality.** Every new retrieval stage must ship with a pytest
   entry under `-m eval` and a delta against `docs/eval/baseline.json`.
2. **Flag-gated rollout.** New behavior defaults OFF so existing users see no
   regression; flipping one flag upgrades them in place.
3. **Minimal upstream fixes.** Keep PRs scoped; avoid incidental refactors.
4. **Postgres is production.** SQLite stays the dev fallback; Postgres-only
   features (FTS, HNSW) degrade gracefully on SQLite.
5. **BYOK for user LLM keys, server-side for infra keys** (reranker, Langfuse,
   connectors).

---

## Phase 0 — Foundations ✅ COMPLETE

**Goal:** stand up the plumbing that makes every later phase measurable and
reversible.

| # | Task | Status | Location |
|---|---|---|---|
| 0.1 | Feature-flag / settings scaffold (hybrid, reranker, contextual, graph, agent) | ✅ | `backend/settings.py:79-112` |
| 0.2 | Langfuse tracing facade — always importable, no-op when unconfigured | ✅ | `backend/services/tracing.py` |
| 0.3 | Pluggable `retrieval_pipeline.py` orchestrator: `embed → dense → [fts+rrf] → [rerank]` | ✅ | `backend/services/retrieval_pipeline.py` |
| 0.4 | Golden dataset scaffold (3 seed items; extensible) | ✅ | `backend/tests/eval/golden.json` |
| 0.5 | `pytest -m eval` harness with deterministic embeddings + JSON report | ✅ | `backend/tests/eval/test_retrieval_eval.py` |
| 0.6 | Commit baseline eval report | ✅ | `docs/eval/baseline.json` |
| 0.7 | Retrieval debug panel in chat UI (stage chips, per-chunk scores, latency) | ✅ | `app/components/ChatArea.tsx::RetrievalDebugPanel` |
| 0.8 | `/api/chat` JSON response exposes `stages` metadata | ✅ | `backend/routers/chat.py:252-258` |
| 0.9 | Env-var documentation in `.env.example` + README section | ✅ | `.env.example`, `README.md` |

**Acceptance criteria (all met):**
- `pytest -q backend/tests` → 28 passed
- `pytest -m eval backend/tests/eval` → recall@3 = 1.0
- `npm run lint` → 0 new errors
- API + worker + frontend run locally with migration v5 applied cleanly.

---

## Phase 1 — Retrieval quality ✅ COMPLETE

**Goal:** close the quality gap to commercial RAG products on recall, ranking,
latency, and groundedness.

### 1.A — Shipped in the first PR

| # | Task | Status | Location |
|---|---|---|---|
| 1.1 | Real SSE streaming endpoint `/api/chat/stream` (sources → token → message_saved → done) | ✅ | `backend/routers/chat.py::_stream_chat_response` |
| 1.2 | Cross-encoder reranker service with cohere / jina / bge-local / noop providers (fail-open) | ✅ | `backend/services/reranker.py` |
| 1.3 | Hybrid search: Postgres `tsvector` FTS lane + weighted RRF fusion | ✅ | `backend/services/hybrid.py` |
| 1.4 | Migration v5: generated `content_tsv` column + GIN index + HNSW (IVFFlat fallback) on `document_chunks.embedding` | ✅ | `backend/database.py:343-395`, `backend/migrations.py` |
| 1.5 | Unit tests for RRF (weight/dedup/empty lane), reranker (noop/fail-open/reorder), pipeline wiring + over-fetch | ✅ | `backend/tests/test_retrieval_pipeline.py` |
| 1.6 | OpenAI + Gemini streaming generators wired into SSE | ✅ | `backend/services/llm.py:54-107` |

### 1.B — Extensions (all shipped)

| # | Task | Status | Location |
|---|---|---|---|
| 1.7 | **Query transformations**: HyDE, multi-query expansion, step-back questions — parallel lanes; flag-gated via `RETRIEVAL_QUERY_TRANSFORMS` | ✅ | `backend/services/query_transform.py`, `backend/routers/chat.py::_maybe_transform_queries` |
| 1.8 | **Contextual retrieval** (Anthropic 2024): at ingest time, prepend each chunk with an LLM-generated document-level summary before embedding | ✅ | `backend/services/contextual.py`, `backend/services/jobs.py:199-227` |
| 1.9 | **MMR diversification** on fused candidates before top_k cut to reduce redundant chunks | ✅ | `backend/services/mmr.py`, `backend/services/retrieval_pipeline.py:169-192` |
| 1.10 | **Parent-document retrieval**: embed small child windows but return parent windows to the LLM | ✅ | `backend/services/chunking.py::chunk_sections_parent_child`, `backend/services/jobs.py:423-426` |
| 1.11 | **LLMLingua / token-budget compression** of the retrieved context before prompt build | ✅ | `backend/services/compression.py`, `backend/routers/chat.py:200-215` |
| 1.12 | **Groundedness verifier**: second-pass LLM call asserts each sentence maps to a citation; flags ungrounded spans | ✅ | `backend/services/grounding.py`, `backend/routers/chat.py:327-339` |
| 1.13 | **Inline `[n]` citation spans** rendered as clickable pills in `MessageBubble`, with hover preview of the chunk | ✅ | `app/components/MessageBubble.tsx::CitationPills` |
| 1.14 | **RAGAS integration** (if `ragas` installed): faithfulness, answer_relevancy, context_precision alongside our recall@K | ✅ | `backend/tests/eval/test_retrieval_eval.py::test_ragas_metrics_on_golden_set` |
| 1.15 | **Golden set expansion**: 31 items across policy / technical / numeric / multi-hop categories | ✅ | `backend/tests/eval/golden_v2.json` |
| 1.16 | **Nightly eval CI**: GitHub Action running `pytest -m eval` and commenting deltas vs baseline | ✅ | `.github/workflows/eval.yml` |
| 1.17 | **Per-stage latency metrics** to Prometheus `/metrics` endpoint | ✅ | `backend/services/tracing.py::_emit_stage_metrics` |
| 1.18 | **SSE in frontend**: `sendChatStream` with live token rendering + stage event display | ✅ | `app/lib/api.ts::sendChatStream`, `app/components/ChatArea.tsx` |
| 1.19 | **Streaming debug panel**: shows each SSE stage as it arrives with timeline | ✅ | `app/components/ChatArea.tsx::RetrievalDebugPanel` |

**Acceptance criteria for Phase 1 completion:**
- Recall@5 ≥ 0.90 on expanded golden set (baseline today: 1.0 on 3-item toy set)
- Faithfulness ≥ 0.85 per RAGAS
- p95 `/api/chat` latency ≤ 2.5s on 200-chunk corpus with reranker on
- Zero regressions in existing pytest suite

---

## Phase 2 — Document understanding (ingestion upgrades) ✅ COMPLETE

**Goal:** match commercial-grade parsing so tables, figures, equations, and
scanned PDFs are all first-class inputs.

| # | Task | Status | Location |
|---|---|---|---|
| 2.1 | Swap `pypdf` for **Docling** (optional); preserve layout + tables as markdown; pypdf fallback | ✅ | `backend/services/extract.py::_extract_pdf_docling` |
| 2.2 | **Semantic chunking** (BoW cosine breakpoint detection) with fallback to fixed-window chunker; `CHUNK_STRATEGY=semantic\|fixed` | ✅ | `backend/services/chunking.py::chunk_sections_semantic`, `backend/settings.py` |
| 2.3 | **Table-aware chunking**: tables as single chunks with `chunk_type=table`; `metadata_json` per chunk | ✅ | Schema v7 (`chunk_type`, `metadata_json`), `backend/services/vectorstore.py` |
| 2.4 | **OCR for scanned PDFs** via `pytesseract`+`pdf2image`; auto-detect when text < threshold | ✅ | `backend/services/extract.py::_ocr_pdf_pages` |
| 2.5 | **Multimodal ingestion**: deferred — requires CLIP/Gemini vision + cross-modal schema | ⏳ | Deferred to Phase 3 |
| 2.6 | **Structured field extraction**: user-defined schema → LLM fills; `POST /documents/{id}/extract` | ✅ | `backend/services/structured_extract.py`, `backend/routers/documents.py` |
| 2.7 | **Advanced formats**: XLSX (sheet-aware), PPTX (slide-level), HTML (DOM-aware + table detection) | ✅ | `backend/services/extract.py::_extract_xlsx`, `_extract_pptx`, `_extract_html` |
| 2.8 | **Progress telemetry**: per-stage `progress_detail` in job status API | ✅ | Schema v7 (`progress_detail`), `backend/services/jobs.py`, `backend/models.py::JobResponse` |
| 2.9 | **Golden-set ingestion tests**: 23 tests covering extraction, validation, and chunking | ✅ | `backend/tests/eval/test_ingestion.py` |

---

## Phase 3 — Agentic + graph retrieval ⏳

**Goal:** handle multi-hop, cross-document, and reasoning-heavy queries that a
single-shot retriever can't answer.

| # | Task | Status | Notes |
|---|---|---|---|
| 3.1 | **Agentic retrieval loop**: planner LLM decides which tool to call (retrieve / filter / expand / ask_user) up to N iterations | ⏳ | New `backend/services/agent.py`; flag `RETRIEVAL_AGENT_ENABLED` |
| 3.2 | **Tool registry**: `search_chunks`, `get_document_summary`, `list_documents`, `compare_documents`, `run_sql` (scoped to extracted tables) | ⏳ | Strict input/output schemas |
| 3.3 | **GraphRAG ingest**: entity + relation extraction (LLM-based), stored in a property graph (networkx → pgvector-compatible table) | ⏳ | Flag `RETRIEVAL_GRAPH_ENABLED` |
| 3.4 | **Community detection + summary**: Leiden clustering on the entity graph; per-community summary chunk indexed alongside raw chunks | ⏳ | Nightly or per-document job |
| 3.5 | **Graph traversal retrieval**: for "who / how / why" queries, expand from seed entities N hops before chunk retrieval | ⏳ | Hybrid with existing dense lane |
| 3.6 | **Cross-document synthesis**: answers that cite ≥2 distinct documents, with per-doc confidence | ⏳ | Extends agent loop |
| 3.7 | **Conversation memory layer**: summarize past turns into a rolling memory; inject as system prefix (replaces naive last-N history) | ⏳ | `backend/services/memory.py` |
| 3.8 | **User feedback loop**: thumbs-up/down per answer → writes to `feedback` table → consumed by eval harness as online signal | ⏳ | UI + backend + schema migration |
| 3.9 | **Active learning hint**: when feedback is negative, auto-surface "try rephrasing" or "expand search" suggestions | ⏳ | UI-only; uses existing stages data |

---

## Phase 4 — Product + ops (showcase polish) ⏳

**Goal:** turn the engine into something that looks and feels like a
production SaaS, ready for demo-day / portfolio review.

| # | Task | Status | Notes |
|---|---|---|---|
| 4.1 | **Connectors**: Google Drive, Notion, Confluence, S3 — each as a background sync job | ⏳ | New `backend/connectors/` package |
| 4.2 | **Notebook UX**: split-pane with PDF viewer + chat, click-through citations scroll to page | ⏳ | Frontend heavy lift; PDF.js |
| 4.3 | **Workspaces + sharing**: multi-user, role-based access, shareable conversation links | ⏳ | Schema: `workspace_id` FK everywhere |
| 4.4 | **Usage metering + quotas**: per-user token / storage counters; `/api/usage` endpoint | ⏳ | Middleware + UI |
| 4.5 | **Prompt library**: saved prompts, per-document templates, team-wide playbooks | ⏳ | New entity + UI |
| 4.6 | **Observability dashboard**: Grafana panels from `/metrics` + Langfuse embed | ⏳ | Ops-only; docs + sample dashboard JSON |
| 4.7 | **Deployment polish**: `docker compose` production profile, Fly.io / Render one-click, HTTPS + OAuth | ⏳ | Infra docs |
| 4.8 | **Demo deployment**: live URL + seeded demo workspace with 10 sample documents | ⏳ | Post-Phase-3 |
| 4.9 | **Landing page** with feature matrix, architecture diagram, eval numbers | ⏳ | Static page under `app/(marketing)/` |
| 4.10 | **Portfolio-ready README**: architecture diagram, benchmarks table, contribution guide, screenshots | ⏳ | Replaces current minimal README |

---

## Decisions locked in (from planning)

- **Runtime:** Postgres + pgvector is production; SQLite dev fallback stays.
- **Embedding:** keep provider-selected (OpenAI / Gemini); add bge-large as a
  third option in Phase 2. No automatic switch on ingest-time language
  detection — user picks.
- **Reranker default:** `cohere` when flag is on (fastest cold start). Users
  with no external keys can pick `bge-local`.
- **Agent loop cap:** 4 iterations; truncate with partial answer + explain.
- **Graph ingest:** runs as a secondary job after chunk embedding completes.
- **BYOK:** user LLM keys never persisted server-side; reranker / Langfuse /
  connector keys live in `.env`.
- **Eval gate:** Phase N PR must not drop any metric on the Phase (N-1)
  baseline by more than 1pp.

---

## Out of scope (explicitly)

- ➖ Fine-tuning embeddings on-repo (use off-the-shelf; revisit in Phase 5).
- ➖ Self-hosted LLM inference (vLLM / TGI). Keep provider calls; users can
  point at any OpenAI-compatible URL if they want.
- ➖ Realtime collaborative editing on documents.
- ➖ Mobile native app. PWA-friendly web only.

---

## Current snapshot (auto-update this section each PR)

- **Last baseline:** `docs/eval/baseline.json` — recall@3 = 1.0 on 3-item toy set
- **Last run:** `docs/eval/last_run.json` — regenerated by `pytest -m eval`
- **Expanded eval:** `docs/eval/last_run_v2.json` — 31-item set with category breakdown
- **RAGAS report:** `docs/eval/last_run_ragas.json` — optional, when `ragas` installed
- **Ingestion tests:** `backend/tests/eval/test_ingestion.py` — 23 tests (20 pass, 3 skip for optional deps)
- **Schema version:** v7 (Postgres + SQLite)
- **Feature flags on by default:** none
- **Phase 1 status:** ✅ COMPLETE (all 19 tasks shipped)
- **Phase 2 status:** ✅ COMPLETE (8 of 9 tasks shipped; 2.5 multimodal deferred)
- **Next up:** Phase 3 — Agentic retrieval
