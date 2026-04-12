"""Provider auth helpers shared between routers and services."""

from __future__ import annotations


class MissingProviderApiKeyError(ValueError):
    """Raised when a provider requires an API key but none was supplied."""

    def __init__(self, message: str = "Missing provider API key.") -> None:
        super().__init__(message)


def provider_requires_api_key(provider: str) -> bool:
    """Return True if the provider requires a caller-supplied API key.

    Vertex AI Search uses service-side credentials for ingest/reprocess/search,
    so it does not require `X-Provider-Api-Key` for those flows.
    """

    return provider != "vertex_search"


def normalize_provider_api_key(value: str | None) -> str:
    return (value or "").strip()


def require_provider_api_key(provider: str, value: str | None) -> str:
    key = normalize_provider_api_key(value)
    if provider_requires_api_key(provider) and not key:
        raise MissingProviderApiKeyError()
    return key

