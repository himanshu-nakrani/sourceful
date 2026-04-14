"""Model listing endpoints for providers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.routers.deps import RequestContext, get_request_context
from backend.services.provider_auth import normalize_provider_api_key

logger = logging.getLogger("ragapp.models")
router = APIRouter()

# Default model lists as fallback
DEFAULT_CHAT_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "gemini": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
}

DEFAULT_EMBEDDING_MODELS: dict[str, list[str]] = {
    "openai": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
    "gemini": ["models/gemini-embedding-001"],
}


def _require_provider_api_key(x_provider_api_key: str | None = Header(default=None)) -> str:
    """
    Validate and return a normalized provider API key from the X-Provider-Api-Key header.
    
    Parameters:
        x_provider_api_key (str | None): Value of the `X-Provider-Api-Key` header (may be None).
    
    Returns:
        str: The normalized provider API key.
    
    Raises:
        fastapi.HTTPException: With status code 401 and code `MISSING_PROVIDER_API_KEY` when the header is missing or the normalized value is empty.
    """
    provider_api_key = normalize_provider_api_key(x_provider_api_key)
    if not provider_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Missing X-Provider-Api-Key header.",
                "code": "MISSING_PROVIDER_API_KEY",
            },
        )
    return provider_api_key


async def _fetch_openai_models(api_key: str) -> list[str]:
    """
    Fetch available chat and embedding model IDs from the OpenAI service, falling back to configured defaults on failure or when no matching models are found.
    
    Returns:
        tuple[list[str], list[str]]: A pair where the first element is the list of chat model IDs (filtered by presence of "gpt") and the second element is the list of embedding model IDs (filtered by presence of "embedding"). If the remote fetch fails, returns non-200 status, raises an exception, or yields no matches, returns the module's default chat and embedding model lists for OpenAI.
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.warning("openai_models_fetch_failed", status_code=response.status_code)
                return DEFAULT_CHAT_MODELS["openai"]

            data = response.json()
            models = [m["id"] for m in data.get("data", [])]

            # Filter for chat models (gpt models)
            chat_models = [m for m in models if "gpt" in m.lower()]
            embedding_models = [m for m in models if "embedding" in m.lower()]

            return chat_models if chat_models else DEFAULT_CHAT_MODELS["openai"], \
                   embedding_models if embedding_models else DEFAULT_EMBEDDING_MODELS["openai"]
    except Exception as exc:
        logger.warning("openai_models_fetch_error", error=str(exc))
        return DEFAULT_CHAT_MODELS["openai"], DEFAULT_EMBEDDING_MODELS["openai"]


async def _fetch_gemini_models(api_key: str) -> tuple[list[str], list[str]]:
    """
    Retrieve available Gemini models and separate them into chat (generative) and embedding model lists.
    
    Parameters:
        api_key (str): API key for Google Gemini (Generative Language API).
    
    Returns:
        tuple[list[str], list[str]]: A pair where the first element is the list of chat/generative model IDs and the second is the list of embedding model IDs. If fetching fails or no matching models are found, returns the module's default model lists for Gemini.
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.warning("gemini_models_fetch_failed", status_code=response.status_code)
                return DEFAULT_CHAT_MODELS["gemini"], DEFAULT_EMBEDDING_MODELS["gemini"]

            data = response.json()
            models = data.get("models", [])

            # Filter for generative models (chat) and embedding models
            chat_models = []
            embedding_models = []

            for model in models:
                name = model.get("name", "")
                supported_actions = model.get("supportedGenerationMethods", [])

                # Check if it's a generative model
                if "generateContent" in supported_actions:
                    # Extract just the model name from "models/model-name"
                    model_name = name.replace("models/", "")
                    chat_models.append(model_name)

                # Check if it's an embedding model
                if "embedContent" in supported_actions and "embedding" in name.lower():
                    model_name = name.replace("models/", "")
                    embedding_models.append(model_name)

            return (
                chat_models if chat_models else DEFAULT_CHAT_MODELS["gemini"],
                embedding_models if embedding_models else DEFAULT_EMBEDDING_MODELS["gemini"]
            )
    except Exception as exc:
        logger.warning("gemini_models_fetch_error", error=str(exc))
        return DEFAULT_CHAT_MODELS["gemini"], DEFAULT_EMBEDDING_MODELS["gemini"]


@router.get("/models")
async def list_models(
    request: Request,
    provider: str,
    context: RequestContext = Depends(get_request_context),
    provider_api_key: str = Depends(_require_provider_api_key),
) -> dict[str, Any]:
    """
    Get available chat and embedding model IDs for the specified provider.
    
    Parameters:
        provider (str): Provider name, must be "openai" or "gemini".
        provider_api_key (str): Normalized provider API key extracted from the `X-Provider-Api-Key` header.
    
    Returns:
        dict: {
            "provider": str,
            "chat_models": list[str],
            "embedding_models": list[str]
        }
    
    Raises:
        HTTPException: If `provider` is not "openai" or "gemini" (status 400, code "INVALID_PROVIDER").
    """
    if provider not in ("openai", "gemini"):
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid provider. Must be 'openai' or 'gemini'.", "code": "INVALID_PROVIDER"},
        )

    if provider == "openai":
        chat_models, embedding_models = await _fetch_openai_models(provider_api_key)
    else:
        chat_models, embedding_models = await _fetch_gemini_models(provider_api_key)

    return {
        "provider": provider,
        "chat_models": chat_models,
        "embedding_models": embedding_models,
    }
