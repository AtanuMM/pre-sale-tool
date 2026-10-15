"""Sprint Plan prompt templates v1."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "v1"

PLANNING_SYSTEM = (
    "You are a senior delivery lead writing a Scrum-based release and sprint plan. "
    "Use Scrum Guide terminology and INVEST guidance for stories. "
    "Never invent hour estimates, capacities, costs or calendar calculations."
)

STORIES_SYSTEM = (
    "You write user stories for one module batch. Each feature needs 1-5 stories with "
    "integer share_percent values summing to 100 per feature. At most one spike per feature."
)

GOALS_SYSTEM = (
    "You write sprint goals and release summaries given story titles and sprint markers only. "
    "Do not mention hours, capacity or velocity numbers."
)


def _block(title: str, payload: dict[str, Any]) -> str:
    return f"=== {title} ===\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def build_planning_pass_a_prompt(context: dict[str, Any], instructions: str | None) -> str:
    parts = [
        _block("CONTEXT", context),
        "Produce epics per module, Definition of Ready/Done additions, release exit criteria per committed phase, dependencies, and assumptions.",
    ]
    if instructions:
        parts.append(f"Reviewer instructions:\n{instructions}")
    return "\n\n".join(parts)


def build_planning_pass_b_prompt(context: dict[str, Any], instructions: str | None) -> str:
    parts = [
        _block("CONTEXT", context),
        "Produce risks (use gap_ref G-n when linked, else empty string) and lead-time actions.",
    ]
    if instructions:
        parts.append(f"Reviewer instructions:\n{instructions}")
    return "\n\n".join(parts)


def build_planning_pass_c_prompt(context: dict[str, Any], instructions: str | None) -> str:
    parts = [
        _block("CONTEXT", context),
        "Produce glossary terms relevant to this delivery (domain, integrations, roles).",
    ]
    if instructions:
        parts.append(f"Reviewer instructions:\n{instructions}")
    return "\n\n".join(parts)


def build_planning_prompt(context: dict[str, Any], instructions: str | None) -> str:
    return build_planning_pass_a_prompt(context, instructions)


def build_stories_prompt(
    context: dict[str, Any],
    module: str,
    features: list[dict[str, Any]],
    instructions: str | None,
) -> str:
    parts = [
        _block("CONTEXT", context),
        _block("MODULE", {"module": module, "features": features}),
        "Write stories for every feature listed.",
    ]
    if instructions:
        parts.append(f"Reviewer instructions:\n{instructions}")
    return "\n\n".join(parts)


def build_goals_prompt(sprint_outline: list[dict[str, Any]], instructions: str | None) -> str:
    parts = [
        _block("SPRINT_OUTLINE", {"sprints": sprint_outline}),
        "Write sprint goal and demo focus per sprint, release summaries, and executive summary.",
    ]
    if instructions:
        parts.append(f"Reviewer instructions:\n{instructions}")
    return "\n\n".join(parts)
