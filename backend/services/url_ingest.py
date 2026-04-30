"""Phase 1: URL-backed workspace sources.

Fetches the remote content, detects PDF vs HTML, converts HTML to a plain
text UTF-8 document, and hands the payload to the existing durable ingest
job pipeline. The created workspace_sources row mirrors the document
lifecycle (queued → processing → ready).

The fetch is synchronous-on-enqueue to surface reachability/size problems
up-front while retaining the same chunk/embed/store worker path the rest of
the app already relies on.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.database import fetch_one
from backend.utils.network import prevent_ssrf_hook
from backend.services import workspace_service
from backend.services.jobs import enqueue_ingest_job
from backend.services.provider_auth import provider_requires_api_key
from backend.settings import settings

logger = logging.getLogger("ragapp.url_ingest")

SUPPORTED_SCHEMES = {"http", "https"}
MAX_URL_BYTES = 10 * 1024 * 1024  # 10 MB
FETCH_TIMEOUT_SECONDS = 30.0


class UrlIngestError(Exception):
    """Structured error raised by the URL ingest flow."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise UrlIngestError("URL is required.", code="URL_REQUIRED")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in SUPPORTED_SCHEMES:
        raise UrlIngestError(
            f"Unsupported URL scheme: {parsed.scheme or '(none)'}",
            code="URL_SCHEME_UNSUPPORTED",
            details={"scheme": parsed.scheme},
        )
    if not parsed.netloc:
        raise UrlIngestError("URL is missing a host.", code="URL_HOST_MISSING")
    return url


def _derive_title_from_html(html: str, fallback: str) -> str:
    lowered = html.lower()
    start = lowered.find("<title>")
    if start == -1:
        return fallback
    end = lowered.find("</title>", start + 7)
    if end == -1:
        return fallback
    raw = html[start + 7 : end].strip()
    return raw[:300] or fallback


async def _prevent_ssrf_hook(request: httpx.Request) -> None:
    try:
        await prevent_ssrf_hook(request)
    except RuntimeError as exc:
        raise UrlIngestError(
            "URL resolves to a restricted network.",
            code="URL_RESTRICTED_NETWORK",
            status_code=403,
            details={"host": request.url.host},
        ) from exc


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.extract()
        text = soup.get_text(separator="\n")
    except Exception:  # noqa: BLE001
        # Fall back to naive tag stripping when bs4 isn't importable at runtime.
        import re

        text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
    # Collapse excess whitespace
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


