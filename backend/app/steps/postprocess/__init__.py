"""Step-specific post-processing hooks run in code after schema validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel


class PostprocessError(Exception):
    """Post-processing could not produce a usable document (generation fails)."""


@dataclass(frozen=True)
class PostprocessContext:
    """Facts from approved upstream outputs needed to validate references."""

    # Reference prefix (e.g. "G") -> number of items in the approved source section.
    ref_counts: dict[str, int] = field(default_factory=dict)
    max_features: int = 250
    feature_ids: tuple[str, ...] = ()
    feature_titles: dict[str, str] = field(default_factory=dict)
    feature_priorities: dict[str, str] = field(default_factory=dict)
    feature_depends: dict[str, tuple[str, ...]] = field(default_factory=dict)
    high_medium_gap_refs: tuple[str, ...] = ()
    selected_phases: tuple[str, ...] = ()
    estimated_role_names: tuple[str, ...] = ()
    user_inputs: dict = field(default_factory=dict)
    max_work_packages: int = 40
    max_effort_lines: int = 1800
    max_assumptions: int = 40
    max_components: int = 10
    feature_risk_domains: dict[str, str] = field(default_factory=dict)
    feature_origins: dict[str, str] = field(default_factory=dict)
    feature_gap_refs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    gap_severities: dict[str, str] = field(default_factory=dict)
    role_disciplines: dict[str, str] = field(default_factory=dict)
    source_requirements_total: int = 0
    implied_count: int = 0
    suggested_count: int = 0
    project_id: str = ""
    version_no: int = 1
    scope_content: dict | None = None
    gap_content: dict | None = None
    feature_list_content: dict | None = None
    estimate_content: dict | None = None
    estimate_user_inputs: dict = field(default_factory=dict)
    srs_content: dict | None = None
    sprint_plan_content: dict | None = None
    frs_revision_parts: tuple[str, ...] = ()


# Returns the stored model plus integer-only validation notes (never text).
PostprocessFn = Callable[[BaseModel, PostprocessContext], tuple[BaseModel, dict[str, int]]]
