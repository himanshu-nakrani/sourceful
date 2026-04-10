"""File validation, MIME sniffing, and text extraction with lightweight metadata."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(slots=True)
class ExtractedSection:
    text: str
    page_number: int | None = None


@dataclass(slots=True)
class ExtractedDocument:
    sections: list[ExtractedSection]
    page_count: int | None = None


CANONICAL_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
}


class FileValidationError(ValueError):
    pass


@dataclass(slots=True)
class ValidatedUpload:
    filename: str
    suffix: str
    mime_type: str
    checksum: str
    size: int



def validate_upload(filename: str, raw: bytes, declared_mime_type: str | None = None) -> ValidatedUpload:
    suffix = PurePath(filename.lower()).suffix
    if suffix not in CANONICAL_MIME_TYPES:
        raise FileValidationError(f"Unsupported file type: {suffix}")

    mime_type = sniff_mime_type(filename, raw, declared_mime_type)
    checksum = hashlib.sha256(raw).hexdigest()
    return ValidatedUpload(
        filename=filename,
        suffix=suffix,
        mime_type=mime_type,
        checksum=checksum,
        size=len(raw),
    )



def sniff_mime_type(filename: str, raw: bytes, declared_mime_type: str | None = None) -> str:
    suffix = PurePath(filename.lower()).suffix
    canonical = CANONICAL_MIME_TYPES.get(suffix)
    if canonical is None:
        raise FileValidationError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        if not raw.startswith(b"%PDF"):
            raise FileValidationError("File does not look like a valid PDF.")
        return canonical

    if suffix == ".docx":
        if raw[:2] != b"PK":
            raise FileValidationError("File does not look like a valid DOCX archive.")
        return canonical

    if suffix in {".txt", ".md", ".csv"}:
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileValidationError("Text-based files must be valid UTF-8.") from exc
        return canonical if declared_mime_type in (None, "", "application/octet-stream") else declared_mime_type

    return canonical



def extract_document(*, filename: str, raw: bytes) -> ExtractedDocument:
    suffix = PurePath(filename.lower()).suffix

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("pypdf is required to parse PDF files.") from exc

        reader = PdfReader(io.BytesIO(raw))
        sections: list[ExtractedSection] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append(ExtractedSection(text=text, page_number=index))
        if not sections:
            raise ValueError("Could not extract text from PDF (empty or scanned image-only).")
        return ExtractedDocument(sections=sections, page_count=len(reader.pages))

    if suffix in {".txt", ".md"}:
        text = raw.decode("utf-8").strip()
        if not text:
            raise ValueError("Document is empty.")
        return ExtractedDocument(sections=[ExtractedSection(text=text)])

    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("python-docx is required to parse DOCX files.") from exc

        doc = Document(io.BytesIO(raw))
        paragraphs = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
        if not paragraphs:
            raise ValueError("Could not extract text from DOCX (empty document).")
        return ExtractedDocument(sections=[ExtractedSection(text="\n\n".join(paragraphs))])

    if suffix == ".csv":
        decoded = raw.decode("utf-8")
        reader_csv = csv.reader(io.StringIO(decoded))
        rows = [" | ".join(cell.strip() for cell in row) for row in reader_csv]
        text = "\n".join(row for row in rows if row.strip()).strip()
        if not text:
            raise ValueError("CSV file appears to be empty.")
        return ExtractedDocument(sections=[ExtractedSection(text=text)])

    raise ValueError(f"Unsupported file type: {suffix}")
