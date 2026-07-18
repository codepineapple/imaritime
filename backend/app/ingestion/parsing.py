"""Turns an uploaded source document into plain text.

Produces the `report_text` string `app.extraction.signature
.ExtractMaritimeReport` expects ("including page numbers for
reference"). Docling is only invoked for rich formats (PDF, DOCX, ...)
where it adds real value via layout-aware, per-page parsing; plain
text/Markdown files are read as-is.

File type is validated by content (see
`app.ingestion.file_validation.validate_file_content`) before this
module is ever reached -- by the time `parse_document_to_text` runs,
the file has already been confirmed to genuinely be what its extension
claims.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.file_validation import PLAIN_TEXT_EXTENSIONS, SUPPORTED_EXTENSIONS

#: Kept for backwards-compatible imports elsewhere; the source of truth
#: for supported extensions now lives in `app.ingestion.file_validation`.
SUPPORTED_PLAIN_EXTENSIONS = PLAIN_TEXT_EXTENSIONS
SUPPORTED_RICH_EXTENSIONS = SUPPORTED_EXTENSIONS - PLAIN_TEXT_EXTENSIONS


class ParsingError(Exception):
    """Raised when a document's content cannot be parsed into text."""


def parse_document_to_text(file_path: str) -> str:
    """Parses a source document on disk into a single plain-text string.

    Args:
        file_path: Path to the previously-validated, previously-saved
            source document.

    Returns:
        The document's text, with `--- Page N ---` markers inserted
        where per-page provenance is available (PDF/DOCX via Docling).
        Plain text/Markdown files are returned as-is (no page concept).

    Raises:
        ParsingError: If the file extension isn't supported, or parsing
            fails for any other reason.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in PLAIN_TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix in SUPPORTED_RICH_EXTENSIONS:
        return _parse_with_docling(path)

    raise ParsingError(
        f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def _parse_with_docling(path: Path) -> str:
    """Parses a rich document (PDF/DOCX/...) into page-marked text via Docling.

    Args:
        path: Path to the document to parse.

    Returns:
        The document's text, page-annotated where possible (see
        `_export_with_page_markers`), or a flat markdown export as a
        fallback.

    Raises:
        ParsingError: If the `docling` package isn't installed.
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - optional heavy dependency
        raise ParsingError(
            "The 'docling' package is required to parse PDF/DOCX files. "
            "Install it with `uv sync` (it's declared in pyproject.toml)."
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(str(path))
    document = result.document

    try:
        return _export_with_page_markers(document)
    except Exception:
        return document.export_to_markdown()


def _export_with_page_markers(document) -> str:
    """Groups a Docling document's text items by page and marks each page.

    Args:
        document: A Docling `DoclingDocument` (from `ConversionResult.document`).

    Returns:
        Text with `--- Page N ---` markers between pages, so the model's
        evidence citations (`source_page_numbers`) can be grounded in
        something real.

    Raises:
        ValueError: If no page-provenance text items were found (the
            caller falls back to a flat export in that case).
    """
    pages: dict[int, list[str]] = {}

    for item, _level in document.iterate_items():
        text = getattr(item, "text", None)
        if not text:
            continue
        prov = getattr(item, "prov", None)
        page_no = None
        if prov:
            first = prov[0] if isinstance(prov, list) else prov
            page_no = getattr(first, "page_no", None)
        pages.setdefault(page_no or 0, []).append(text)

    if not pages:
        raise ValueError("No page-provenance text items found")

    chunks = []
    for page_no in sorted(pages.keys()):
        label = f"--- Page {page_no} ---" if page_no else "--- Page (unknown) ---"
        chunks.append(label + "\n" + "\n".join(pages[page_no]))
    return "\n\n".join(chunks)
