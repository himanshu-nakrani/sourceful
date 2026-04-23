"""Chunk extracted sections while keeping chunk/page metadata.

Supports three strategies:
  - ``fixed`` (default): Token-window chunking with sentence-aware breaks.
  - ``semantic``: Sentence-embedding breakpoint detection that merges
    consecutive sentences while their cosine similarity exceeds a threshold.
  - ``table``: Keeps pre-detected tables as single chunks with type ``table``.

The strategy is selected via the ``CHUNK_STRATEGY`` setting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from backend.services.extract import ExtractedSection


@dataclass(slots=True)
class ChunkPayload:
    chunk_index: int
    content: str
    page_number: int | None = None
    # When parent-document retrieval is used, `content` is the small child
    # window we embed and `parent_content` is the larger surrounding window
    # we hand to the LLM at retrieval time. Leave `None` for flat chunking.
    parent_content: str | None = None
    # Contextual retrieval: if set, this (richer) text is what we embed,
    # while `content` remains the raw chunk we display in citations.
    # When `None`, we embed `content` directly.
    embedding_content: str | None = None
    # Phase 2: chunk type — 'text' (default) | 'table' | 'image'
    chunk_type: str = "text"
    # Phase 2: arbitrary per-chunk metadata (table headers, slide index, etc.)
    metadata: dict | None = None

    @property
    def metadata_json(self) -> str | None:
        """Serialize metadata dict to JSON for persistence."""
        if self.metadata is None:
            return None
        return json.dumps(self.metadata, separators=(",", ":"))


SENTENCE_ENDINGS = {".", "!", "?", "\n"}


def _chunk_one(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 5)

    chunks: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        end = min(index + chunk_size, length)
        if end < length:
            search_start = max(index + int(chunk_size * 0.8), index)
            best_break = end
            for cursor in range(end - 1, search_start - 1, -1):
                if text[cursor] in SENTENCE_ENDINGS:
                    best_break = cursor + 1
                    break
            end = best_break

        piece = text[index:end].strip()
        if piece:
            chunks.append(piece)

        if end >= length:
            break

        index += max(1, (end - index) - chunk_overlap)

    return chunks


def chunk_sections(sections: list[ExtractedSection], chunk_size: int, chunk_overlap: int) -> list[ChunkPayload]:
    payloads: list[ChunkPayload] = []
    chunk_index = 0
    for section in sections:
        chunk_type = getattr(section, "chunk_type", "text") or "text"
        metadata = getattr(section, "metadata", None)
        for piece in _chunk_one(section.text, chunk_size, chunk_overlap):
            payloads.append(
                ChunkPayload(
                    chunk_index=chunk_index,
                    content=piece,
                    page_number=section.page_number,
                    chunk_type=chunk_type,
                    metadata=metadata,
                )
            )
            chunk_index += 1
    return payloads


def chunk_sections_parent_child(
    sections: list[ExtractedSection],
    *,
    parent_size: int,
    child_size: int,
    child_overlap: int,
) -> list[ChunkPayload]:
    """Parent-document chunking: child windows for embedding, parent text for the LLM.

    Each section is first split into parent windows sized `parent_size`
    (using the existing sentence-aware splitter with no overlap — parents
    don't overlap so we don't leak duplicate context to the LLM), then
    each parent is further subdivided into child windows of `child_size`
    with `child_overlap`. Every child carries a reference to its parent
    text so retrieval can substitute it at read time.
    """
    if parent_size <= child_size:
        # Degenerate config — fall back to flat chunking.
        return chunk_sections(sections, child_size, child_overlap)

    payloads: list[ChunkPayload] = []
    chunk_index = 0
    for section in sections:
        parents = _chunk_one(section.text, parent_size, 0)
        for parent in parents:
            children = _chunk_one(parent, child_size, child_overlap)
            if not children:
                continue
            for child in children:
                payloads.append(
                    ChunkPayload(
                        chunk_index=chunk_index,
                        content=child,
                        page_number=section.page_number,
                        parent_content=parent,
                    )
                )
                chunk_index += 1
    return payloads


# ---- Semantic chunking ------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter for semantic chunking.

    Splits on `. `, `! `, `? `, and newlines. Preserves the delimiter
    at the end of each sentence for readability.
    """
    sentences: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        current.append(char)
        if char in {".", "!", "?"} and i + 1 < len(text) and text[i + 1] in {" ", "\n"}:
            sentences.append("".join(current).strip())
            current = []
        elif char == "\n":
            piece = "".join(current).strip()
            if piece:
                sentences.append(piece)
            current = []
        i += 1
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return [s for s in sentences if s]


def chunk_sections_semantic(
    sections: list[ExtractedSection],
    *,
    max_chunk_chars: int = 1200,
    sim_threshold: float = 0.5,
) -> list[ChunkPayload]:
    """Semantic chunking: merge consecutive sentences while they're similar.

    Uses a simple TF-IDF-like bag-of-words cosine similarity to detect
    breakpoints between sentences. When two consecutive sentences are
    below `sim_threshold`, a chunk boundary is inserted.

    Falls back gracefully to fixed-window chunking when chunks exceed
    `max_chunk_chars`.
    """
    import hashlib
    import math

    DIM = 64

    def _bow_vector(text: str) -> list[float]:
        vec = [0.0] * DIM
        for token in text.lower().split():
            bucket = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % DIM
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (norm_a * norm_b)

    payloads: list[ChunkPayload] = []
    chunk_index = 0

    for section in sections:
        sentences = _split_sentences(section.text)
        if not sentences:
            continue

        chunk_type = getattr(section, "chunk_type", "text") or "text"
        metadata = getattr(section, "metadata", None)

        # Compute vectors for all sentences
        vectors = [_bow_vector(s) for s in sentences]

        # Merge consecutive sentences while similar and under size limit
        groups: list[list[str]] = [[sentences[0]]]
        for i in range(1, len(sentences)):
            sim = _cosine(vectors[i - 1], vectors[i])
            current_len = sum(len(s) for s in groups[-1]) + len(sentences[i])
            if sim >= sim_threshold and current_len <= max_chunk_chars:
                groups[-1].append(sentences[i])
            else:
                groups.append([sentences[i]])

        for group in groups:
            text = " ".join(group).strip()
            if not text:
                continue
            # If still too long, fall back to fixed-window splitting
            if len(text) > max_chunk_chars:
                for piece in _chunk_one(text, max_chunk_chars, max_chunk_chars // 5):
                    payloads.append(
                        ChunkPayload(
                            chunk_index=chunk_index,
                            content=piece,
                            page_number=section.page_number,
                            chunk_type=chunk_type,
                            metadata=metadata,
                        )
                    )
                    chunk_index += 1
            else:
                payloads.append(
                    ChunkPayload(
                        chunk_index=chunk_index,
                        content=text,
                        page_number=section.page_number,
                        chunk_type=chunk_type,
                        metadata=metadata,
                    )
                )
                chunk_index += 1

    return payloads
