## 2025-05-18 - Offload CPU-bound calculations in async routes
**Learning:** `json.loads` parsing and `numpy` matrix calculations in an asynchronous FastAPI event loop can become CPU bottlenecks, blocking the main thread and slowing down concurrency for web traffic. This was especially noticeable in the fallback SQLite branch for `query_similar` where many chunks are parsed.
**Action:** Use `asyncio.to_thread` for wrapping heavy JSON parsing or NumPy matrix math in async API paths.
