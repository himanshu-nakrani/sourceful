"""Google Drive connector using OAuth2 service account or user credentials."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from backend.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    RemoteDocument,
    SyncResult,
)
from backend.connectors.registry import register_connector


@register_connector("google_drive")
class GoogleDriveConnector(BaseConnector):
    """Google Drive connector supporting service account and OAuth2 user flows."""

    SOURCE_TYPE = "google_drive"

    SUPPORTED_MIME_TYPES = {
        # Google Workspace types (exportable)
        "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.google-apps.drawing": "image/png",
        # Binary types (direct download)
        "application/pdf": None,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": None,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": None,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": None,
        "text/plain": None,
        "text/markdown": None,
        "text/html": None,
    }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._credentials = config.credentials or {}
        self._service = None

    def _get_service(self):
        """Lazy-load Google Drive service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise RuntimeError("Google API client not installed. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

        creds_dict = self._credentials
        # Support service account JSON key
        if creds_dict.get("type") == "service_account":
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
        elif creds_dict.get("refresh_token"):
            # OAuth2 user credentials
            from google.oauth2.credentials import Credentials
            credentials = Credentials(
                token=creds_dict.get("token"),
                refresh_token=creds_dict.get("refresh_token"),
                token_uri=creds_dict.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=creds_dict.get("client_id"),
                client_secret=creds_dict.get("client_secret"),
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
        else:
            raise ValueError("Invalid Google Drive credentials: need service_account or refresh_token")

        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return self._service

    async def test_connection(self) -> tuple[bool, str | None]:
        """Test by listing drives (lightweight operation)."""
        try:
            import asyncio
            service = self._get_service()
            # Run sync Google API call in thread pool
            await asyncio.to_thread(service.drives().list(pageSize=1).execute)
            return True, None
        except Exception as e:
            return False, str(e)

    async def list_documents(
        self, since: datetime | None = None
    ) -> AsyncIterator[RemoteDocument]:
        """List all supported documents in the drive."""
        import asyncio

        service = self._get_service()
        page_token = None

        # Build query for modified time if specified
        query_parts = ["trashed=false"]
        mime_filter = " or ".join([f"mimeType='{m}'" for m in self.SUPPORTED_MIME_TYPES.keys()])
        query_parts.append(f"({mime_filter})")

        if since:
            # Google Drive uses RFC 3339 format
            since_str = since.isoformat()
            query_parts.append(f"modifiedTime > '{since_str}'")

        query = " and ".join(query_parts)

        while True:
            try:
                response = await asyncio.to_thread(
                    service.files().list(
                        q=query,
                        pageSize=100,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, size, parents, webViewLink)",
                        pageToken=page_token,
                    ).execute
                )

                for file in response.get("files", []):
                    path = await self._build_path(service, file)
                    if not self.should_include(path):
                        continue

                    modified_at = None
                    if file.get("modifiedTime"):
                        try:
                            modified_at = datetime.fromisoformat(file["modifiedTime"].replace("Z", "+00:00"))
                        except ValueError:
                            pass

                    created_at = None
                    if file.get("createdTime"):
                        try:
                            created_at = datetime.fromisoformat(file["createdTime"].replace("Z", "+00:00"))
                        except ValueError:
                            pass

                    yield RemoteDocument(
                        source_id=file["id"],
                        source_type=self.SOURCE_TYPE,
                        connector_id=self.config.id,
                        name=file["name"],
                        path=path,
                        mime_type=file.get("mimeType"),
                        modified_at=modified_at,
                        created_at=created_at,
                        size_bytes=int(file["size"]) if file.get("size") else None,
                        metadata={
                            "webViewLink": file.get("webViewLink"),
                            "parents": file.get("parents", []),
                        },
                    )

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            except Exception as e:
                print(f"Error listing Google Drive files: {e}")
                break

    async def _build_path(self, service, file_obj: dict) -> str:
        """Build human-readable path from parent chain."""
        import asyncio

        parts = [file_obj["name"]]
        parent_id = file_obj.get("parents", [None])[0]

        # Avoid infinite loops
        visited = {file_obj["id"]}
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            try:
                parent = await asyncio.to_thread(
                    service.files().get(fileId=parent_id, fields="name, parents, id").execute
                )
                if parent.get("name"):  # Skip "My Drive" root for cleaner paths
                    parts.append(parent["name"])
                parent_id = parent.get("parents", [None])[0]
            except Exception:
                break

        return "/".join(reversed(parts))

    async def download_document(self, remote_doc: RemoteDocument) -> bytes:
        """Download or export document content."""
        import asyncio
        from googleapiclient.http import MediaIoBaseDownload

        service = self._get_service()
        mime_type = remote_doc.mime_type or ""
        file_id = remote_doc.source_id

        try:
            if mime_type.startswith("application/vnd.google-apps."):
                # Google Workspace file - export to Office format
                export_mime = self.SUPPORTED_MIME_TYPES.get(mime_type)
                if export_mime:
                    request = service.files().export_media(fileId=file_id, mimeType=export_mime)
                else:
                    raise ValueError(f"Cannot export Google Workspace file: {mime_type}")
            else:
                # Binary file - direct download
                request = service.files().get_media(fileId=file_id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = await asyncio.to_thread(downloader.next_chunk)

            return fh.getvalue()
        except Exception as e:
            raise RuntimeError(f"Failed to download {remote_doc.name}: {e}")

    async def sync(self, db_session: Any, document_service: Any) -> SyncResult:
        """Perform full sync with the drive."""
        started = datetime.now(timezone.utc)
        stats = {"added": 0, "updated": 0, "removed": 0, "failed": 0}
        last_error = None

        try:
            since = self.config.last_sync_at
            async for remote_doc in self.list_documents(since=since):
                try:
                    content = await self.download_document(remote_doc)
                    # Check if document already exists by source_id
                    existing = await document_service.get_by_source_id(
                        db_session, remote_doc.source_id, self.SOURCE_TYPE
                    )

                    if existing:
                        # Update if hash changed
                        import hashlib
                        new_hash = hashlib.sha256(content).hexdigest()[:32]
                        if existing.content_hash != new_hash:
                            await document_service.update_content(
                                db_session, existing.id, content, new_hash
                            )
                            stats["updated"] += 1
                    else:
                        # Create new document
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
                    print(f"Failed to sync {remote_doc.name}: {e}")

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
