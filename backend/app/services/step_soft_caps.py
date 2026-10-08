"""Post-validation list soft caps from step definitions."""

from __future__ import annotations

from pydantic import BaseModel

from app.config import get_settings
from app.steps.definitions import SoftListCap, StepDefinition


def _cap_value(defn: StepDefinition, cap: SoftListCap) -> int:
    if cap.settings_key:
        return int(getattr(get_settings(), cap.settings_key))
    return cap.limit


def apply_soft_list_caps(defn: StepDefinition, content: BaseModel) -> tuple[dict, BaseModel]:
    if not defn.soft_list_caps or defn.output_schema is None:
        return {}, content
    data = content.model_dump()
    trim_meta: dict[str, dict[str, int]] = {}
    for cap in defn.soft_list_caps:
        items = data.get(cap.field)
        if not isinstance(items, list):
            continue
        limit = _cap_value(defn, cap)
        if len(items) > limit:
            removed = len(items) - limit
            data[cap.field] = items[:limit]
            trim_meta[cap.field] = {"removed": removed}
    trimmed = defn.output_schema.model_validate(data)
    list_trim = {"list_trim": trim_meta} if trim_meta else {}
    return list_trim, trimmed
