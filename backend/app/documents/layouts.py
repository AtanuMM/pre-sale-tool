"""Resolve DOCX layout from step definitions, content-aware for Estimate v1 vs v2."""

from __future__ import annotations

from typing import Any

from app.steps.definitions import get_step
from app.steps.layout_config import SectionLayoutSpec
from app.steps.layouts_registry import ESTIMATE_LAYOUT, ESTIMATE_V2_LAYOUT


def content_schema_version(content: dict[str, Any] | None) -> int:
    if not isinstance(content, dict):
        return 1
    raw = content.get("schema_version")
    if isinstance(raw, int) and raw == 2:
        return 2
    return 1


def layout_for_step(
    step_key: str, content: dict[str, Any] | None = None
) -> tuple[SectionLayoutSpec, ...] | None:
    try:
        defn = get_step(step_key)
    except KeyError:
        return None
    if not defn.layout:
        return None
    if step_key == "estimate" and content_schema_version(content) != 2:
        return ESTIMATE_LAYOUT
    if step_key == "estimate":
        return ESTIMATE_V2_LAYOUT
    return defn.layout
