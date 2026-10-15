"""Position-based reference labels for layout sections (display/prompt only)."""

from __future__ import annotations

import copy
import re
from typing import Any

from app.steps.layout_config import SectionLayoutSpec

_REF_RE = re.compile(r"^([A-Za-z]+)-(\d+)$")


def ref_label(prefix: str, index: int) -> str:
    """1-based position -> label, e.g. ("G", 1) -> "G-1"."""
    return f"{prefix}-{index}"


def parse_ref(value: str) -> tuple[str, int] | None:
    match = _REF_RE.match(value.strip())
    if match is None:
        return None
    return match.group(1).upper(), int(match.group(2))


def ref_sections(layout: tuple[SectionLayoutSpec, ...]) -> tuple[SectionLayoutSpec, ...]:
    return tuple(s for s in layout if s.ref_prefix)


def section_ref_count(content: dict[str, Any], section: SectionLayoutSpec) -> int:
    raw = content.get(section.key)
    return len(raw) if isinstance(raw, list) else 0


def annotate_content_with_refs(
    layout: tuple[SectionLayoutSpec, ...], content: dict[str, Any]
) -> dict[str, Any]:
    """Return a deep copy of content with refs rendered on ref_prefix sections.

    Object items get a leading "ref" key; string items are prefixed "X-n: ".
    The stored content is never modified.
    """
    annotated = copy.deepcopy(content)
    for section in ref_sections(layout):
        raw = annotated.get(section.key)
        if not isinstance(raw, list) or section.ref_prefix is None:
            continue
        prefix = section.ref_prefix
        rendered: list[Any] = []
        for index, item in enumerate(raw, start=1):
            label = ref_label(prefix, index)
            if isinstance(item, dict):
                rendered.append({"ref": label, **item})
            elif isinstance(item, str):
                rendered.append(f"{label}: {item}")
            else:
                rendered.append(item)
        annotated[section.key] = rendered
    return annotated
