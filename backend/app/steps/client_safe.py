"""Client-safe projection deny-list (SOW, SRS, and related prompts)."""

from __future__ import annotations

import json
from typing import Any

FORBIDDEN_PROMPT_SUBSTRINGS: frozenset[str] = frozenset(
    {
        "ai_gain",
        "ai_leverage",
        "confidence_raw",
        "guardrail_codes",
        "hours_with_ai",
        "best_hours",
        "worst_hours",
        "likely_hours",
        "recommended_hours",
        "health_rows",
        "project_ai_cap",
        "hourly_rate",
        "validation_notes",
        "default_allowance",
        "effort_lines",
        "computed",
        "headcount",
        "hours_per_week",
        "utilisation",
        "utilization",
        "ceremony_overhead_pct",
        "load_percent",
        "planned_hours",
        "per_role",
        "tokens_in",
        "tokens_out",
    }
)


def assert_client_safe(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False).casefold()
    for token in FORBIDDEN_PROMPT_SUBSTRINGS:
        if token.casefold() in text:
            raise ValueError(f"client-unsafe projection contains {token!r}")
