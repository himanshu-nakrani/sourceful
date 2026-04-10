## 2025-05-18 - Offload CPU-bound calculations in async routes
**Learning:** `json.loads` parsing and `numpy` matrix calculations in an asynchronous FastAPI event loop can become CPU bottlenecks, blocking the main thread and slowing down concurrency for web traffic. This was especially noticeable in the fallback SQLite branch for `query_similar` where many chunks are parsed.
**Action:** Use `asyncio.to_thread` for wrapping heavy JSON parsing or NumPy matrix math in async API paths.

## 2026-04-09 - Avoid asyncio.to_thread for small JSON payloads
**Learning:** Offloading simple JSON parsing to `asyncio.to_thread` is an anti-pattern. Thread dispatch and context-switching overhead (~50-100 microseconds) often far exceeds the time saved for typical API response payloads, worsening latency rather than improving it. Additionally, depending on conditional libraries like `orjson` inside application loops without adding them as explicit requirements does not guarantee a performance win.
**Action:** For high-performance JSON deserialization directly into Python objects in an async path, use Pydantic V2's core Rust parser. Pre-compile a `TypeAdapter` at the module level (e.g., `_adapter = TypeAdapter(list[Model])`) and call `_adapter.validate_json(payload)`. This skips the `json.loads` overhead and validates in a single, highly optimized pass.

## 2026-04-10 - Batch Database Operations
**Learning:** In the SQLite/PostgreSQL layer, repeatedly executing single INSERT statements inside a loop (like for document chunks) is significantly slower due to per-query network and database overhead.
**Action:** Use `execute_many` wrapping connection `executemany` calls when dealing with bulk inserts rather than iterating with `await execute`.
