"""Regression coverage for model-list fallbacks."""

from __future__ import annotations

from backend.routers.models import DEFAULT_CHAT_MODELS, DEFAULT_EMBEDDING_MODELS


class RaisingAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")


def test_models_endpoint_falls_back_when_provider_fetch_raises(client, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", RaisingAsyncClient)

    response = client.get(
        "/api/models?provider=openai",
        headers={"X-Client-Session": "models-fallback", "X-Provider-Api-Key": "test-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "chat_models": DEFAULT_CHAT_MODELS["openai"],
        "embedding_models": DEFAULT_EMBEDDING_MODELS["openai"],
    }
