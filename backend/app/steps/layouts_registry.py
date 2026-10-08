"""Step layout definitions (shared by API, DOCX, validation)."""

from __future__ import annotations

from app.steps.layout_config import LayoutColumn, SectionKind, SectionLayoutSpec

SCOPE_ANALYSIS_LAYOUT: tuple[SectionLayoutSpec, ...] = (
    SectionLayoutSpec("executive_summary", "Executive summary", SectionKind.TEXT),
    SectionLayoutSpec("objectives", "Objectives", SectionKind.LIST),
    SectionLayoutSpec(
        "stakeholders_and_users",
        "Stakeholders and users",
        SectionKind.TABLE,
        columns=(
            LayoutColumn("name", "Name"),
            LayoutColumn("role_or_group", "Role / group"),
            LayoutColumn("needs_or_interest", "Needs / interest"),
        ),
    ),
    SectionLayoutSpec("in_scope", "In scope", SectionKind.LIST),
    SectionLayoutSpec(
        "out_of_scope_or_assumed",
        "Out of scope or assumed",
        SectionKind.TABLE,
        columns=(
            LayoutColumn("item", "Item"),
            LayoutColumn("rationale", "Rationale"),
        ),
    ),
    SectionLayoutSpec(
        "ambiguities_and_questions",
        "Ambiguities and questions",
        SectionKind.TABLE,
        columns=(
            LayoutColumn("question", "Question"),
            LayoutColumn("why_it_matters", "Why it matters"),
        ),
        copyable=True,
    ),
    SectionLayoutSpec(
        "risks",
        "Risks",
        SectionKind.TABLE,
        columns=(
            LayoutColumn("risk", "Risk"),
            LayoutColumn("impact", "Impact"),
            LayoutColumn("suggested_mitigation", "Suggested mitigation"),
        ),
    ),
    SectionLayoutSpec("dependencies", "Dependencies", SectionKind.LIST),
    SectionLayoutSpec("assumptions", "Assumptions", SectionKind.LIST),
)

GAP_ANALYSIS_LAYOUT: tuple[SectionLayoutSpec, ...] = (
    SectionLayoutSpec("summary", "Summary", SectionKind.TEXT),
    SectionLayoutSpec(
        "gaps",
        "Gaps",
        SectionKind.RECORDS,
        record_fields=(
            LayoutColumn("title", "Title"),
            LayoutColumn("description", "Description"),
            LayoutColumn("why_it_matters", "Why it matters"),
            LayoutColumn("clarification_question", "Clarification question"),
            LayoutColumn("suggested_default_assumption", "Default assumption"),
            LayoutColumn("related_scope_section", "Related scope section"),
        ),
        badge_fields=("severity", "category"),
    ),
    SectionLayoutSpec(
        "client_questions",
        "Client questions",
        SectionKind.NUMBERED_LIST,
        copyable=True,
    ),
)
