"""Confluence connector for space/page sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator

from backend.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    RemoteDocument,
    SyncResult,
)
from backend.connectors.registry import register_connector


@register_connector("confluence")
class ConfluenceConnector(BaseConnector):
    """Confluence connector using REST API v2. Supports cloud and server."""

    SOURCE_TYPE = "confluence"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        creds = config.credentials or {}
        self._base_url = creds.get("base_url", "").rstrip("/")
        self._username = creds.get("username", "")
        self._api_token = creds.get("api_token", "")
        self._is_cloud = "atlassian.net" in self._base_url

    def _auth(self) -> tuple[str, str] | dict[str, str]:
        """Return auth for requests."""
        if self._is_cloud:
            # Cloud uses email + API token as basic auth
            return (self._username, self._api_token)
        # Server/Data Center can use PAT or basic auth
        return (self._username, self._api_token)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if not self._is_cloud:
            # For server with PAT, use Bearer
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    def _api_url(self, path: str) -> str:
        """Build full API URL."""
        # Confluence Cloud uses /wiki/rest/api or /wiki/api/v2
        # Confluence Server uses /rest/api
        if self._is_cloud:
            return f"{self._base_url}/wiki/api/v2{path}"
        return f"{self._base_url}/rest/api{path}"

    async def test_connection(self) -> tuple[bool, str | None]:
        """Test by fetching current user or spaces list."""
        import asyncio

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        try:
            async with httpx.AsyncClient() as client:
                auth = self._auth()
                headers = self._headers()

                # Try to get spaces (lightweight)
                response = await client.get(
                    self._api_url("/spaces"),
                    auth=auth if self._is_cloud else None,
                    headers=headers,
                    timeout=30,
                )

                if response.status_code == 200:
                    return True, None
                elif response.status_code == 401:
                    return False, "Authentication failed (401)"
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as e:
            return False, str(e)

    async def list_documents(
        self, since: datetime | None = None
    ) -> AsyncIterator[RemoteDocument]:
        """List all pages from configured spaces."""
        import asyncio

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        # Get spaces to crawl
        space_keys = self.config.options.get("space_keys", []) if self.config.options else []

        async with httpx.AsyncClient() as client:
            auth = self._auth()
            headers = self._headers()

            # If no specific spaces, list all accessible
            if not space_keys:
                try:
                    response = await client.get(
                        self._api_url("/spaces"),
                        auth=auth if self._is_cloud else None,
                        headers=headers,
                        timeout=30,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        space_keys = [s.get("key") for s in data.get("results", [])]
                except Exception as e:
                    print(f"Error listing Confluence spaces: {e}")
                    return

            for space_key in space_keys:
                if not space_key:
                    continue

                cursor = None
                while True:
                    try:
                        # Use pages endpoint with space filter
                        url = self._api_url("/pages")
                        params = {
                            "spaceKey": space_key,
                            "limit": 100,
                            "expand": "version",
                        }
                        if cursor:
                            params["cursor"] = cursor

                        response = await client.get(
                            url,
                            params=params,
                            auth=auth if self._is_cloud else None,
                            headers=headers,
                            timeout=30,
                        )

                        if response.status_code != 200:
                            print(f"Error fetching pages for space {space_key}: {response.status_code}")
                            break

                        data = response.json()

                        for page in data.get("results", []):
                            page_id = page.get("id")
                            title = page.get("title", "Untitled")
                            path = f"{space_key}/{title}"

                            if not self.should_include(path):
                                continue

                            # Get modification time from version
                            version = page.get("version", {})
                            modified_str = version.get("when")
                            modified_at = None
                            if modified_str:
                                try:
                                    modified_at = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
                                except ValueError:
                                    pass

                            if since and modified_at and modified_at < since:
                                continue

                            yield RemoteDocument(
                                source_id=page_id,
                                source_type=self.SOURCE_TYPE,
                                connector_id=self.config.id,
                                name=f"{title}.html",
                                path=path,
                                mime_type="text/html",
                                modified_at=modified_at,
                                metadata={
                                    "space_key": space_key,
                                    "space_name": page.get("spaceId"),
                                    "url": f"{self._base_url}/pages/viewpage.action?pageId={page_id}",
                                    "author": version.get("by", {}).get("displayName"),
                                },
                            )

                        # Pagination
                        links = data.get("_links", {})
                        cursor = None
                        if "next" in links:
                            # Extract cursor from URL
                            next_url = links["next"]
                            if "cursor=" in next_url:
                                cursor = next_url.split("cursor=")[1].split("&")[0]

                        if not cursor:
                            break

                    except Exception as e:
                        print(f"Error processing space {space_key}: {e}")
                        break

    async def download_document(self, remote_doc: RemoteDocument) -> bytes:
        """Download page content as HTML."""
        import asyncio

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        page_id = remote_doc.source_id
        auth = self._auth()
        headers = self._headers()

        async with httpx.AsyncClient() as client:
            # Get page content with body storage
            response = await client.get(
                self._api_url(f"/pages/{page_id}"),
                params={"body-format": "storage"},
                auth=auth if self._is_cloud else None,
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                raise RuntimeError(f"Failed to fetch page {page_id}: {response.status_code}")

            data = response.json()
            body = data.get("body", {}).get("storage", {}).get("value", "")
            title = data.get("title", "Untitled")

            # Wrap in basic HTML structure
            html = f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""
            return html.encode("utf-8")

    async def sync(self, db_session: Any, document_service: Any) -> SyncResult:
        """Perform full sync with Confluence."""
        started = datetime.now(timezone.utc)
        stats = {"added": 0, "updated": 0, "removed": 0, "failed": 0}
        last_error = None

        try:
            since = self.config.last_sync_at
            async for remote_doc in self.list_documents(since=since):
                try:
                    content = await self.download_document(remote_doc)
                    existing = await document_service.get_by_source_id(
                        db_session, remote_doc.source_id, self.SOURCE_TYPE
                    )

                    import hashlib
                    new_hash = hashlib.sha256(content).hexdigest()[:32]

                    if existing:
                        if existing.content_hash != new_hash:
                            await document_service.update_content(
                                db_session, existing.id, content, new_hash
                            )
                            stats["updated"] += 1
                    else:
                        await document_service.create_from_connector(
                            db_session,
                            workspace_id=self.config.workspace_id,
                            connector_id=self.config.id,
                            remote_doc=remote_doc,
                            content=content,
                        )
                        stats["added"] += 1

                except Exception as e:
                    stats["failed"] += 1
                    last_error = str(e)

            status = "success" if stats["failed"] == 0 else "partial"

        except Exception as e:
            status = "error"
            last_error = str(e)

        completed = datetime.now(timezone.utc)

        return SyncResult(
            connector_id=self.config.id,
            started_at=started,
            completed_at=completed,
            status=status,
            documents_added=stats["added"],
            documents_updated=stats["updated"],
            documents_removed=stats["removed"],
            documents_failed=stats["failed"],
            error_message=last_error,
        )
