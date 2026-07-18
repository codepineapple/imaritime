"""Content-based file type validation.

Checking only a filename's extension is easy to spoof (accidentally or
otherwise) -- a renamed `.exe` can claim to be `.pdf`. This module
inspects the actual file bytes (magic-number/content sniffing via
`python-magic`, falling back to the pure-Python `filetype` package if
libmagic isn't available) and cross-checks the result against what the
claimed extension implies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import filetype

try:
    import magic

    _HAS_LIBMAGIC = True
except ImportError:  # pragma: no cover - environment-dependent
    _HAS_LIBMAGIC = False


class UnsupportedFileTypeError(Exception):
    """Raised when a file's extension is unsupported, or its actual
    content doesn't match what that extension implies."""


#: Extensions parsed via Docling, and the MIME type(s) libmagic/filetype
#: may reasonably report for a genuine file of that type. Office Open
#: XML formats (.docx/.pptx) are themselves zip containers, so some
#: detectors only get as far as reporting "application/zip" -- accepted
#: too, rather than rejecting genuine files over a detector limitation.
_EXPECTED_MIME_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
    ".html": {"text/html"},
    ".htm": {"text/html"},
}

#: Extensions with no reliable magic number -- validated by decodability
#: instead (see `_looks_like_text`).
PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}

SUPPORTED_EXTENSIONS = PLAIN_TEXT_EXTENSIONS | set(_EXPECTED_MIME_TYPES)


def detect_mime_type(content: bytes) -> Optional[str]:
    """Detects a file's MIME type from its content (magic bytes).

    Args:
        content: Raw file bytes to inspect.

    Returns:
        The detected MIME type string, or None if it couldn't be
        determined by either backend.
    """
    if _HAS_LIBMAGIC:
        try:
            return magic.from_buffer(content, mime=True)
        except Exception:  # noqa: BLE001 - fall back to filetype below
            pass

    guess = filetype.guess(content)
    return guess.mime if guess else None


def _looks_like_text(content: bytes, sample_size: int = 8192) -> bool:
    """Heuristically checks whether content is plausibly UTF-8 text.

    Plain text/Markdown files have no magic number to check, so this
    instead verifies the sample is valid UTF-8 with no NUL bytes and few
    non-whitespace control characters -- the kind of thing a renamed
    binary file would fail.

    Args:
        content: Raw file bytes to inspect.
        sample_size: How many leading bytes to sample.

    Returns:
        True if the sample looks like genuine text.
    """
    sample = content[:sample_size]
    if b"\x00" in sample:
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text.strip():
        return True  # an empty/whitespace-only file isn't "not text"
    control_chars = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    return (control_chars / len(text)) < 0.01


def validate_file_content(filename: str, content: bytes) -> None:
    """Validates that a file's actual content matches its claimed extension.

    Args:
        filename: The uploaded filename (its extension determines what
            content is expected).
        content: The raw uploaded file bytes.

    Raises:
        UnsupportedFileTypeError: If the extension isn't supported, or
            the file's actual content doesn't match what that extension
            implies (wrong/corrupted/mislabeled file).
    """
    suffix = Path(filename).suffix.lower()

    if suffix in PLAIN_TEXT_EXTENSIONS:
        if not _looks_like_text(content):
            raise UnsupportedFileTypeError(
                f"'{filename}' has a text extension ({suffix}) but its content "
                "doesn't decode as plain UTF-8 text -- it may be a renamed "
                "binary file."
            )
        return

    expected = _EXPECTED_MIME_TYPES.get(suffix)
    if expected is None:
        raise UnsupportedFileTypeError(
            f"Unsupported file extension '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    detected = detect_mime_type(content)
    if detected is None:
        raise UnsupportedFileTypeError(
            f"Could not determine the actual content type of '{filename}' to "
            f"verify it is really a {suffix} file."
        )
    if detected not in expected:
        raise UnsupportedFileTypeError(
            f"'{filename}' has extension '{suffix}' but its content was detected "
            f"as '{detected}', not one of {sorted(expected)}. The file may be "
            "mislabeled, corrupted, or a different format than its extension suggests."
        )
