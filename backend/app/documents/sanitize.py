"""Plain-text sanitization for untrusted model output in DOCX."""

from __future__ import annotations

import re

# XML 1.0 invalid control chars (keep tab, LF, CR).
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def sanitize_docx_text(value: str) -> str:
    return _XML_INVALID.sub("", value)


def sanitize_optional_text(value: str | None) -> str:
    if value is None:
        return ""
    return sanitize_docx_text(value)
