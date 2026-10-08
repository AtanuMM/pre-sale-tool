"""Resolve DOCX layout from step definitions."""

from __future__ import annotations

from app.steps.definitions import get_step
from app.steps.layout_config import SectionLayoutSpec


def layout_for_step(step_key: str) -> tuple[SectionLayoutSpec, ...] | None:
    try:
        defn = get_step(step_key)
    except KeyError:
        return None
    if not defn.layout:
        return None
    return defn.layout
