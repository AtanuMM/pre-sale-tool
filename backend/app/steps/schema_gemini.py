"""Helpers to inspect Pydantic schemas as converted for Gemini requests."""

from __future__ import annotations

from typing import Any

from google.genai import _transformers as genai_transformers

FORBIDDEN_JSON_SCHEMA_KEYS = frozenset(
    {"anyOf", "oneOf", "allOf", "additionalProperties", "additional_properties"}
)


def gemini_processed_schema_dict(model: type) -> dict[str, Any]:
    schema = genai_transformers.t_schema(None, model)
    if schema is None:
        raise ValueError("Schema conversion returned None")
    return schema.model_dump(exclude_unset=True)


def collect_forbidden_keywords(node: Any) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_JSON_SCHEMA_KEYS:
                    found.append(key)
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(node)
    return found
