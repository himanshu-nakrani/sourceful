"""Embedding helpers for OpenAI and Gemini."""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from backend.settings import settings


async def embed_texts_openai(api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI's API.

    Processes texts in batches of 64 to respect API limits.

    Args:
        api_key: OpenAI API key.
        model: The embedding model to use (e.g., 'text-embedding-3-small').
        texts: List of text strings to embed.

    Returns:
        A list of embedding vectors, one per input text.
    """
    client = AsyncOpenAI(api_key=api_key, timeout=settings.request_timeout_seconds)
    result: list[list[float]] = []
    batch_size = 64
    for index in range(0, len(texts), batch_size):
        batch = texts[index:index + batch_size]
        response = await client.embeddings.create(model=model, input=batch)
        for item in response.data:
            result.append(list(item.embedding))
    return result


async def embed_query_openai(api_key: str, model: str, text: str) -> list[float]:
    """Generate an embedding for a single query text using OpenAI's API.

    Args:
        api_key: OpenAI API key.
        model: The embedding model to use.
        text: The query text to embed.

    Returns:
        A single embedding vector.
    """
    client = AsyncOpenAI(api_key=api_key, timeout=settings.request_timeout_seconds)
    response = await client.embeddings.create(model=model, input=text)
    return list(response.data[0].embedding)



def embed_texts_gemini_sync(api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using Google Gemini's API.

    Note: This is a synchronous function wrapped for compatibility.

    Args:
        api_key: Google API key.
        model: The embedding model to use.
        texts: List of text strings to embed.

    Returns:
        A list of embedding vectors, one per input text.

    Raises:
        ValueError: If Gemini returns no embedding for a chunk.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    embeddings: list[list[float]] = []
    for text in texts:
        result = genai.embed_content(model=model, content=text, task_type="retrieval_document")
        embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
        if embedding is None:
            raise ValueError("Gemini returned no embedding for a chunk.")
        embeddings.append(list(embedding))
    return embeddings



def embed_query_gemini_sync(api_key: str, model: str, text: str) -> list[float]:
    """Generate an embedding for a single query text using Google Gemini's API.

    Note: This is a synchronous function wrapped for compatibility.

    Args:
        api_key: Google API key.
        model: The embedding model to use.
        text: The query text to embed.

    Returns:
        A single embedding vector.

    Raises:
        ValueError: If Gemini returns no embedding for the question.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    result = genai.embed_content(model=model, content=text, task_type="retrieval_query")
    embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
    if embedding is None:
        raise ValueError("Gemini returned no embedding for the question.")
    return list(embedding)


async def embed_texts(provider: str, api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using the specified provider.

    Dispatches to the appropriate provider-specific implementation.

    Args:
        provider: The embedding provider ('openai' or 'gemini').
        api_key: API key for the provider.
        model: The embedding model to use.
        texts: List of text strings to embed.

    Returns:
        A list of embedding vectors, one per input text.
    """
    # if provider == "vertex_search":
    #     return [[0.0] * 768 for _ in texts]
    if provider == "openai":
        return await embed_texts_openai(api_key, model, texts)
    return await asyncio.to_thread(embed_texts_gemini_sync, api_key, model, texts)


async def embed_query(provider: str, api_key: str, model: str, text: str) -> list[float]:
    """Generate an embedding for a single query text using the specified provider.

    Dispatches to the appropriate provider-specific implementation.

    Args:
        provider: The embedding provider ('openai' or 'gemini').
        api_key: API key for the provider.
        model: The embedding model to use.
        text: The query text to embed.

    Returns:
        A single embedding vector.
    """
    # if provider == "vertex_search":
    #     return [0.0] * 768
    if provider == "openai":
        return await embed_query_openai(api_key, model, text)
    return await asyncio.to_thread(embed_query_gemini_sync, api_key, model, text)
