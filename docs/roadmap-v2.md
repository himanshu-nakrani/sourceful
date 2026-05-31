# Sourceful — Phase 5+ Roadmap

> **Status:** Phases 0–4 of `advanced-rag-roadmap.md` are complete. This document plans the next 6–12 months.
> **Authored:** 2026-06-01 · v0.1.0 just shipped · 2 GitHub stars
> **Source material:** competitor analysis of 13 OSS RAG platforms + adoption-pattern research across 10 breakout OSS projects.

---

## TL;DR

Sourceful's engine is already competitive with Onyx, RAGFlow, and AnythingLLM on retrieval sophistication. What it lacks is (a) **adoption-blocking parity features** the self-host crowd treats as table stakes, (b) **operational polish** that turns a 1k-star repo into a 10k-star one, and (c) **distribution surfaces** beyond the web UI.

The plan below has three concurrent tracks, each with a clear acceptance bar:

| Track | Goal | Acceptance bar |
|---|---|---|
| **A. Stabilize** | Make v0.1.x boringly reliable | Zero P0 issues open >7 days; upgrade path with migration tooling; ingestion never silently fails |
| **B. Close parity gaps** | Stop losing prospects to "does it support X?" | Local models, MCP server, web search, multimodal, SSO — all shipped |
| **C. Build distribution** | Reach r/LocalLLaMA + r/selfhosted + HN audiences | Hosted playground live; one viral demo asset; 2 distribution surfaces beyond web UI |

The single biggest insight from competitor research: **Onyx, the closest analog, gates SSO/RBAC/audit behind an Enterprise paywall.** That's Sourceful's wedge. "All the Onyx features, none of the upsell" is positioning that writes itself — provided the features actually exist.

---

## Track A — Stabilize (Months 1–2)

The universal complaint across every competitor's issue tracker is **"setup, upgrades, and operational gotchas eat me alive."** Quivr lost mindshare over slow upload UX (issue #138 open for years). R2R's v2→v3 broke users. RAGFlow's v0.20+ broke prior agents. This is Sourceful's opportunity to win on reliability before anyone notices it's quiet.

### A1. Ingestion observability & failure modes
- **Streaming progress per stage** — chunks extracted / embedded / indexed surfaced as percentages, not just a state name. Phase 2.8 added `progress_detail`; expose it in the UI as a live progress bar.
- **Retry & resume UX** — failed jobs need a "retry from stage X" button, not "delete and re-upload."
- **Per-document health** — surface index coverage (% of chunks embedded vs total), embedding model used, last successful query. RAGFlow's chunking visualization is the bar to beat.
- **Backpressure** — when worker is overloaded, queue depth and ETA shown to user.

### A2. Migration tooling
- `sourceful migrate` CLI that runs schema migrations idempotently, with `--dry-run` and `--rollback`.
- Per-release migration notes auto-generated from `migrations.py`.
- Test matrix: fresh DB, v0.1.0 → v0.x upgrade, v0.x → v0.y skip-version upgrade.
- **Why this matters:** R2R lost users specifically because v2→v3 needed manual scripting. Don't repeat that.

### A3. Stable upgrade contracts
- Versioned `/api/*` endpoints; deprecation warnings ship at least one minor before removal.
- Feature flag changes (default flips) called out in CHANGELOG as **BREAKING** when they alter answer behavior.
- Document the upgrade story in `docs/UPGRADING.md`.

