"""Production middleware for request IDs, datastore-backed rate limits, and logging."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.database import cleanup_rate_limits, upsert_rate_limit
from backend.errors import api_error_payload
from backend.metrics import metrics

logger = logging.getLogger("ragapp")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rpm: int = 60) -> None:  # type: ignore[override]
        super().__init__(app)
        self.rpm = rpm

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in {"/health", "/ready", "/metrics"}:
            return await call_next(request)

        window_start = int(time.time() // 60)
        auth_token = request.headers.get("authorization", "anonymous")[:24]
        client_ip = request.client.host if request.client else "unknown"
        bucket_id = f"{auth_token}:{client_ip}"
        try:
            count = await upsert_rate_limit(bucket_id, window_start)
            await cleanup_rate_limits(window_start - 2)
        except Exception:
            logger.exception("rate_limit_failed")
            metrics.inc("rate_limit_failures_total")
            return await call_next(request)

        if count > self.rpm:
            metrics.inc("rate_limited_requests_total")
            return JSONResponse(
                status_code=429,
                content=api_error_payload(
                    error="Rate limit exceeded. Try again later.",
                    code="RATE_LIMIT_EXCEEDED",
                    request_id=getattr(request.state, "request_id", None),
                ),
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        request_id = getattr(request.state, "request_id", "-")
        logger.info(
            "%s %s %s %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        metrics.inc(
            "http_requests_total",
            method=request.method,
            path=request.url.path,
            status=str(response.status_code),
        )
        metrics.observe(
            "http_request_duration_ms",
            duration_ms,
            method=request.method,
            path=request.url.path,
        )
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
