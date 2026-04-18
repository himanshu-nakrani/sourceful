"""Prompt building and streaming helpers for OpenAI and Gemini."""

from __future__ import annotations


from openai import AsyncOpenAI

from backend.services.vectorstore import RetrievedChunk
from backend.settings import settings


SYSTEM_PROMPT = (
    "You are a careful document assistant. Answer only from the provided document excerpts. "
    "When you use an excerpt, cite it with [1], [2], and so on. If the answer is not in the "
    "retrieved excerpts, clearly say you cannot find it in the document. Use concise markdown."
)



def build_rag_prompt(
    retrieved_chunks: list[RetrievedChunk],
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    numbered_context = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        page = f" (page {chunk.page_number})" if chunk.page_number else ""
        numbered_context.append(f"[{index}]{page}\n{chunk.excerpt}")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Document excerpts:\n\n" + "\n\n---\n\n".join(numbered_context)},
    ]
    for item in history or []:
        if item["role"] in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": question})
    return messages


async def create_openai_text(api_key: str, model: str, messages: list[dict[str, str]]) -> str:
    client = AsyncOpenAI(api_key=api_key, timeout=settings.request_timeout_seconds)
    response = await client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        stream=False,
    )
    if not response.choices:
        return ""
    return response.choices[0].message.content or ""


async def stream_openai_text(api_key: str, model: str, messages: list[dict[str, str]]):
    """Yield OpenAI chat completion tokens as they arrive."""
    client = AsyncOpenAI(api_key=api_key, timeout=settings.request_timeout_seconds)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta is None:
            continue
        piece = getattr(delta, "content", None)
        if piece:
            yield piece
            continue
        refusal = getattr(delta, "refusal", None)
        if refusal:
            yield refusal


def stream_gemini_text(api_key: str, model_name: str, messages: list[dict[str, str]]):
    """Synchronous generator yielding Gemini tokens; caller runs in a thread."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    system_instruction = None
    history: list[dict] = []

    for message in messages:
        if message["role"] == "system":
            system_instruction = message["content"]
        elif message["role"] == "assistant":
            history.append({"role": "model", "parts": [message["content"]]})
        elif message["role"] == "user":
            if history and history[-1]["role"] == "user":
                history[-1]["parts"][0] += "\n\n" + message["content"]
            else:
                history.append({"role": "user", "parts": [message["content"]]})

    prompt = ""
    if history and history[-1]["role"] == "user":
        prompt = history.pop()["parts"][0]

    model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
    if history:
        chat = model.start_chat(history=history)
        response_iter = chat.send_message(prompt, stream=True)
    else:
        response_iter = model.generate_content(prompt, stream=True)

    for chunk in response_iter:
        text = _extract_gemini_stream_text(chunk)
        if text:
            yield text


def _extract_gemini_stream_text(chunk) -> str:
    """Incremental stream chunks often lack `.text` (it raises until the stream completes).

    Prefer structured candidates/parts, then fall back to `.text` when available.
    """
    parts_out: list[str] = []
    candidates = getattr(chunk, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", None) or []:
            t = getattr(part, "text", None)
            if t:
                parts_out.append(t)
    if parts_out:
        return "".join(parts_out)
    try:
        t2 = chunk.text
    except (ValueError, AttributeError):
        return ""
    return t2 or ""



def gemini_text(api_key: str, model_name: str, messages: list[dict[str, str]]) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    system_instruction = None
    history: list[dict] = []

    for message in messages:
        if message["role"] == "system":
            system_instruction = message["content"]
        elif message["role"] == "assistant":
            history.append({"role": "model", "parts": [message["content"]]})
        elif message["role"] == "user":
            if history and history[-1]["role"] == "user":
                history[-1]["parts"][0] += "\n\n" + message["content"]
            else:
                history.append({"role": "user", "parts": [message["content"]]})

    prompt = ""
    if history and history[-1]["role"] == "user":
        prompt = history.pop()["parts"][0]

    model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
    if history:
        chat = model.start_chat(history=history)
        response = chat.send_message(prompt, stream=False)
    else:
        response = model.generate_content(prompt, stream=False)

    try:
        text = response.text
    except ValueError as e:
        raise ValueError(f"Response yielded a blocked or empty payload due to safety filters or API limits. {e}")
    except AttributeError:
        return ""
    
    return text or ""