### A4. Hardening
- Default rate limits per workspace, not just per IP.
- Circuit breaker on provider calls (OpenAI/Gemini outage shouldn't 500 the whole app).
- Connection pool tuning + Postgres advisory locks for worker claims (already partial — finish the audit).
- Add a `/healthz` + `/readyz` distinction; readyz checks DB + worker liveness + provider reachability.

### A5. Test surface
- E2E test: upload → ingest → query → verify citation → delete. Must run on every PR.
- Backwards-compat smoke test against last 3 minor releases.
- Eval gate enforced in CI: a PR that drops recall@5 by >1pp gets a 🚨 comment, not a silent merge.

**Acceptance for Track A:**
- Zero P0 (data-loss / silent-failure) issues open >7 days.
- Documented upgrade path from v0.0.x → v0.1.x verified by a fresh contributor.
- p95 `/api/chat` ≤ 2.5s on a 1k-document corpus.
- All advanced RAG flags can be toggled in production without restart.

---

## Track B — Close parity gaps (Months 2–6)

These are features competitors universally ship that Sourceful doesn't. Each is a discrete adoption blocker.

### B1. Local-model support (CRITICAL — Month 2)
Every serious competitor — Onyx, AnythingLLM, RAGFlow, kotaemon, Khoj, Open WebUI, PrivateGPT — supports Ollama + vLLM. Sourceful is BYOK OpenAI/Gemini only. This single gap blocks r/LocalLLaMA, the EU privacy market, and any air-gapped deployment.

- **OpenAI-compatible endpoint adapter** — one provider class that points at any `OPENAI_BASE_URL`. This unlocks Ollama, LM Studio, vLLM, Groq, Together, Anyscale, OpenRouter, all at once.
- **Embedding model variety** — bge-large, nomic-embed-text, gte-large via local serving; document the recall@5 vs OpenAI text-embedding-3-small tradeoff.
- **Local reranker** — bge-reranker-v2-m3 as a Docker side-car; already mentioned in the roadmap as the no-API-key option.
- **Smoke tests** — CI matrix that boots Ollama and verifies the full ingest → chat pipeline against `llama3.1:8b` + `nomic-embed-text`.

**Marketing angle:** A blog post titled "Sourceful with Ollama: fully air-gapped RAG" is a one-shot Show HN re-launch. Khoj timed their HN post to Llama 2; Sourceful can time this to whatever model drops in Q3.

### B2. MCP server (HIGH — Month 2)
Onyx, RAGFlow, Haystack all shipped MCP in late 2025 / early 2026. Claude Desktop / Cursor / Cline can query Sourceful's corpus as a tool. This is becoming table stakes.

- **Server**: expose `search_chunks`, `get_document`, `list_documents`, `compare_documents` as MCP tools.
- **Auth**: workspace-scoped token; respects existing RBAC.
- **Distribution**: publish to the Anthropic MCP registry + write a setup blog post.

### B3. Web search fallback (HIGH — Month 3)
NotebookLM's Nov 2025 Deep Research, Onyx's Serper/Brave/SearXNG, R2R's deep research — pure-corpus RAG looks dated. Add a tool the agent loop can call when the corpus answer is low-confidence.

- Pluggable provider: SearXNG (default, self-hosted), Brave, Tavily, Serper.
- Feature flag `WEB_SEARCH_ENABLED`; off by default to preserve "your data, your machine" positioning.
- Surface "answered from web vs corpus" in the citation rail.

### B4. Multimodal ingestion (MEDIUM — Months 3–4)
Phase 2.5 was deferred. RAGFlow (PDF/DOCX images), R2R (.png, .mp3), Cognita (audio/video), Open WebUI (Whisper) all do this.

- **Images in PDFs/DOCX** — VLM caption + embed via Gemini Vision or local LLaVA / Qwen-VL. Store as `chunk_type=image` (schema already has `chunk_type`).
- **Audio** — Whisper-based transcription pipeline; surface as a regular document with timestamp-anchored chunks.
- **Tables** — already partial. Finish: detect, render in chat with row/column citations.
- **Diagrams** — defer to Phase 6; needs more infra.

### B5. Connector breadth (MEDIUM — ongoing)
Sourceful has 4 connectors (Notion, Confluence, GDrive, S3). Onyx has 50+; Open WebUI added OneDrive/SharePoint. Connector count is Onyx's moat and the #1 reason teams pick it.

Priority queue (top of business demand):
1. **Slack** (export + live-sync) — most-requested integration in r/selfhosted RAG threads.
2. **GitHub / GitLab** — code + issues + wikis.
3. **Web crawler** — Firecrawl-style site ingestion with robots.txt respect.
4. **Email (IMAP)** — privacy-sensitive teams love this.
5. **SharePoint / OneDrive** — Microsoft shops are huge in self-hosted enterprise.
6. **Jira** — frequent ask from devtool teams.
7. **Salesforce, Zendesk, HubSpot** — once a few SaaS users land.

Build them as `BaseConnector` subclasses with shared sync primitives (incremental, delta detection, retry, RBAC inheritance). One connector / 2 weeks is achievable.

### B6. SSO / SCIM (MEDIUM — Month 4)
Onyx's biggest critique: SSO/RBAC/audit behind a paywall. Sourceful can ship it Apache-2.0 and own that positioning.

- **OIDC** first (Google, Okta, Authentik, Keycloak). Token validation, group→role mapping.
- **SAML** second (one quarter later) — bigger surface, fewer users.
- **SCIM** for user provisioning — Open WebUI has this.
- Document the "free SSO" story explicitly in README + a launch post.

### B7. Web crawler
The web search story (B3) is reactive; the crawler (B5.3) is proactive. Both matter. Worth a `firecrawl-lite` style submodule.

---

## Track C — Differentiate & distribute (Months 1–12, parallel)

Closing parity is necessary but not sufficient. Sourceful also needs a **DeepDoc-equivalent**: the one feature people quote when recommending it.

### C1. Pick the "owned moat" feature
Competitor research identified the genuine differentiator: **the retrieval-quality stack + eval + observability, fully open, no paywall.** That's a positioning statement, not a feature. The product features that prove it:

| Candidate | Why it could be the moat | Risk |
|---|---|---|
| **Built-in RAGAS eval harness with visible deltas per release** | Verba marks eval "planned"; Onyx/RAGFlow/AnythingLLM/kotaemon have nothing native. "See your recall@5 improve every release." | Hard to demo in 60s |
| **Groundedness verifier (already shipped, under-marketed)** | The "47% of GenAI users hit a negative consequence" stat drives demand for verified output. None of the 13 competitors ship this layer. | Needs UI work — ungrounded spans should glow red |
| **Compliance-native RAG (audit lineage on every answer)** | EU AI Act enforcement Aug 2 2026. No OSS competitor positions here. | Adds product surface; SOC2/ISO are paperwork-heavy |
| **Chunking visualization (RAGFlow's hook)** | Visual "explainability" sells. RAGFlow rode this to 81k stars. | Already a crowded angle |

**Recommendation:** lead with **"eval + groundedness verification as first-class UI."** Build a "Trust Panel" that on every answer shows: chunks retrieved, rerank deltas, groundedness coverage per sentence, latency per stage. Make ungrounded sentences visibly orange. This is the screenshot.

### C2. The 60-second demo asset
Every breakout has one. Sourceful needs one before any launch post.

- **Setup:** real document (an SEC 10-K, a 200-page incident postmortem, or a scanned invoice).
- **Action:** ask a question that requires multi-hop reasoning across pages.
- **Payoff (first 15s):** cited answer with click-through to the PDF page; trust panel showing each sentence is grounded.
- **Format:** 60s Loom or YouTube, embedded as a GIF in README hero.

### C3. Hosted playground (Month 1)
sourceful.dev/playground. BYOK input + rate-limited free Gateway proxy for users without keys. Pre-seeded with 5 demo documents. Every breakout competitor has this — it's non-negotiable.

Cheapest path: a Vercel deployment of the existing app + a `playground` workspace + Vercel AI Gateway with a per-IP rate limit.

### C4. Distribution surfaces beyond the web UI
Khoj's 6 surfaces (Obsidian, Emacs, browser, mobile, desktop, WhatsApp) are the real reason it's at 35k stars. For Sourceful, in order of ROI:

1. **MCP server** (already in B2). Lowest effort, highest leverage in 2026.
2. **Obsidian plugin** — Khoj's playbook. Underexploited for RAG. Obsidian users are high-intent.
3. **VS Code extension** — query your team's docs from the editor. Continue.dev's path.
4. **CLI** — `sourceful ask "..."` for terminal users.
5. **Slack bot** — once connector exists.
6. **Desktop app** — defer; Tauri wrapper after the above land.

### C5. Content engine
Two posts/month, one technical deep-dive + one ecosystem take. Topics from competitor research:

- "Postgres+pgvector vs Elasticsearch+Qdrant: what we measured." (Concrete benchmarks vs RAGFlow's stack.)
- "Why we built groundedness verification into the core RAG loop."
- "MCP for RAG: what changes when your corpus is a tool."
- "Anthropic Contextual Retrieval, six months in: did it actually help?"
- "The eval-driven RAG release: what shipping recall@5 deltas teaches you."

Cross-post to dev.to, daily.dev, lobste.rs.

### C6. Launch sequencing
Don't fire off the existing launch-posts.md drafts yet. Sequence:

1. **Weeks 1–3:** ship B1 (local models) + C3 (hosted playground) + C2 (demo video) + README rewrite with hero GIF.
2. **Week 4:** seed in r/LocalLLaMA + r/selfhosted with the demo, framed as feedback request, not launch.
3. **Week 5:** Show HN — Tue/Wed 13:00 UTC. Title format: `Show HN: Sourceful – Self-hostable RAG with local models, groundedness verification (Apache-2.0)`. Live in comments 36h.
4. **Week 6:** MCP server (B2) → Show HN re-launch eligible per Continue.dev's playbook.
5. **Month 3:** Obsidian plugin → niche-community launch in Obsidian forum + r/ObsidianMD.
6. **Month 4+:** monthly minor releases with their own launch posts.

---

## Track D — Feature ideas (lower priority, Months 6–12)

Things that would be interesting but aren't blockers. Pick 1–2 only.

### D1. Compliance-native RAG (EU AI Act tailwind)
Aug 2 2026 enforcement is creating real demand. None of the OSS competitors position here.

- **Audit lineage** — every answer stores a verifiable receipt: chunks retrieved, model version, prompt hash, timestamp, user.
- **PII redaction at ingest** — pluggable presidio / Microsoft PII detection.
- **Data residency controls** — per-workspace "documents stored in EU only" enforcement.
- **Export-for-audit** — JSON-LD trace for any conversation.

### D2. Sub-agents (Vectara-style)
Specialized agents per domain (legal, security, finance) that the planner loop dispatches to. Each has its own prompt + tool set + retrieval config.

### D3. Memory/personalization layer
Phase 3.7 shipped conversation memory. Extend to cross-conversation user memory: stable facts about the user injected into the prompt.

### D4. Visual query builder
Dify's 100k stars came from this. For RAG specifically: a UI for composing retrieval lanes ("dense + FTS + rerank, drop chunks below score 0.4, expand graph 2 hops"). Could be the GraphRAG visualization people don't have.

### D5. Model routing / cost optimization
LiteLLM-style fallback chains. Cheap model for first-pass; expensive model for low-confidence answers. Per-workspace cost dashboards.

### D6. Mobile / PWA
The roadmap explicitly excluded native mobile. PWA is fair game and cheap.

### D7. Run_SQL agent tool (deferred from Phase 3.2)
Now that structured extraction shipped in Phase 2.6, this unblocks.

### D8. Embed mode
`<iframe src="sourceful.example.com/embed?workspace=..." />` — for teams that want to put RAG into an existing portal.

---

## What NOT to build

Filtered through competitor analysis — these have a clear winner already, low ROI, or contradict positioning:

- ❌ **A visual workflow builder.** Dify (129k) and n8n own this category. Don't fight on their terrain.
- ❌ **A LangChain-style framework.** That's create-llama / Haystack territory. Sourceful is a product.
- ❌ **Self-hosted LLM inference (vLLM/TGI).** B1 makes Sourceful client-side compatible; running the inference is someone else's job.
- ❌ **Fine-tuning embeddings on-repo.** Off-the-shelf is enough until a 1k-customer plays this card.
- ❌ **Realtime collaborative editing.** Notion territory; not a RAG win.
- ❌ **Native mobile app.** PWA only.
- ❌ **A second vector store.** Postgres+pgvector is the simplicity bet. RAGFlow's vector-DB lock-in is a complaint, not a feature.
- ❌ **Paywall any feature in the OSS core.** That's the whole positioning. Hosted tier can be paid; OSS stays Apache.

---

## Risks & how they bite

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Onyx ships free SSO** and closes the positioning wedge | Medium | High | Ship B6 before mid-year; build content around it now |
| **Solo maintainer burnout** trying to do all 3 tracks | High | High | Track A is the only non-negotiable; B and C move in parallel but at lower velocity |
| **RAG market commoditizes** behind one framework winner | Medium | High | Lean into eval + compliance differentiation, not raw retrieval |
| **Local-model parity attracts compliance-shy enterprises** that then ask for SOC2 | Medium | Medium | Document the road to SOC2 even if not certified; many self-hosted buyers don't require it |
| **A competitor copies the eval-as-first-class-UI angle** | Low | Medium | Move fast on C1; publish blog posts to plant the flag |

---

## Acceptance criteria for "Phase 5+ delivered"

By **2026-12-01** (6 months out):

- ✅ Local-model support: Ollama + OpenAI-compat endpoints work end-to-end. CI proves it.
- ✅ MCP server published; Claude Desktop integration documented.
- ✅ ≥3 new connectors (Slack, GitHub, web crawler).
- ✅ OIDC SSO shipped under Apache-2.0.
- ✅ Hosted playground live with 5 demo documents.
- ✅ One viral asset (60s demo) + Show HN executed.
- ✅ MCP + Obsidian plugin published as separate distribution surfaces.
- ✅ Monthly release cadence sustained for 4 consecutive months.
- ✅ Zero P0 issues open >7 days for 3 consecutive months.
- ✅ Star count ≥1,000 (top-of-funnel signal, not the goal — but the threshold above which the next playbook unlocks).

By **2026-12-01** what's deliberately NOT delivered: native mobile, fine-tuning, workflow builder, second vector DB, SOC2 certification, multi-modal video.

---

## How to use this document

- **Weekly:** pick one task from Track A or B and ship it.
- **Monthly:** publish a release. Update the snapshot section of `advanced-rag-roadmap.md`. Write a blog post.
- **Quarterly:** re-read the competitor section. Things move fast — Onyx may close the SSO gap; a new competitor may appear. Update the table.

Track A is the foundation. Track B unlocks markets. Track C makes them notice. Run them in parallel, but if a week forces a choice, **stabilize first.** A 10k-star repo that loses people on a bad upgrade is harder to recover than a 200-star repo that ships every Tuesday.
