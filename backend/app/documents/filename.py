"""ASCII-safe filenames for step version exports."""

from __future__ import annotations

import re

_MAX_BASENAME_LEN = 180

_SLUG_INVALID = re.compile(r"[^a-z0-9]+")


def _slug_part(value: str) -> str:
    ascii_only = value.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_INVALID.sub("-", ascii_only.lower()).strip("-")
    return slug or "export"


def build_step_export_filename(
    *,
    project_name: str,
    step_key: str,
    version_no: int,
    is_draft: bool,
) -> str:
    project = _slug_part(project_name)[:60]
    step = _slug_part(step_key.replace("_", "-"))[:40]
    base = f"{project}-{step}-v{version_no}"
    if is_draft:
        base = f"{base}-DRAFT"
    if len(base) > _MAX_BASENAME_LEN:
        base = base[:_MAX_BASENAME_LEN].rstrip("-")
    return f"{base}.docx"
