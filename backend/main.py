import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.auth import ensure_default_superuser
from backend.database import close_db, fetch_one, init_db, record_heartbeat, require_current_schema
from backend.errors import api_error_payload
from backend.logging_utils import configure_logging
from backend.metrics import metrics
from backend.middleware import RateLimitMiddleware, RequestIdMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware
from backend.routers import analytics, auth, chat, conversations, documents, ingest, users
from backend.routers import jobs as jobs_router
from backend.settings import settings

configure_logging(settings.log_level)
logger = logging.getLogger("ragapp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("api_starting")
        await init_db()
        await require_current_schema()
        await ensure_default_superuser()
        await record_heartbeat("api")
        logger.info("api_started")
        yield
    except Exception:
        logger.exception("api_startup_failed")
        raise
    finally:
        await close_db()
        logger.info("api_stopped")


app = FastAPI(title="Document RAG API", version="2.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, rpm=settings.rate_limit_rpm)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content=api_error_payload(
            error="Internal server error.",
            code="INTERNAL_ERROR",
            request_id=request_id,
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    detail = exc.detail
    if isinstance(detail, dict):
        payload = {
            "error": detail.get("error", "Request failed."),
            "code": detail.get("code", "HTTP_ERROR"),
            "request_id": request_id,
        }
        if detail.get("details") is not None:
            payload["details"] = detail["details"]
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content=api_error_payload(
            error=str(detail),
            code="HTTP_ERROR",
            request_id=request_id,
        ),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content=api_error_payload(
            error="Request validation failed.",
            code="VALIDATION_ERROR",
            request_id=request_id,
            details=exc.errors(),
        ),
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    try:
        await require_current_schema()
        await fetch_one("SELECT 1 AS ok")
        worker = await fetch_one("SELECT updated_at FROM service_heartbeats WHERE service_name = ?", ("worker",))
        if not worker:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not ready",
                    "reason": "worker heartbeat missing",
                    "checks": {
                        "schema": "ok",
                        "database": "ok",
                        "worker_heartbeat": "missing",
                    },
                },
            )
        raw_updated = worker["updated_at"]
        if isinstance(raw_updated, str):
            updated_at = datetime.fromisoformat(raw_updated.replace(" ", "T"))
        else:
            updated_at = raw_updated
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age > settings.worker_heartbeat_ttl_seconds:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not ready",
                    "reason": "worker heartbeat stale",
                    "checks": {
                        "schema": "ok",
                        "database": "ok",
                        "worker_heartbeat": "stale",
                    },
                },
            )
        return {
            "status": "ready",
            "checks": {
                "schema": "ok",
                "database": "ok",
                "worker_heartbeat": "ok",
            },
        }
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "reason": str(exc),
                "checks": {
                    "schema": "error",
                    "database": "error",
                    "worker_heartbeat": "unknown",
                },
            },
        )


@app.get("/metrics")
async def metrics_endpoint():
    return PlainTextResponse(metrics.render_prometheus())


app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(jobs_router.router, prefix="/api")
app.include_router(users.router, prefix="/api")
