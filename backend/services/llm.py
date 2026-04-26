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

# Phase 2 — analysis modes. Each mode appends a structured-output instruction
# to the base SYSTEM_PROMPT. Citations and grounding rules from the base
# prompt always apply.
MODE_INSTRUCTIONS: dict[str, str] = {
    "ask": "",
    "compare": (
        "\n\nMode: COMPARE. The user wants similarities and differences across the "
        "provided sources. Structure your answer as: a 1-2 sentence framing, then a "
        "section titled 'Similarities' with bullet points (each citing its source), "
        "then a section titled 'Differences' as a markdown table with columns "
        "'Aspect' and one column per cited source. Each bullet/cell must include a "
        "citation marker like [1]."
    ),
    "extract": (
        "\n\nMode: EXTRACT. The user wants normalized field extraction. Identify the "
        "fields the user is asking about, return a markdown table with columns "
        "'Field', 'Value', and 'Source'. Every row must include a citation marker. "
        "If a field cannot be located in the excerpts, write 'not found' in the "
        "Value column."
    ),
    "brief": (
        "\n\nMode: BRIEF. Produce an executive summary with these sections in this "
        "order: 'TL;DR' (1-2 sentences), 'Key points' (3-6 bullets, each cited), "
        "'Risks / open questions' (1-3 bullets if applicable). Keep total length "
        "under 250 words. Every claim must include a citation marker."
    ),
}


def system_prompt_for_mode(mode: str | None) -> str:
    """Return the SYSTEM_PROMPT augmented for ``mode`` (defaults to 'ask')."""
    suffix = MODE_INSTRUCTIONS.get((mode or "ask").lower(), "")
    return SYSTEM_PROMPT + suffix


def build_rag_prompt(
    retrieved_chunks: list[RetrievedChunk],
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    mode: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the chat prompt from retrieved chunks.

    Phase 2 introduces a precedence rule: source-document chunks (``chunk_type
    in {"text", "table", "image"}`` etc.) form the primary evidence set, and
    workspace artifacts (``chunk_type == "artifact"``) are appended under a
    separate "Saved knowledge" heading. Both groups share a single ``[N]``
    citation numbering so the LLM can reference any of them, but the system
    prompt suffix tells the model that artifact entries are *augmenting*
    context — never to be presented as primary source documents.
    """
    primary_lines: list[str] = []
    artifact_lines: list[str] = []
    has_artifacts = False
    for index, chunk in enumerate(retrieved_chunks, start=1):
        page = f" (page {chunk.page_number})" if chunk.page_number else ""
        if getattr(chunk, "chunk_type", "text") == "artifact":
            has_artifacts = True
            title = ""
            try:
                if chunk.metadata_json:
                    import json as _json

                    meta = _json.loads(chunk.metadata_json)
                    if isinstance(meta, dict):
                        if meta.get("title"):
                            title = f" — {meta['title']}"
            except (TypeError, ValueError):
                title = ""
            artifact_lines.append(f"[{index}]{page} (saved {title.strip(' —') or 'note'})\n{chunk.excerpt}")
        else:
            primary_lines.append(f"[{index}]{page}\n{chunk.excerpt}")

    user_blocks: list[str] = []
    # Always emit the primary "Document excerpts:" header so single-document
    # callers see the same shape they did pre-Phase-2 even when there are no
    # primary chunks (rare but possible during empty-retrieval edge cases).
    user_blocks.append(
        "Document excerpts:\n\n" + "\n\n---\n\n".join(primary_lines)
    )
    if artifact_lines:
        user_blocks.append(
            "Saved knowledge (augmenting context, not primary sources):\n\n"
            + "\n\n---\n\n".join(artifact_lines)
        )

    system_prompt = system_prompt_for_mode(mode)
    if has_artifacts:
        system_prompt = (
            system_prompt
            + "\n\nSome numbered excerpts come from the workspace's saved "
            "knowledge (notes, saved answers, briefs). Treat them as "
            "augmenting context: never present them as if they were the "
            "primary source documents, and prefer the source excerpts when "
            "they conflict."
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n===\n\n".join(user_blocks)},
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