async def _fetch_url(url: str) -> tuple[bytes, str, str]:
    """Fetch a URL and return (raw_bytes, content_type, final_url)."""
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "document-qa-url-ingest/1.0"},
            event_hooks={"request": [_prevent_ssrf_hook]},
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise UrlIngestError(
            f"URL fetch timed out after {FETCH_TIMEOUT_SECONDS}s.",
            code="URL_FETCH_TIMEOUT",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise UrlIngestError(
            f"URL fetch failed: {exc}",
            code="URL_FETCH_FAILED",
            status_code=502,
        ) from exc

    if response.status_code >= 400:
        raise UrlIngestError(
            f"URL responded with HTTP {response.status_code}.",
            code="URL_HTTP_ERROR",
            status_code=502,
            details={"status": response.status_code},
        )

    raw = response.content
    if len(raw) > MAX_URL_BYTES:
        raise UrlIngestError(
            "Remote content exceeds the 10 MB ingest limit.",
            code="URL_CONTENT_TOO_LARGE",
            status_code=413,
            details={"max_bytes": MAX_URL_BYTES, "received_bytes": len(raw)},
        )
    return raw, (response.headers.get("content-type") or "").lower(), str(response.url)


async def refetch_url_source(
    *,
    workspace_id: str,
    owner_scope: str,
    source: dict[str, Any],
    provider_api_key: str | None,
) -> dict[str, Any]:
    """Re-fetch a URL-backed workspace source and enqueue a fresh ingest job.

    Phase 3 sync semantics: the URL is fetched again (so updated content is
    indexed), the underlying document's chunks are replaced via the worker,
    and the workspace_source row's ``last_fetched_at`` / status / sync history
    are updated.
    """
    if source.get("source_type") != "url":
        raise UrlIngestError(
            "Only URL sources support refetch.",
            code="SOURCE_NOT_URL",
        )
    url = source.get("source_url") or ""
    document_id = source.get("document_id")
    if not url or not document_id:
        raise UrlIngestError(
            "URL source is missing url or document binding.",
            code="SOURCE_INVALID",
            status_code=409,
        )

    document = await fetch_one(
        "SELECT * FROM documents WHERE id = ? AND owner_id = ?",
        (document_id, owner_scope),
    )
    if not document:
        raise UrlIngestError(
            "Underlying document not found.",
            code="DOCUMENT_NOT_FOUND",
            status_code=404,
        )

    provider = document["provider"]
    embedding_model = document["embedding_model"]
    if provider_requires_api_key(provider) and not provider_api_key:
        raise UrlIngestError(
            "Missing X-Provider-Api-Key header.",
            code="MISSING_PROVIDER_API_KEY",
            status_code=401,
        )

    from backend.services import sync_runs

    run_id = await sync_runs.start_run(
        workspace_id=workspace_id, source_id=source["id"]
    )

    try:
        raw, content_type, final_url = await _fetch_url(url)
        if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
            mime_type = "application/pdf"
            payload = raw
        else:
            try:
                html_text = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                html_text = raw.decode("latin-1", errors="replace")
            text = _html_to_text(html_text)
            if not text.strip():
                raise UrlIngestError(
                    "URL returned no text content to index.",
                    code="URL_EMPTY_CONTENT",
                )
            mime_type = "text/plain"
            payload = text.encode("utf-8")
    except UrlIngestError as exc:
        await sync_runs.finish_run(
            run_id=run_id,
            source_id=source["id"],
            status="error",
            error_message=str(exc),
        )
        raise

    checksum = hashlib.sha256(payload).hexdigest()

    # Update document payload + reset status, then enqueue a reprocess job that
    # will re-chunk and re-embed the new content.
    from backend.database import execute as _execute
    from backend.services.jobs import enqueue_reprocess_job

    await _execute(
        "UPDATE documents SET file_bytes = ?, mime_type = ?, checksum = ?, status = 'queued', last_error = NULL WHERE id = ? AND owner_id = ?",
        (payload, mime_type, checksum, document_id, owner_scope),
    )
    document, job = await enqueue_reprocess_job(
        owner_id=owner_scope,
        document_id=document_id,
        provider_api_key=provider_api_key or "",
        embedding_model=embedding_model,
    )
    # Mirror status onto the source and stamp last_fetched_at.
    await _execute(
        "UPDATE workspace_sources SET status = 'queued', mime_type = ?, last_fetched_at = "
        + ("NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP")
        + ", updated_at = "
        + ("NOW()" if settings.using_postgres else "CURRENT_TIMESTAMP")
        + " WHERE id = ? AND workspace_id = ?",
        (mime_type, source["id"], workspace_id),
    )
    await sync_runs.finish_run(
        run_id=run_id,
        source_id=source["id"],
        status="success",
        checksum=checksum,
    )
    refreshed = await workspace_service.get_source(source["id"], workspace_id)
    logger.info(
        "url_source_refetched workspace=%s source=%s document=%s job=%s",
        workspace_id,
        source["id"],
        document_id,
        (job or {}).get("id"),
    )
    return refreshed or source


async def enqueue_url_source(
    *,
    workspace_id: str,
    owner_scope: str,
    url: str,
    title: str | None,
    provider: str | None,
    embedding_model: str | None,
    provider_api_key: str | None,
) -> dict[str, Any]:
    clean_url = _validate_url(url)

    # Resolve provider and embedding defaults.
    selected_provider = (provider or "openai").strip().lower()
    if selected_provider not in {"openai", "gemini"}:
        raise UrlIngestError(
            f"Unsupported provider: {selected_provider}",
            code="INVALID_PROVIDER",
            details={"provider": selected_provider},
        )
    if provider_requires_api_key(selected_provider) and not provider_api_key:
        raise UrlIngestError(
            "Missing X-Provider-Api-Key header.",
            code="MISSING_PROVIDER_API_KEY",
            status_code=401,
        )

    model_name = (embedding_model or "").strip()
    if not model_name:
        model_name = (
            settings.default_embedding_model_openai
            if selected_provider == "openai"
            else settings.default_embedding_model_gemini
        )

    raw, content_type, final_url = await _fetch_url(clean_url)

    if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
        mime_type = "application/pdf"
        payload = raw
        filename = title or final_url.rsplit("/", 1)[-1] or "page.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        derived_title = title or filename
    else:
        # Treat everything else as HTML/text.
        try:
            html_text = raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            html_text = raw.decode("latin-1", errors="replace")
        text = _html_to_text(html_text)
        if not text.strip():
            raise UrlIngestError(
                "URL returned no text content to index.",
                code="URL_EMPTY_CONTENT",
            )
        mime_type = "text/plain"
        derived_title = title or _derive_title_from_html(html_text, final_url)
        filename = f"{derived_title[:80] or 'url'}.txt"
        payload = text.encode("utf-8")

    checksum = hashlib.sha256(payload).hexdigest()

    document, job, deduplicated = await enqueue_ingest_job(
        owner_id=owner_scope,
        provider=selected_provider,
        embedding_model=model_name,
        provider_api_key=provider_api_key or "",
        filename=filename,
        mime_type=mime_type,
        checksum=checksum,
        raw=payload,
    )

    # Attach the document to the workspace for cross-feature visibility.
    from backend.database import execute

    await execute(
        "UPDATE documents SET workspace_id = ? WHERE id = ? AND owner_id = ?",
        (workspace_id, document["id"], owner_scope),
    )

    source = await workspace_service.create_source(
        workspace_id,
        source_type="url",
        source_title=derived_title,
        document_id=document["id"],
        source_url=final_url,
        mime_type=mime_type,
        status=document.get("status", "queued"),
        metadata={
            "fetched_content_type": content_type,
            "original_url": clean_url,
            "deduplicated": deduplicated,
            "job_id": job["id"] if job else document.get("current_job_id"),
        },
    )
    logger.info(
        "url_source_enqueued workspace=%s source=%s document=%s deduplicated=%s",
        workspace_id,
        source["id"],
        document["id"],
        deduplicated,
    )
    return source
