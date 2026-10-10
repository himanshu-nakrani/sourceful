"""Unit tests for the legacy JSON document registry (backend.services.registry)."""

from __future__ import annotations

import json

from backend.services import registry


def test_missing_file_loads_empty(tmp_path):
    assert registry.load_registry(str(tmp_path / "nope.json")) == {}


def test_non_dict_json_loads_empty(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps([1, 2, 3]))
    assert registry.load_registry(str(path)) == {}


def test_register_get_unregister_roundtrip_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "documents.json"
    registry.register_document(str(path), "doc-1", provider="openai", embedding_model="m", chunk_count=3)
    registry.register_document(str(path), "doc-2", provider="gemini", embedding_model="g", chunk_count=1)
    assert registry.get_document(str(path), "doc-1") == {
        "provider": "openai",
        "embedding_model": "m",
        "chunk_count": 3,
    }
    registry.unregister_document(str(path), "doc-1")
    assert registry.get_document(str(path), "doc-1") is None
    assert set(registry.load_registry(str(path))) == {"doc-2"}


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "documents.json"
    registry.save_registry(str(path), {"a": {"x": 1}})
    assert json.loads(path.read_text()) == {"a": {"x": 1}}
    assert [p.name for p in tmp_path.iterdir()] == ["documents.json"]


def test_unregister_missing_is_noop_and_does_not_create_file(tmp_path):
    path = tmp_path / "documents.json"
    registry.unregister_document(str(path), "ghost")
    assert not path.exists()


def test_get_document_ignores_non_dict_entries(tmp_path):
    path = tmp_path / "documents.json"
    path.write_text(json.dumps({"weird": "not-a-dict"}))
    assert registry.get_document(str(path), "weird") is None
