"""Lightweight tracing facade with optional Langfuse backend.

The tracer is always importable and usable as a context manager. When
Langfuse is configured (env vars set *and* the `langfuse` package is
installed) spans are sent to Langfuse; otherwise every call is a cheap
no-op. Attribute metadata (`update(...)`) is attached to the trace
event and also emitted to structured logs at DEBUG level so that
pipeline stages remain observable even without Langfuse.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

from backend.metrics import metrics
from backend.settings import settings

logger = logging.getLogger("ragapp.tracing")

# Prometheus label values must be plain ASCII. Sanitize span names so we
# don't emit garbage if callers pass dotted or mixed-case identifiers.
_SPAN_LABEL_RE = re.compile(r"[^a-zA-Z0-9_:.]")


def _emit_stage_metrics(name: str, metadata: dict[str, Any]) -> None:
    label = _SPAN_LABEL_RE.sub("_", name) or "unknown"
    elapsed = metadata.get("elapsed_ms")
    if isinstance(elapsed, (int, float)):
        metrics.observe("retrieval_stage_latency_ms", float(elapsed), stage=label)
    hits = metadata.get("hits")
    if isinstance(hits, (int, float)):
        metrics.observe("retrieval_stage_hits", float(hits), stage=label)
    metrics.inc("retrieval_stage_total", stage=label)

_client = None
_initialised = False


def _get_client():
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True
    if not settings.langfuse_configured:
        return None
    try:
        from langfuse import Langfuse  # type: ignore
    except ImportError:
        logger.info("langfuse_not_installed_tracing_disabled")
        return None
    try:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        logger.exception("langfuse_init_failed")
        _client = None
    return _client


class _Span:
    """A single traced span. Always safe to use; metadata is stored lazily."""

    __slots__ = ("name", "metadata", "_started", "_sink", "_handle")

    def __init__(self, name: str, sink):
        self.name = name
        self.metadata: dict[str, Any] = {}
        self._started = time.perf_counter()
        self._sink = sink  # parent span or Langfuse trace handle, or None
        self._handle = None

    def update(self, **fields: Any) -> None:
        self.metadata.update(fields)

    def _elapsed_ms(self) -> float:
        return (time.perf_counter() - self._started) * 1000.0


@contextmanager
def trace(name: str, **initial_metadata: Any) -> Iterator[_Span]:
    """Start a top-level trace. All nested `span(...)` calls attach to it."""
    client = _get_client()
    sink = None
    if client is not None:
        try:
            sink = client.trace(name=name, metadata=initial_metadata or None)
        except Exception:
            logger.exception("langfuse_trace_start_failed")
            sink = None
    span = _Span(name, sink)
    span.metadata.update(initial_metadata)
    try:
        yield span
    finally:
        elapsed_ms = span._elapsed_ms()
        span.metadata.setdefault("elapsed_ms", round(elapsed_ms, 2))
        logger.debug("trace_end name=%s meta=%s", name, span.metadata)
        _emit_stage_metrics(name, span.metadata)
        if sink is not None:
            try:
                sink.update(metadata=span.metadata)
            except Exception:
                logger.exception("langfuse_trace_update_failed")
        if client is not None:
            try:
                client.flush()
            except Exception:
                pass


@contextmanager
def span(parent: _Span | None, name: str, **initial_metadata: Any) -> Iterator[_Span]:
    """Open a child span under an existing trace. Never raises."""
    sink = None
    if parent is not None and parent._sink is not None:
        try:
            sink = parent._sink.span(name=name, metadata=initial_metadata or None)
        except Exception:
            logger.exception("langfuse_span_start_failed")
            sink = None
    child = _Span(name, sink)
    child.metadata.update(initial_metadata)
    try:
        yield child
    finally:
        elapsed_ms = child._elapsed_ms()
        child.metadata.setdefault("elapsed_ms", round(elapsed_ms, 2))
        logger.debug("span_end name=%s meta=%s", name, child.metadata)
        _emit_stage_metrics(name, child.metadata)
        if sink is not None:
            try:
                sink.end(metadata=child.metadata)
            except Exception:
                logger.exception("langfuse_span_end_failed")
