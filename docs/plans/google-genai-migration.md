# Plan: `google-generativeai` → `google-genai`, and `openai` 1.x → current major

Status: **plan only**, no code changed. Written 2026-10-10 against `main` @ 5eff3a3.

## 1. Why now

| SDK | Pinned | Installed | Latest (PyPI, 2026-10-10) | Status |
|---|---|---|---|---|
| `google-generativeai` | `>=0.8.0,<1` | 0.8.6 | 0.8.6 (final) | **Deprecated. All support ended permanently on 2025-11-30.** Critical fixes only before that; no new features (Live API, Veo, `gemini-embedding-2` features). |
| `google-genai` | – | – | 2.29.0 (2026-10-07), Python ≥3.10 | GA, recommended replacement |
| `openai` | `>=1.57.0,<2` | 1.109.1 (last 1.x, 2025-09-24) | **3.28.0** (2026-10-09), Python ≥3.10 | Two majors behind: 2.0.0 (2025-09-30), 3.0.0 (2026-08-12) |

Sources:
- PyPI `google-generativeai` project page ("End-of-Life Date: All support for this repository ended permanently on November 30, 2025"): https://pypi.org/project/google-generativeai/
- Gemini API libraries page, "Legacy libraries … deprecated as of November 30th, 2025; Python `google-generativeai`: Not actively maintained": https://ai.google.dev/gemini-api/docs/libraries
- Official migration guide: https://ai.google.dev/gemini-api/docs/migrate (last updated 2026-09-17)
- Embeddings guide (normalization, `gemini-embedding-2`): https://ai.google.dev/gemini-api/docs/embeddings (last updated 2026-10-09)
- `google-genai` README / `errors.py` / `types.py`: https://github.com/googleapis/python-genai
- OpenAI Python CHANGELOG (2.0.0 and 3.0.0 breaking changes): https://github.com/openai/openai-python/blob/main/CHANGELOG.md

## 2. Inventory of current usage

### `google.generativeai` (all lazily imported inside functions)

| File | Function | What it does | Callers |
|---|---|---|---|
| `backend/services/llm.py` | `stream_gemini_text()` | `genai.configure`, `GenerativeModel(system_instruction=…)`, `start_chat(history).send_message(stream=True)` or `generate_content(stream=True)`. Sync generator, run in a thread. Text via `_extract_gemini_stream_text()` (walks `candidates[].content.parts[].text`, falls back to `.text`, which **raises** `ValueError` mid-stream in the old SDK). | `routers/chat.py` streaming path |
| `backend/services/llm.py` | `gemini_text()` | Same conversion, non-streaming. Maps old SDK `ValueError` from `response.text` (blocked/empty) to a friendly `ValueError`. | `routers/chat.py` ×2, `contextual`, `grounding`, `memory`, `query_transform`, `agent`, `graph`, `graph_communities` (all via `run_in_executor`) |
| `backend/services/embeddings.py` | `embed_texts_gemini_sync()` | **One `embed_content` call per chunk**, `task_type="retrieval_document"`, `output_dimensionality=1536` from `embedding_spec`, then `l2_normalize`, `ensure_dimensions`. | `embed_texts()` via `asyncio.to_thread` |
| `backend/services/embeddings.py` | `embed_query_gemini_sync()` | Same, `task_type="retrieval_query"`. | `embed_query()` |
| `backend/services/structured_extract.py` | `_extract_gemini()` | `GenerativeModel(model).generate_content([prompt], generation_config=GenerationConfig(temperature=0, response_mime_type="application/json"))`, reads `response.text`, `usage_metadata.prompt_token_count/candidates_token_count`. | structured extraction endpoint |

### Not affected (checked)
- `backend/services/extract.py`: no LLM SDK. It uses docling, pypdf, pytesseract, openpyxl, python-pptx and bs4. **No file upload or multimodal Gemini path exists today**, so `genai.upload_file` and image parts need no mapping.
- `backend/services/vertex_search.py`: uses `google-cloud-discoveryengine` (separate package, unaffected).
- Safety settings: **none configured anywhere**. We rely on API defaults; only the "blocked" response handling matters (see §4).
- Retries: no SDK-level retry config. Ingestion retries are app-level (`services/jobs.py` exponential backoff).

### `openai`

