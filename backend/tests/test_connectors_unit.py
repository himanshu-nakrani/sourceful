"""Connector unit tests with mocked HTTP (httpx.MockTransport) and fake SDKs.

No network: Notion/Confluence go through an httpx MockTransport (the SSRF DNS
hooks are dropped), Google Drive gets a fake ``service`` object and a fake
MediaIoBaseDownload, S3 gets a fake boto3 client.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import patch

import httpx
import pytest

from backend.connectors.base import ConnectorConfig
from backend.connectors.confluence import ConfluenceConnector
from backend.connectors.google_drive import GoogleDriveConnector
from backend.connectors.notion import NotionConnector
from backend.connectors.s3 import S3Connector

_RealAsyncClient = httpx.AsyncClient
UTC = timezone.utc


def _cfg(source_type, credentials=None, **kw) -> ConnectorConfig:
    return ConnectorConfig(id=f"c-{source_type}", source_type=source_type, workspace_id="ws-1",
                           enabled=True, credentials=credentials, **kw)


@pytest.fixture
def http(monkeypatch):
    """Route every httpx.AsyncClient through a handler; record requests."""
    state = {"handler": None, "requests": []}

    def factory(*args, **kwargs):
        kwargs.pop("event_hooks", None)  # SSRF hooks resolve DNS; not wanted offline

        def handle(request):
            state["requests"].append(request)
            return state["handler"](request)

        return _RealAsyncClient(*args, transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return state


class FakeDocService:
    def __init__(self, existing: dict[str, bytes] | None = None, fail_ids=()):
        self.existing = {k: NS(id=f"doc-{k}", content_hash=hashlib.sha256(v).hexdigest()[:32])
                         for k, v in (existing or {}).items()}
        self.created, self.updated, self.fail_ids = [], [], set(fail_ids)

    async def get_by_source_id(self, db, source_id, source_type):
        if source_id in self.fail_ids:
            raise RuntimeError(f"db down for {source_id}")
        return self.existing.get(source_id)

    async def update_content(self, db, doc_id, content, new_hash):
        self.updated.append(doc_id)

    async def create_from_connector(self, db, *, workspace_id, connector_id, remote_doc, content):
        assert workspace_id == "ws-1"
        self.created.append(remote_doc.source_id)


async def _collect(agen):
    return [d async for d in agen]


def run(coro):
    return asyncio.run(coro)


# ============================== Notion ======================================

def _notion_page(pid, *, title_prop="title", title="Page", edited="2026-10-05T10:00:00.000Z"):
    props = {}
    if title_prop:
        props[title_prop] = {"type": "title", "title": [{"plain_text": title}]}
    props["Status"] = {"type": "select", "select": None}
    return {"id": pid, "properties": props, "last_edited_time": edited,
            "created_time": "2026-01-01T00:00:00.000Z", "url": f"https://notion.so/{pid}"}


def _notion_handler(search_pages, blocks=None, fail_search=False):
    def handler(request):
        if request.url.path == "/v1/users":
            return httpx.Response(200, json={"results": []})
        if request.url.path == "/v1/search":
            if fail_search:
                return httpx.Response(500, json={"message": "boom"})
            body = json.loads(request.content)
            idx = int(body.get("start_cursor", "0"))
            nxt = str(idx + 1) if idx + 1 < len(search_pages) else None
            return httpx.Response(200, json={"results": search_pages[idx], "next_cursor": nxt})
        if request.url.path.endswith("/children"):
            pages = blocks or [[]]
            idx = int(request.url.params.get("start_cursor", "0"))
            nxt = str(idx + 1) if idx + 1 < len(pages) else None
            return httpx.Response(200, json={"results": pages[idx], "next_cursor": nxt})
        return httpx.Response(404)
    return handler


def test_notion_test_connection(http):
    conn = NotionConnector(_cfg("notion", {"integration_token": "secret"}))
    http["handler"] = lambda r: httpx.Response(200, json={})
    assert run(conn.test_connection()) == (True, None)
    assert http["requests"][0].headers["authorization"] == "Bearer secret"
    assert http["requests"][0].headers["notion-version"] == "2022-06-28"
    http["handler"] = lambda r: httpx.Response(401, text="unauthorized")
    ok, err = run(conn.test_connection())
    assert not ok and err.startswith("HTTP 401")


def test_notion_lists_pages_across_cursors_with_titles_and_filters(http):
    pages = [
        [_notion_page("aaaaaaaa-1", title="Roadmap"),
         _notion_page("bbbbbbbb-2", title_prop="Name", title="DB row title")],  # database page
        [_notion_page("cccccccc-3", title_prop=None), _notion_page("dddddddd-4", title="Secret plan")],
    ]
    http["handler"] = _notion_handler(pages)
    conn = NotionConnector(_cfg("notion", {"integration_token": "t"}, exclude_paths=["Secret*"]))
    docs = run(_collect(conn.list_documents()))
    assert [(d.source_id, d.name) for d in docs] == [
        ("aaaaaaaa-1", "Roadmap.md"),
        ("bbbbbbbb-2", "DB row title.md"),  # title property is found by type, not by name
        ("cccccccc-3", "Untitled (cccccccc).md"),
    ]
    assert docs[0].modified_at == datetime(2026, 10, 5, 10, tzinfo=UTC)
    assert docs[0].mime_type == "text/markdown" and docs[0].metadata["url"].endswith("aaaaaaaa-1")
    second_search = json.loads(http["requests"][1].content)
    assert second_search["start_cursor"] == "1"


def test_notion_since_filter_accepts_naive_and_aware_timestamps(http):
    pages = [[_notion_page("old", edited="2026-09-01T00:00:00.000Z"), _notion_page("new", edited="2026-10-05T00:00:00.000Z")]]
    http["handler"] = _notion_handler(pages)
    conn = NotionConnector(_cfg("notion", {"integration_token": "t"}))
    for since in (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 1)):  # naive == UTC
        assert [d.source_id for d in run(_collect(conn.list_documents(since=since)))] == ["new"]


def test_notion_markdown_export_paginates_and_maps_blocks(http):
    rt = lambda t: {"rich_text": [{"plain_text": t}]}  # noqa: E731
    blocks = [
        [{"type": "heading_2", "heading_2": rt("Intro")}, {"type": "paragraph", "paragraph": rt("Hello")},
         {"type": "bulleted_list_item", "bulleted_list_item": rt("b")},
         {"type": "numbered_list_item", "numbered_list_item": rt("n")},
         {"type": "to_do", "to_do": {**rt("done"), "checked": True}},
         {"type": "code", "code": {**rt("x = 1"), "language": "python"}}],
        [{"type": "quote", "quote": rt("q")}, {"type": "divider", "divider": {}},
         {"type": "image", "image": {"type": "external", "external": {"url": "https://i/x.png"}}},
         {"type": "table", "table": {}}, {"type": "child_page", "child_page": {"title": "Sub"}},
         {"type": "link_to_page", "link_to_page": {"page_id": "p9"}}, {"type": "unsupported", "unsupported": {}}],
    ]
    http["handler"] = _notion_handler([[]], blocks=blocks)
    conn = NotionConnector(_cfg("notion", {"integration_token": "t"}))
    md = run(conn.download_document(NS(source_id="page-1"))).decode()
    assert md.split("\n\n") == [
        "## Intro", "Hello", "- b", "1. n", "- [x] done", "```python\nx = 1\n```",
        "> q", "---", "![image](https://i/x.png)", "[Table content - see Notion]", "## Sub", "[Linked page: p9]",
    ]


def test_notion_sync_counts_added_updated_unchanged_failed(http):
    rt = {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "same"}]}}
    pages = [[_notion_page("new"), _notion_page("changed"), _notion_page("same"), _notion_page("broken")]]
    http["handler"] = _notion_handler(pages, blocks=[[rt]])
    svc = FakeDocService(existing={"changed": b"old", "same": b"same"}, fail_ids={"broken"})
    result = run(NotionConnector(_cfg("notion", {"integration_token": "t"})).sync(None, svc))
    assert (result.documents_added, result.documents_updated, result.documents_failed) == (1, 1, 1)
    assert result.status == "partial" and "db down" in result.error_message
    assert svc.created == ["new"] and svc.updated == ["doc-changed"]


def test_notion_listing_failure_fails_the_sync(http):
    http["handler"] = _notion_handler([[]], fail_search=True)
    result = run(NotionConnector(_cfg("notion", {"integration_token": "t"})).sync(None, FakeDocService()))
    assert result.status == "error" and "500" in (result.error_message or "")


# ============================ Confluence ====================================

def _conf_page(pid, title, when="2026-10-05T00:00:00.000Z"):
    return {"id": pid, "title": title, "spaceId": "S1", "version": {"when": when, "by": {"displayName": "Ann"}}}


def test_confluence_cloud_vs_server_urls_and_auth(http):
    http["handler"] = lambda r: httpx.Response(200, json={"results": []})
    cloud = ConfluenceConnector(_cfg("confluence", {"base_url": "https://acme.atlassian.net/", "username": "a@x", "api_token": "tok"}))
    assert run(cloud.test_connection()) == (True, None)
    req = http["requests"][-1]
    assert str(req.url) == "https://acme.atlassian.net/wiki/api/v2/spaces"
    assert req.headers["authorization"].startswith("Basic ")
    server = ConfluenceConnector(_cfg("confluence", {"base_url": "https://wiki.corp", "api_token": "pat"}))
    run(server.test_connection())
    req = http["requests"][-1]
    assert str(req.url) == "https://wiki.corp/rest/api/spaces" and req.headers["authorization"] == "Bearer pat"
    http["handler"] = lambda r: httpx.Response(401)
    assert run(server.test_connection()) == (False, "Authentication failed (401)")


def test_confluence_lists_spaces_then_paginates_pages(http):
    def handler(request):
        if request.url.path.endswith("/spaces"):
            return httpx.Response(200, json={"results": [{"key": "ENG"}, {"key": None}]})
        if request.url.params.get("cursor") == "c2":
            return httpx.Response(200, json={"results": [_conf_page("3", "Old", when="2026-01-01T00:00:00.000Z")], "_links": {}})
        return httpx.Response(200, json={"results": [_conf_page("1", "Runbook"), _conf_page("2", "Draft")],
                                         "_links": {"next": "/wiki/api/v2/pages?cursor=c2&limit=100"}})

    http["handler"] = handler
    conn = ConfluenceConnector(_cfg("confluence", {"base_url": "https://acme.atlassian.net", "username": "u", "api_token": "t"},
                                    exclude_paths=["ENG/Draft"]))
    docs = run(_collect(conn.list_documents(since=datetime(2026, 6, 1))))  # naive since == UTC
    assert [(d.source_id, d.path, d.mime_type) for d in docs] == [("1", "ENG/Runbook", "text/html")]
    assert docs[0].metadata["author"] == "Ann" and docs[0].metadata["space_key"] == "ENG"
    page_reqs = [r for r in http["requests"] if r.url.path.endswith("/pages")]
    assert page_reqs[0].url.params["spaceKey"] == "ENG" and page_reqs[1].url.params["cursor"] == "c2"


def test_confluence_download_wraps_and_escapes_title(http):
    http["handler"] = lambda r: httpx.Response(200, json={"title": "Q&A <draft>", "body": {"storage": {"value": "<p>Body</p>"}}})
    conn = ConfluenceConnector(_cfg("confluence", {"base_url": "https://wiki.corp", "api_token": "t"}))
    html = run(conn.download_document(NS(source_id="42"))).decode()
    assert "<title>Q&amp;A &lt;draft&gt;</title>" in html and "<h1>Q&amp;A &lt;draft&gt;</h1>" in html
    assert "<p>Body</p>" in html
    assert http["requests"][0].url.params["body-format"] == "storage"
    http["handler"] = lambda r: httpx.Response(404)
    with pytest.raises(RuntimeError, match="404"):
        run(conn.download_document(NS(source_id="42")))


def test_confluence_page_listing_failure_fails_the_sync(http):
    http["handler"] = lambda r: httpx.Response(503)
    conn = ConfluenceConnector(_cfg("confluence", {"base_url": "https://wiki.corp", "api_token": "t"}, options={"space_keys": ["ENG"]}))
    result = run(conn.sync(None, FakeDocService()))
    assert result.status == "error" and "503" in (result.error_message or "")


def test_confluence_sync_adds_pages(http):
    def handler(request):
        if request.url.path.endswith("/pages"):
            return httpx.Response(200, json={"results": [_conf_page("1", "Runbook")]})
        return httpx.Response(200, json={"title": "Runbook", "body": {"storage": {"value": "x"}}})

    http["handler"] = handler
    conn = ConfluenceConnector(_cfg("confluence", {"base_url": "https://wiki.corp", "api_token": "t"}, options={"space_keys": ["ENG"]}))
    svc = FakeDocService()
    result = run(conn.sync(None, svc))
    assert result.status == "success" and svc.created == ["1"]


# ============================ Google Drive ==================================

class FakeDrive:
    def __init__(self, pages, parents=None, fail_list=False):
        self.pages, self.parents, self.fail_list = pages, parents or {}, fail_list
        self.list_calls, self.export_calls, self.media_calls = [], [], []

    def files(self):
        return self

    def drives(self):
        return NS(list=lambda pageSize: NS(execute=lambda: {"drives": []}))

    def list(self, **kw):
        self.list_calls.append(kw)

        def execute():
            if self.fail_list:
                raise RuntimeError("quota exceeded")
            return self.pages[int(kw.get("pageToken") or 0)]

        return NS(execute=execute)

    def get(self, fileId, fields):
        return NS(execute=lambda: self.parents[fileId])

    def export_media(self, fileId, mimeType):
        self.export_calls.append((fileId, mimeType))
        return f"export:{fileId}".encode()

    def get_media(self, fileId):
        self.media_calls.append(fileId)
        return f"media:{fileId}".encode()


class FakeDownloader:
    """Mimics MediaIoBaseDownload: writes the 'request' bytes in two chunks."""

    def __init__(self, fh, request):
        self.fh, self.data, self.step = fh, request, 0

    def next_chunk(self):
        half = len(self.data) // 2
        self.fh.write(self.data[:half] if self.step == 0 else self.data[half:])
        self.step += 1
        return None, self.step >= 2


def _drive(pages=None, **kw):
    conn = GoogleDriveConnector(_cfg("google_drive", {"type": "service_account"}, **{k: v for k, v in kw.items() if k.endswith("_paths")}))
    conn._service = FakeDrive(pages or [{"files": []}], **{k: v for k, v in kw.items() if not k.endswith("_paths")})
    return conn


DRIVE_FILES = [
    {"files": [{"id": "f1", "name": "Plan", "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-10-05T00:00:00Z", "createdTime": "2026-01-01T00:00:00Z", "parents": ["p1"]}],
     "nextPageToken": "1"},
    {"files": [{"id": "f2", "name": "spec.pdf", "mimeType": "application/pdf", "size": "2048", "parents": ["p1"]},
               {"id": "f3", "name": "tmp.txt", "mimeType": "text/plain", "parents": ["p1"]}]},
]
PARENTS = {"p1": {"id": "p1", "name": "Team", "parents": ["root"]}, "root": {"id": "root", "name": "", "parents": []}}


def test_drive_lists_with_paths_pagination_query_and_filters():
    conn = _drive(DRIVE_FILES, parents=PARENTS, exclude_paths=["*/tmp.txt"])
    docs = run(_collect(conn.list_documents(since=datetime(2026, 10, 1, 12, 0))))
    assert [(d.source_id, d.path, d.size_bytes) for d in docs] == [("f1", "Team/Plan", None), ("f2", "Team/spec.pdf", 2048)]
    assert docs[0].modified_at == datetime(2026, 10, 5, tzinfo=UTC)
    calls = conn._service.list_calls
    assert [c["pageToken"] for c in calls] == [None, "1"]
    q = calls[0]["q"]
    assert "trashed=false" in q and "mimeType='application/pdf'" in q
    # naive since is treated as UTC and sent as RFC 3339 with an explicit offset
    assert "modifiedTime > '2026-10-01T12:00:00+00:00'" in q


def test_drive_build_path_stops_on_parent_lookup_errors_and_cycles():
    conn = _drive(parents={"p1": {"id": "p1", "name": "A", "parents": ["p1"]}})
    assert run(conn._build_path(conn._service, {"id": "f", "name": "doc", "parents": ["p1"]})) == "A/doc"
    assert run(conn._build_path(conn._service, {"id": "f", "name": "doc", "parents": ["missing"]})) == "doc"


def test_drive_download_exports_workspace_files_and_streams_binaries():
    conn = _drive()
    fake_http = types.ModuleType("googleapiclient.http")
    fake_http.MediaIoBaseDownload = FakeDownloader
    with patch.dict(sys.modules, {"googleapiclient.http": fake_http}):
        gdoc = NS(source_id="f1", name="Plan", mime_type="application/vnd.google-apps.document")
        assert run(conn.download_document(gdoc)) == b"export:f1"
        assert run(conn.download_document(NS(source_id="f2", name="x.pdf", mime_type="application/pdf"))) == b"media:f2"
        with pytest.raises(RuntimeError, match="Cannot export"):
            run(conn.download_document(NS(source_id="f9", name="form", mime_type="application/vnd.google-apps.form")))
    assert conn._service.export_calls[0][1].endswith("wordprocessingml.document")


def test_drive_credentials_validation_and_test_connection():
    bad = GoogleDriveConnector(_cfg("google_drive", {"something": "else"}))
    with pytest.raises(ValueError, match="Invalid Google Drive credentials"):
        bad._get_service()
    ok, err = run(bad.test_connection())
    assert not ok and "Invalid Google Drive credentials" in err
    assert run(_drive().test_connection()) == (True, None)


def test_drive_oauth_credentials_build_service(monkeypatch):
    built = {}
    import googleapiclient.discovery as discovery

    monkeypatch.setattr(discovery, "build", lambda *a, **kw: built.setdefault("svc", (a, kw)))
    conn = GoogleDriveConnector(_cfg("google_drive", {"refresh_token": "r", "client_id": "id", "client_secret": "s"}))
    svc = conn._get_service()
    assert svc[0] == ("drive", "v3") and svc[1]["credentials"].refresh_token == "r"
    assert conn._get_service() is svc  # cached


def test_drive_listing_failure_fails_the_sync():
    result = run(_drive(fail_list=True).sync(None, FakeDocService()))
    assert result.status == "error" and "quota exceeded" in (result.error_message or "")


def test_drive_sync_downloads_and_creates(monkeypatch):
    conn = _drive([DRIVE_FILES[1]], parents=PARENTS)
    fake_http = types.ModuleType("googleapiclient.http")
    fake_http.MediaIoBaseDownload = FakeDownloader
    svc = FakeDocService(existing={"f3": b"media:f3"})
    with patch.dict(sys.modules, {"googleapiclient.http": fake_http}):
        result = run(conn.sync(None, svc))
    assert result.status == "success" and svc.created == ["f2"] and svc.updated == []


# ================================= S3 =======================================

class FakeS3:
    def __init__(self, pages, fail=False, bodies=None):
        self.pages, self.fail, self.bodies, self.calls = pages, fail, bodies or {}, []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        outer = self

        class P:
            def paginate(self, **kw):
                outer.calls.append(kw)
                if outer.fail:
                    raise RuntimeError("AccessDenied")
                yield from outer.pages

        return P()

    def get_object(self, Bucket, Key):
        if Key not in self.bodies:
            raise KeyError(Key)
        return {"Body": NS(read=lambda: self.bodies[Key])}

    def head_bucket(self, Bucket):
        self.calls.append(("head", Bucket))

    def list_buckets(self):
        self.calls.append(("list_buckets",))


S3_PAGES = [
    {"Contents": [{"Key": "docs/", "Size": 0},
                  {"Key": "docs/a.pdf", "Size": 10, "ETag": '"etag-a"', "LastModified": datetime(2026, 10, 5, tzinfo=UTC)},
                  {"Key": "docs/b.exe", "Size": 1, "LastModified": datetime(2026, 10, 5, tzinfo=UTC)},
                  {"Key": "README", "Size": 1}]},
    {"Contents": [{"Key": "docs/old.md", "Size": 3, "LastModified": datetime(2026, 1, 1, tzinfo=UTC)},
                  {"Key": "private/c.txt", "Size": 3, "LastModified": datetime(2026, 10, 6, tzinfo=UTC)}]},
    {},
]


def _s3(pages=S3_PAGES, creds=None, **kw):
    conn = S3Connector(_cfg("s3", creds if creds is not None else {"bucket": "b", "prefix": "docs/"}, exclude_paths=["private/*"]))
    conn._client = FakeS3(pages, **kw)
    return conn


def test_s3_lists_supported_objects_with_since_and_filters():
    conn = _s3()
    docs = run(_collect(conn.list_documents(since=datetime(2026, 10, 1))))  # naive since == UTC
    assert [(d.source_id, d.name, d.content_hash, d.mime_type) for d in docs] == [
        ("s3://b/docs/a.pdf", "a.pdf", "etag-a", "application/pdf"),
    ]
    assert conn._client.calls[0] == {"Bucket": "b", "Prefix": "docs/"}


def test_s3_requires_bucket_and_boto3():
    with pytest.raises(ValueError, match="bucket not configured"):
        run(_collect(_s3(creds={"prefix": "x"}).list_documents()))
    with patch.dict(sys.modules, {"boto3": None}), pytest.raises(RuntimeError, match="boto3 not installed"):
        S3Connector(_cfg("s3", {"bucket": "b"}))._get_client()


def test_s3_client_session_kwargs(monkeypatch):
    seen = {}

    class Session:
        def __init__(self, **kw):
            seen.update(kw)

        def client(self, name):
            return f"client:{name}"

    with patch.dict(sys.modules, {"boto3": types.SimpleNamespace(Session=Session)}):
        conn = S3Connector(_cfg("s3", {"bucket": "b", "access_key_id": "AK", "secret_access_key": "SK", "region": "eu-west-1"}))
        assert conn._get_client() == "client:s3"
    assert seen == {"aws_access_key_id": "AK", "aws_secret_access_key": "SK", "region_name": "eu-west-1"}


def test_s3_test_connection_and_download():
    conn = _s3(bodies={"docs/a.pdf": b"%PDF"})
    assert run(conn.test_connection()) == (True, None) and conn._client.calls[-1] == ("head", "b")
    no_bucket = _s3(creds={})
    assert run(no_bucket.test_connection()) == (True, None) and no_bucket._client.calls[-1] == ("list_buckets",)
    remote = NS(metadata={"bucket": "b", "key": "docs/a.pdf"})
    assert run(conn.download_document(remote)) == b"%PDF"
    with pytest.raises(RuntimeError, match="Failed to download s3://b/docs/missing"):
        run(conn.download_document(NS(metadata={"bucket": "b", "key": "docs/missing"})))


def test_s3_listing_failure_fails_the_sync():
    result = run(_s3(fail=True).sync(None, FakeDocService()))
    assert result.status == "error" and "AccessDenied" in (result.error_message or "")


def test_s3_sync_counts():
    conn = _s3(bodies={"docs/a.pdf": b"new", "docs/old.md": b"same", "private/c.txt": b"x"})
    svc = FakeDocService(existing={"s3://b/docs/old.md": b"same"})
    result = run(conn.sync(None, svc))
    assert result.status == "success" and svc.created == ["s3://b/docs/a.pdf"] and svc.updated == []


# ============================ shared helpers ================================

def test_store_timestamps_are_aware_utc():
    from backend.connectors.base import as_utc
    from backend.connectors.store import _timestamp

    assert _timestamp("2026-10-01 12:00:00") == datetime(2026, 10, 1, 12, tzinfo=UTC)  # SQLite CURRENT_TIMESTAMP
    assert _timestamp("2026-10-01T12:00:00Z").tzinfo is not None
    assert _timestamp(datetime(2026, 10, 1)) == datetime(2026, 10, 1, tzinfo=UTC)
    assert _timestamp("garbage") is None and _timestamp(None) is None
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    assert as_utc(datetime(2026, 10, 1, 17, 30, tzinfo=ist)) == datetime(2026, 10, 1, 12, tzinfo=UTC)
