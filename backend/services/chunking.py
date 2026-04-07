"""Chunk extracted sections while keeping chunk/page metadata."""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.extract import ExtractedSection


@dataclass(slots=True)
class ChunkPayload:
    chunk_index: int
    content: str
    page_number: int | None = None


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
        for piece in _chunk_one(section.text, chunk_size, chunk_overlap):
            payloads.append(
                ChunkPayload(
                    chunk_index=chunk_index,
                    content=piece,
                    page_number=section.page_number,
                )
            )
            chunk_index += 1
    return payloads