| File | Usage |
|---|---|
| `services/llm.py` | `AsyncOpenAI(api_key, timeout)`, `chat.completions.create(stream=False/True)`, reads `choices[0].message.content`, `delta.content`, `delta.refusal` |
| `services/embeddings.py` | `AsyncOpenAI`, `embeddings.create(model, input, dimensions=1536)` |
| `services/structured_extract.py` | **sync** `OpenAI(api_key)` in `asyncio.to_thread`, `response_format={"type":"json_object"}`, `usage.prompt_tokens/completion_tokens` |
| `routers/chat.py` | `from openai import APIError` (3 `except` sites) |
| `routers/models.py` | raw HTTPS to `/v1/models` via httpx (no SDK) |

We use only Chat Completions and Embeddings: **no Responses API, Assistants, tools/function calling, or custom `http_client`.**

### Tests that touch the SDKs
- `test_llm_unit.py`: fake `google.generativeai` module (`GenerativeModel`, `start_chat`, `generate_content`), fake `AsyncOpenAI`.
- `test_embeddings_providers.py`, `test_embedding_dimensions.py`: fake `genai.embed_content` via `patch.dict(sys.modules, {"google", "google.generativeai"})`; `patch.object(emb, "AsyncOpenAI")`.
- ~25 other tests patch our own wrappers (`gemini_text`, `create_openai_text`, `embed_texts`…), so they are **SDK-agnostic and unaffected**.

## 3. API mapping (old → new)

Create one client per call site (cheap) or a small cached factory keyed by API key, since keys are per-request/BYOK:

```python
from google import genai
from google.genai import types, errors
client = genai.Client(api_key=api_key,
                      http_options=types.HttpOptions(timeout=settings.request_timeout_seconds * 1000,  # ms
                                                     retry_options=types.HttpRetryOptions(attempts=3)))
```

| Concern | `google-generativeai` (today) | `google-genai` (target) | Notes |
|---|---|---|---|
| Auth | `genai.configure(api_key=…)` (**process-global!**) | `genai.Client(api_key=…)` | Removes a real race: with BYOK keys, concurrent requests in threads currently overwrite each other's global key. |
| System prompt | `GenerativeModel(model, system_instruction=s)` | `config=types.GenerateContentConfig(system_instruction=s)` | |
| One-shot text | `model.generate_content(prompt)` | `client.models.generate_content(model=…, contents=…, config=…)` | |
| Chat w/ history | `model.start_chat(history=[{"role","parts":[str]}]).send_message(p)` | Simpler: pass the **whole conversation as `contents`** (`[types.Content(role="user"\|"model", parts=[types.Part.from_text(text=…)])…]`) to `generate_content`. `client.chats.create(model, history=…)` also exists. | We rebuild history every request anyway, so stateless `contents` is the cleanest and keeps the existing user-turn merging logic. |
| Streaming | `generate_content(..., stream=True)` iterator | `client.models.generate_content_stream(...)` (sync) or `async for c in await client.aio.models.generate_content_stream(...)` | `chunk.text` returns `None` instead of raising, so `_extract_gemini_stream_text` simplifies. Consider native async (`client.aio`) for chat streaming to drop the thread hop (optional, phase 2). |
| Generation config | `genai.GenerationConfig(temperature, response_mime_type)` | `types.GenerateContentConfig(temperature=0, response_mime_type="application/json")` | |
| Structured output | JSON mode only | Same JSON mode; optionally `response_schema=<pydantic model>` → `response.parsed` | Keep JSON mode for parity; schema is a later improvement. |
| Usage | `response.usage_metadata.prompt_token_count / candidates_token_count` | Same field names on pydantic `usage_metadata` | No change in mapping code. |
| Embeddings | `genai.embed_content(model, content=text, task_type="retrieval_document", output_dimensionality=1536)` → `result["embedding"]` | `client.models.embed_content(model=…, contents=[t1, t2, …], config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=1536))` → `[e.values for e in result.embeddings]` | **Batch the chunk list in one call (per batch) instead of one call per chunk** (big ingestion speedup). Keep `l2_normalize`: docs say `gemini-embedding-001` truncated (non-3072) outputs **must be normalized manually**. Keep `ensure_dimensions`. Task type is uppercase enum in new SDK. |
| Safety | (none set) | `config.safety_settings=[types.SafetySetting(category=…, threshold=…)]` | Nothing to port. Note a behavior change in blocked-response detection (below). |
| Blocked / empty | `response.text` **raises `ValueError`** → we re-raise a friendly `ValueError` | `response.text` returns `None`; inspect `response.prompt_feedback.block_reason` and `candidates[0].finish_reason` (`SAFETY`, `RECITATION`, …) | Must re-implement explicitly or blocked answers silently become `""`. |
| Errors | `google.api_core.exceptions.*` (e.g. `ResourceExhausted`, `InvalidArgument`) leaking as generic `Exception` | `google.genai.errors.APIError` (`.code`, `.message`, `.status`), subclasses `ClientError` (4xx) / `ServerError` (5xx) | Opportunity: map 429/401/400 to the same user-facing errors `chat.py` produces for `openai.APIError`. |
| Retries | implicit api_core defaults | `HttpOptions(retry_options=HttpRetryOptions(attempts, initial_delay, http_status_codes=[429,500,503…]))` | Set explicitly so behavior is known; keep app-level job retries. |
| Timeout | none (!) | `HttpOptions(timeout=<ms>)` | Use `settings.request_timeout_seconds`. Today Gemini calls have **no timeout**. |
| File upload / multimodal | not used | `client.files.upload(file=…)`, `types.Part.from_bytes(data, mime_type)` | N/A today; enables future Gemini-based PDF/image extraction. |

