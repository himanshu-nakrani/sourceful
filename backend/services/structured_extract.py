"""Phase 2.6: Structured field extraction via LLM.

Given a document and a user-defined JSON schema, uses an LLM to extract
structured fields from the document text and persists the result alongside
the document for downstream filtering and boosting.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger("ragapp.structured_extract")


@dataclass(slots=True)
class ExtractionResult:
    """Result of a structured extraction run."""
    fields: dict
    model: str
    token_usage: dict | None = None


_SYSTEM_PROMPT = """\
You are a precise document analysis assistant. The user will provide document
text and a JSON schema describing the fields to extract.

Your task:
1. Read the document text carefully.
2. For each field in the schema, extract the value from the document.
3. If a field cannot be found, use null.
4. Return ONLY a valid JSON object matching the schema. No extra commentary.
"""


async def extract_fields(
    *,
    document_text: str,
    schema: dict,
    provider: str,
    api_key: str,
    model: str,
    max_doc_chars: int = 30_000,
) -> ExtractionResult:
    """Extract structured fields from a document using an LLM.

    Parameters
    ----------
    document_text:
        The full text of the document (truncated to *max_doc_chars*).
    schema:
        A JSON-schema-like dict describing the fields to extract.
        Example: ``{"title": "string", "author": "string", "date": "string",
                   "summary": "string (max 200 chars)"}``
    provider:
        ``"openai"`` or ``"gemini"``.
    api_key:
        The provider API key.
    model:
        The chat model to use for extraction.
    max_doc_chars:
        Maximum document text length sent to the model.
    """
    truncated = document_text[:max_doc_chars]

    user_prompt = (
        f"## Document text\n\n{truncated}\n\n"
        f"## Schema to fill\n\n```json\n{json.dumps(schema, indent=2)}\n```\n\n"
        "Extract the fields and return ONLY the JSON object."
    )

    if provider == "openai":
        return await _extract_openai(user_prompt, model, api_key)
    elif provider == "gemini":
        return await _extract_gemini(user_prompt, model, api_key)
    else:
        raise ValueError(f"Unsupported provider for extraction: {provider}")


async def _extract_openai(user_prompt: str, model: str, api_key: str) -> ExtractionResult:
    import asyncio
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("openai package is required for OpenAI extraction.") from exc

    client = OpenAI(api_key=api_key)
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or "{}"
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    try:
        fields = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("extraction_json_parse_failed content=%s", content[:200])
        fields = {"_raw": content}

    return ExtractionResult(fields=fields, model=model, token_usage=usage)


async def _extract_gemini(user_prompt: str, model: str, api_key: str) -> ExtractionResult:
    import asyncio
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise ValueError("google-generativeai package is required for Gemini extraction.") from exc

    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(model)

    response = await asyncio.to_thread(
        gen_model.generate_content,
        [_SYSTEM_PROMPT + "\n\n" + user_prompt],
        generation_config=genai.GenerationConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    content = response.text or "{}"
    usage = None
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = {
            "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
            "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
        }

    try:
        fields = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("extraction_json_parse_failed content=%s", content[:200])
        fields = {"_raw": content}

    return ExtractionResult(fields=fields, model=model, token_usage=usage)
