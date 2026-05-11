## 2025-05-18 - Offload CPU-bound calculations in async routes
**Learning:** `json.loads` parsing and `numpy` matrix calculations in an asynchronous FastAPI event loop can become CPU bottlenecks, blocking the main thread and slowing down concurrency for web traffic. This was especially noticeable in the fallback SQLite branch for `query_similar` where many chunks are parsed.
**Action:** Use `asyncio.to_thread` for wrapping heavy JSON parsing or NumPy matrix math in async API paths.

## 2026-04-09 - Avoid asyncio.to_thread for small JSON payloads
**Learning:** Offloading simple JSON parsing to `asyncio.to_thread` is an anti-pattern. Thread dispatch and context-switching overhead (~50-100 microseconds) often far exceeds the time saved for typical API response payloads, worsening latency rather than improving it. Additionally, depending on conditional libraries like `orjson` inside application loops without adding them as explicit requirements does not guarantee a performance win.
**Action:** For high-performance JSON deserialization directly into Python objects in an async path, use Pydantic V2's core Rust parser. Pre-compile a `TypeAdapter` at the module level (e.g., `_adapter = TypeAdapter(list[Model])`) and call `_adapter.validate_json(payload)`. This skips the `json.loads` overhead and validates in a single, highly optimized pass.

## 2026-04-10 - Batch Database Operations
**Learning:** In the SQLite/PostgreSQL layer, repeatedly executing single INSERT statements inside a loop (like for document chunks) is significantly slower due to per-query network and database overhead.
**Action:** Use `execute_many` wrapping connection `executemany` calls when dealing with bulk inserts rather than iterating with `await execute`.
## 2024-05-19 - Pydantic TypeAdapter serialization vs json.dumps

**Learning:** `json.dumps()` from the standard library is exceptionally slow when serializing large float arrays (like LLM embeddings) and large lists of object dicts. For Pydantic models and basic types, using a pre-compiled `TypeAdapter(type).dump_json().decode("utf-8")` utilizes pydantic's Rust-backed core to execute an order of magnitude faster (e.g. ~8x faster for an embedding payload), while still avoiding adding an extra required dependency.
**Action:** When serializing JSON into the database (like sources payload or SQLite fallback vectors), prefer `TypeAdapter.dump_json()` or `orjson` when present rather than `json.dumps()`. Keep `TypeAdapter` compilations at the module level to avoid the initial compile overhead at runtime.
## 2026-04-13 - Prevent Streaming Re-renders with React.memo()
**Learning:** During chat generation, state updates for every new token stream cause the entire list of messages to re-render. For components containing heavy markdown parsers (like `ReactMarkdown`) and syntax highlighters (like `SyntaxHighlighter`), this creates significant CPU overhead and UI lag. Because older message objects maintain referential equality in the state array while the active message updates, React's default behavior of re-rendering all children is wasteful.
**Action:** Wrap computationally expensive UI list items (like `MessageBubble` and `SourceCard`) in `React.memo()`. This ensures that previous messages bypass the render phase entirely during active token streaming, resulting in a drastically smoother user experience.
## 2026-04-25 - Avoid TypeAdapter(Any) for fallback serialization
**Learning:** While `TypeAdapter.dump_json()` is very fast, using `TypeAdapter(Any)` as a fallback for generic dictionaries can subtly change the serialization output compared to `json.dumps(..., default=str)`. For instance, it formats datetimes with a strict ISO 8601 'T' separator, whereas `str(datetime)` uses a space. This can cause frontend parsing bugs if the client strictly expects the previous format.
**Action:** When optimizing serialization with `orjson`, always retain the exact original `json.dumps` implementation as the fallback unless you are 100% certain the downstream consumer is format-agnostic.

## 2026-04-28 - Optimize High-Frequency SSE Serialization
**Learning:** For high-frequency Server-Sent Events (SSE) like streaming LLM tokens, general-purpose serialization with fallback parameters (`default=str`, `option=orjson.OPT_PASSTHROUGH_DATETIME`) and repeated string-to-byte encoding (`b"event: " + event_bytes`) introduces significant CPU latency per event.
**Action:** When working with high-frequency SSE streaming, implement a fast-path for the most common events (like simple string tokens) that uses bare `orjson.dumps()` or a pre-compiled Pydantic `TypeAdapter` and concatenates pre-computed byte prefixes directly to minimize overhead.

## 2024-05-08 - Optimized sequential retrieval in _tool_compare_documents
**Learning:** The `compare_documents` tool previously iterated through document IDs sequentially, creating an N+1 retrieval bottleneck because each `await retrieve()` call was blocking. Although the underlying `retrieve` function natively supports batching via `document_ids`, batching aggregates chunks globally. In situations like `compare_documents` where per-document `top_k` granularity and explicit result isolation are required, `asyncio.gather` must be used across individual `retrieve()` calls.
**Action:** When implementing or refactoring features that fetch data for multiple distinct items (like documents) independently, evaluate if they can be parallelized with `asyncio.gather` instead of running in sequential loops to significantly reduce latency.
## 2026-05-10 - Batched Similarity Queries
**Learning:** When retrieving chunks for multiple documents simultaneously using `asyncio.gather` loops, the app suffers from N+1 query overhead which dramatically slows down multi-doc contexts. Instead of firing many individual `LIMIT X` searches, you can rewrite the operation natively using an `IN (...)` query across all documents simultaneously, then handle the `LIMIT` globally or in Python.
**Action:** Always look to batch database operations using `IN (...)` where loops execute individual parameterized queries, as DB aggregation performs vastly better.
## 2024-05-12 - Parallelize Extra Query Lanes to avoid N+1 Execution
**Learning:** In the `retrieval_pipeline.py`, sequentially awaiting `_dense_search` within a loop across multiple extra query lanes (e.g. from HyDE / multi-query transformations) creates an N+1 execution bottleneck that scales linearly with the number of generated extra queries.
**Action:** When a loop contains independent asynchronous I/O operations (such as generating multiple dense searches for pipeline RRF-fusion), always use `asyncio.gather(*tasks)` to dispatch these tasks concurrently. This significantly minimizes overall wait latency and improves batch search parallelism.