## 4. Breaking risks and mitigations

1. **Blocked responses become empty strings** (new `.text` is `None`, no exception). *Mitigation:* explicit `finish_reason`/`block_reason` check, plus a unit test with a fake blocked response.
2. **Model name format.** Old SDK accepted `models/gemini-embedding-001` and bare names. The new SDK accepts both, but `embedding_spec` strips `models/`, so it should keep working. *Test:* both forms.
3. **`gemini-embedding-2` already passes our allowlist** (`gemini-embedding-` prefix) but (a) **rejects `task_type`**, (b) **aggregates a list of inputs into one embedding** unless each is wrapped in a `Content`, and (c) its space is incompatible with 001 (requires re-embed). This is a latent bug today and becomes real once batching lands. *Mitigation:* in `embedding_spec`, either restrict to `gemini-embedding-001`, or special-case `-2` (no `task_type`, task prefix in text, one `Content` per chunk, auto-normalized). Decide in phase 1; restricting is the safe default.
4. **Embedding numerics must not drift** (stored 1536-dim vectors must stay comparable). Same model + same `task_type` + same `output_dimensionality` + same normalization should give identical vectors. *Verify:* a one-off script embeds ~20 fixed strings with old and new SDK and asserts cosine ≥ 0.9999 before merging phase 1.
5. **Batch limits.** Batching `contents` has per-request limits (count/tokens; 001 input limit 2,048 tokens/text). *Mitigation:* batch size ~100, fall back to smaller batches on `ClientError` 400.
6. **Global `configure()` removal changes concurrency** (a fix, but behavior-visible): per-request keys become isolated.
7. **Thread usage.** The sync client is still fine in `run_in_executor`; don't share a client across event loops if adopting `client.aio`.
8. **Dependency footprint.** `google-genai` requires Python ≥3.10 (we use 3.12 in CI/Docker: OK) and pulls `httpx`, `pydantic`, `websockets`, `google-auth`. Remove `google-generativeai`; this drops a large legacy dep tree (`google-ai-generativelanguage`, `grpcio` via api_core, if nothing else needs them; `discoveryengine` still needs api_core). Check the Docker image size.
9. **OpenAI 3.0 drops `httpx` as an installed dependency (see §5).** Our *runtime* code imports `httpx` directly in 8 modules (`connectors/{notion,confluence,adapter}.py`, `services/{url_ingest,reranker}.py`, `utils/network.py`, `routers/{auth,models}.py`) but `httpx` is only declared in `requirements-dev.txt`. It works today only transitively. **Pin `httpx` in `requirements.txt` before any OpenAI 3.x bump** (google-genai also depends on it, but don't rely on transitive deps).

## 5. OpenAI SDK assessment (1.109 → 3.28)

- **2.0.0 (2025-09-30)**: the only breaking change is that Responses-API `ResponseFunctionToolCallOutputItem.output` / `ResponseCustomToolCallOutput.output` can be a list instead of a string. **We don't use the Responses API → no code impact.**
- **3.0.0 (2026-08-12)**: **HTTPX2 becomes the default HTTP client and `httpx` is no longer installed automatically.** Apps passing custom `httpx` clients/transports must migrate (we don't pass any: `AsyncOpenAI(api_key, timeout)` / `OpenAI(api_key)` only). Impact for us is the transitive-`httpx` issue in §4.9, plus test mocks: our tests patch `AsyncOpenAI` itself, never the transport, so they are unaffected. `fastapi.testclient` still needs `httpx` (dev pin exists).
- APIs we use (`chat.completions.create` incl. streaming deltas + `refusal`, `embeddings.create(dimensions=)`, `response_format=json_object`, `APIError`) are unchanged across 2.x/3.x per the changelog. **Verify in CI** with the existing unit tests plus one live smoke call (manual, BYOK key).
- Optional follow-ups (not required): `structured_extract` could use the async client and `response_format` json_schema / `.parse()` for stricter output.

**Recommendation:** pin `httpx` first, then go straight to `openai>=3.28,<4` (1-line change; 2.x is not a useful stop). If HTTPX2 causes any issue in Docker/CI, use `openai>=2.54,<3` as the fallback.

## 6. Test strategy

- **Existing mocks need rewiring, not rewriting:** `test_llm_unit.py`, `test_embeddings_providers.py`, `test_embedding_dimensions.py` fake the *module* `google.generativeai`. Replace with a fake `google.genai` exposing `Client(api_key, http_options)` → `.models.generate_content / generate_content_stream / embed_content` and pydantic-like response objects (`SimpleNamespace` is enough). Patch at one seam: add `backend/services/gemini_client.py::get_client(api_key)` and patch that in tests (no more `sys.modules` juggling).
- **New tests:** blocked response → friendly error; `errors.APIError(code=429)` mapping in chat; embeddings batching (N texts → 1 call, order preserved, normalization, `ensure_dimensions`); `task_type` uppercase; history conversion (consecutive user turns merged, assistant→`model`); streaming with chunks whose `.text` is `None`; per-request key isolation (two clients, two keys).
- **Parity check (manual, pre-merge):** old-vs-new embedding cosine script (§4.4) and a live chat smoke test with a real Gemini key and an OpenAI key.
- **Suites:** full backend suite on SQLite + the `backend-postgres` CI job; Nightly Eval (`workflow_dispatch`) on the branch since retrieval quality depends on embeddings.

## 7. Rollout order (one PR each)

1. **Deps hygiene (S, ~1h):** add `httpx>=0.27,<1` to `backend/requirements.txt`. No behavior change.
2. **OpenAI → 3.x (S, 2–3h):** bump pin, run suites + Docker build + live smoke. Fallback to 2.x if HTTPX2 issues.
3. **Gemini embeddings → google-genai (M, ~1 day):** `gemini_client.get_client`, batched `embed_content`, keep normalization, restrict/special-case `gemini-embedding-2`, parity script, Nightly Eval. Keep `google-generativeai` installed so 3/4 can land independently.
4. **Gemini chat + streaming + structured extract → google-genai (M, ~1 day):** `gemini_text`, `stream_gemini_text`, `_extract_gemini`; blocked-response handling, timeout/retry options, `errors.APIError` mapping in `chat.py`.
5. **Remove `google-generativeai` (S, ~1h):** drop the pin, grep-guard test (`google.generativeai` must not appear in `backend/`), Docker image size check, CHANGELOG/README.
6. *(Optional)* native async `client.aio` for chat streaming; `response_schema` for structured extraction.

Each step is independently revertible; 3 and 4 can ship in either order.

## 8. Effort estimate

| Step | Size | Estimate |
|---|---|---|
| 1 httpx pin | S | 0.1 day |
| 2 OpenAI 3.x | S | 0.25–0.5 day |
| 3 Gemini embeddings | M | 1 day (incl. parity + eval) |
| 4 Gemini chat/stream/extract | M | 1–1.5 days |
| 5 Remove legacy SDK | S | 0.1 day |
| **Total** | | **≈ 2.5–3.5 engineer-days**, plus reviewer time and one live-key smoke test |

Confidence: high for OpenAI (no API surface we use changed), medium-high for Gemini (well-documented 1:1 mapping; main risks are blocked-response semantics, `gemini-embedding-2`, and batch limits, all covered above).
