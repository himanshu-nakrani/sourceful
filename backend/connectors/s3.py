"""AWS S3 connector for bucket sync."""

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


@register_connector("s3")
class S3Connector(BaseConnector):
    """AWS S3 connector supporting access key and IAM role auth."""

    SOURCE_TYPE = "s3"

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls",
        ".pptx", ".ppt", ".txt", ".md", ".html", ".htm",
        ".csv", ".json", ".xml",
    }

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._credentials = config.credentials or {}
        self._client = None

    def _get_client(self):
        """Lazy-load S3 client."""
        if self._client is not None:
            return self._client

        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 not installed. Install: pip install boto3")

        # Build session with optional credentials
        session_kwargs = {}
        if self._credentials.get("access_key_id"):
            session_kwargs["aws_access_key_id"] = self._credentials["access_key_id"]
        if self._credentials.get("secret_access_key"):
            session_kwargs["aws_secret_access_key"] = self._credentials["secret_access_key"]
        if self._credentials.get("region"):
            session_kwargs["region_name"] = self._credentials["region"]

        session = boto3.Session(**session_kwargs)
        self._client = session.client("s3")
        return self._client

    async def test_connection(self) -> tuple[bool, str | None]:
        """Test by listing buckets or head-bucket on configured bucket."""
        try:
            import asyncio
            client = self._get_client()
            bucket = self._credentials.get("bucket")

            if bucket:
                await asyncio.to_thread(client.head_bucket, Bucket=bucket)
            else:
                await asyncio.to_thread(client.list_buckets)
            return True, None
        except Exception as e:
            return False, str(e)

    async def list_documents(
        self, since: datetime | None = None
    ) -> AsyncIterator[RemoteDocument]:
        """List objects in bucket matching filters."""

        client = self._get_client()
        bucket = self._credentials.get("bucket")
        prefix = self._credentials.get("prefix", "")

        if not bucket:
            raise ValueError("S3 bucket not configured in credentials")

        paginator = client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]

                    # Skip folder placeholders and unsupported extensions
                    if key.endswith("/"):
                        continue

                    ext = "." + key.split(".")[-1].lower() if "." in key else ""
                    if ext not in self.SUPPORTED_EXTENSIONS:
                        continue

                    path = key
                    if not self.should_include(path):
                        continue

                    modified_at = obj.get("LastModified")
                    if since and modified_at and modified_at < since:
                        continue

                    yield RemoteDocument(
                        source_id=f"s3://{bucket}/{key}",
                        source_type=self.SOURCE_TYPE,
                        connector_id=self.config.id,
                        name=key.split("/")[-1],
                        path=path,
                        mime_type=self._guess_mime_type(key),
                        modified_at=modified_at,
                        size_bytes=obj.get("Size"),
                        content_hash=obj.get("ETag", "").strip('"'),
                        metadata={
                            "bucket": bucket,
                            "key": key,
                            "storage_class": obj.get("StorageClass"),
                        },
                    )
        except Exception as e:
            print(f"Error listing S3 objects: {e}")

    def _guess_mime_type(self, key: str) -> str | None:
        """Guess MIME type from extension."""
        import mimetypes
        return mimetypes.guess_type(key)[0]

    async def download_document(self, remote_doc: RemoteDocument) -> bytes:
        """Download object from S3."""
        import asyncio

        client = self._get_client()
        bucket = remote_doc.metadata.get("bucket")
        key = remote_doc.metadata.get("key")

        try:
            response = await asyncio.to_thread(
                client.get_object, Bucket=bucket, Key=key
            )
            return await asyncio.to_thread(response["Body"].read)
        except Exception as e:
            raise RuntimeError(f"Failed to download s3://{bucket}/{key}: {e}")

    async def sync(self, db_session: Any, document_service: Any) -> SyncResult:
        """Perform full sync with S3 bucket."""
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

                    if existing:
                        import hashlib
                        new_hash = hashlib.sha256(content).hexdigest()[:32]
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
