"""Notion connector for workspace sync."""

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


@register_connector("notion")
class NotionConnector(BaseConnector):
    """Notion connector using official API. Exports pages as markdown."""

    SOURCE_TYPE = "notion"

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._token = (config.credentials or {}).get("integration_token")
        self._base_url = "https://api.notion.com/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> tuple[bool, str | None]:
        """Test by querying the user endpoint."""

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._base_url}/users",
                    headers=self._headers(),
                    timeout=30,
                )
                if response.status_code == 200:
                    return True, None
                return False, f"HTTP {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    async def list_documents(
        self, since: datetime | None = None
    ) -> AsyncIterator[RemoteDocument]:
        """List all pages from Notion workspace."""

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        page_cursor = None
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    # Search for pages (excludes databases)
                    body = {
                        "filter": {"value": "page", "property": "object"},
                        "page_size": 100,
                    }
                    if page_cursor:
                        body["start_cursor"] = page_cursor

                    response = await client.post(
                        f"{self._base_url}/search",
                        headers=self._headers(),
                        json=body,
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()

                    for page in data.get("results", []):
                        page_id = page["id"]
                        props = page.get("properties", {})
                        title_prop = props.get("title", {})
                        title = ""
                        if "title" in title_prop:
                            title = "".join(
                                t.get("plain_text", "")
                                for t in title_prop["title"]
                            )
                        if not title:
                            title = f"Untitled ({page_id[:8]})"

                        path = title
                        if not self.should_include(path):
                            continue

                        modified_str = page.get("last_edited_time")
                        modified_at = None
                        if modified_str:
                            try:
                                modified_at = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
                            except ValueError:
                                pass

                        if since and modified_at and modified_at < since:
                            continue

                        created_str = page.get("created_time")
                        created_at = None
                        if created_str:
                            try:
                                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                            except ValueError:
                                pass

                        yield RemoteDocument(
                            source_id=page_id,
                            source_type=self.SOURCE_TYPE,
                            connector_id=self.config.id,
                            name=f"{title}.md",
                            path=path,
                            mime_type="text/markdown",
                            modified_at=modified_at,
                            created_at=created_at,
                            metadata={
                                "url": page.get("url"),
                                "icon": page.get("icon"),
                                "archived": page.get("archived", False),
                            },
                        )

                    page_cursor = data.get("next_cursor")
                    if not page_cursor:
                        break

                except Exception as e:
                    print(f"Error listing Notion pages: {e}")
                    break

    async def _export_page_as_markdown(self, page_id: str) -> str:
        """Export a Notion page as markdown by fetching block content."""

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed")

        blocks = []
        block_cursor = None

        async with httpx.AsyncClient() as client:
            while True:
                url = f"{self._base_url}/blocks/{page_id}/children"
                if block_cursor:
                    url += f"?start_cursor={block_cursor}"

                response = await client.get(
                    url, headers=self._headers(), timeout=30
                )
                response.raise_for_status()
                data = response.json()

                for block in data.get("results", []):
                    md = self._block_to_markdown(block)
                    if md:
                        blocks.append(md)

                block_cursor = data.get("next_cursor")
                if not block_cursor:
                    break

        return "\n\n".join(blocks)

    def _block_to_markdown(self, block: dict) -> str | None:
        """Convert a Notion block to markdown string."""
        block_type = block.get("type")
        content = block.get(block_type, {})

        # Extract rich text
        def get_text(rich_texts: list) -> str:
            return "".join(r.get("plain_text", "") for r in rich_texts)

        rich_text = content.get("rich_text", [])
        text = get_text(rich_text)

        if block_type == "paragraph":
            return text
        elif block_type.startswith("heading_"):
            level = int(block_type.split("_")[1])
            return f"{'#' * level} {text}"
        elif block_type == "bulleted_list_item":
            return f"- {text}"
        elif block_type == "numbered_list_item":
            return f"1. {text}"
        elif block_type == "to_do":
            checked = content.get("checked", False)
            box = "[x]" if checked else "[ ]"
            return f"- {box} {text}"
        elif block_type == "code":
            lang = content.get("language", "")
            return f"```{lang}\n{text}\n```"
        elif block_type == "quote":
            return f"> {text}"
        elif block_type == "divider":
            return "---"
        elif block_type == "image":
            # Try to get image URL
            img_type = content.get("type")
            if img_type == "external":
                url = content.get("external", {}).get("url", "")
                return f"![image]({url})"
            elif img_type == "file":
                url = content.get("file", {}).get("url", "")
                return f"![image]({url})"
        elif block_type == "table":
            # Tables require nested block fetch; mark placeholder
            return "[Table content - see Notion]"
        elif block_type == "child_page":
            title = content.get("title", "Untitled")
            return f"## {title}"
        elif block_type == "link_to_page":
            page_id = content.get("page_id", "")
            return f"[Linked page: {page_id}]"

        # Unsupported block types return None
        return None

    async def download_document(self, remote_doc: RemoteDocument) -> bytes:
        """Export Notion page as markdown bytes."""
        markdown = await self._export_page_as_markdown(remote_doc.source_id)
        return markdown.encode("utf-8")

    async def sync(self, db_session: Any, document_service: Any) -> SyncResult:
        """Perform full sync with Notion workspace."""
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
