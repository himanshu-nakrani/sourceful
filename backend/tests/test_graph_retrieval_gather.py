import pytest
from backend.services.graph_retrieval import _fetch_chunks_for_entities

@pytest.mark.asyncio
async def test_fetch_chunks_for_entities_mocked(monkeypatch):
    calls = []
    async def mock_fetch_all(sql, params):
        calls.append((sql, params))
        # Return mock results based on params
        doc_id = params[0]
        if doc_id == "doc1":
            return [{"id": "c1", "document_id": "doc1", "content": "apple pie", "page_number": 1, "parent_content": "apple pie recipe"}]
        elif doc_id == "doc2":
            return [{"id": "c2", "document_id": "doc2", "content": "banana split", "page_number": 1, "parent_content": "banana split recipe"}]
        return []

    monkeypatch.setattr("backend.services.graph_retrieval.fetch_all", mock_fetch_all)
    monkeypatch.setattr("backend.services.graph_retrieval.settings.retrieval_parent_doc_enabled", False)

    rows = [
        {"document_id": "doc1", "name": "apple"},
        {"document_id": "doc2", "name": "banana"}
    ]
    res = await _fetch_chunks_for_entities("test_owner", rows, 5)

    assert len(res) == 2
    assert len(calls) == 2
