"""Embedding helpers for OpenAI and Gemini."""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from backend.settings import settings


async def embed_texts_openai(api_key: str, model: str, texts: list[str]) -> list[list[float]]:
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
    client = AsyncOpenAI(api_key=api_key, timeout=settings.request_timeout_seconds)
    response = await client.embeddings.create(model=model, input=text)
    return list(response.data[0].embedding)



def embed_texts_gemini_sync(api_key: str, model: str, texts: list[str]) -> list[list[float]]:
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
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    result = genai.embed_content(model=model, content=text, task_type="retrieval_query")
    embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
    if embedding is None:
        raise ValueError("Gemini returned no embedding for the question.")
    return list(embedding)


async def embed_texts(provider: str, api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    if provider == "vertex_search":
        return [[0.0] * 768 for _ in texts]
    if provider == "openai":
        return await embed_texts_openai(api_key, model, texts)
    return await asyncio.to_thread(embed_texts_gemini_sync, api_key, model, texts)


async def embed_query(provider: str, api_key: str, model: str, text: str) -> list[float]:
    if provider == "vertex_search":
        return [0.0] * 768
    if provider == "openai":
        return await embed_query_openai(api_key, model, text)
    return await asyncio.to_thread(embed_query_gemini_sync, api_key, model, text)
