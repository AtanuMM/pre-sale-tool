"""Sanitise diagram labels (no control chars, length caps)."""

from __future__ import annotations

import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_label(text: str, *, max_len: int = 200) -> str:
    cleaned = _CONTROL_RE.sub("", text or "")
    cleaned = cleaned.replace("<", "").replace(">", "")
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned
