"""Gap Analysis output schema (plan section 9.2). Gemini-safe: enums via Literal, no list maxItems."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GapCategory = Literal[
    "missing_requirement",
    "ambiguity",
    "conflict",
    "undefined_nfr",
    "unknown_integration",
    "compliance",
]

GapSeverity = Literal["high", "medium", "low"]


class GapItem(BaseModel):
    title: str = Field(..., description="Short gap title.", max_length=300)
    category: GapCategory = Field(..., description="Gap category.")
    severity: GapSeverity = Field(..., description="Severity for estimation impact.")
    description: str = Field(..., description="What is missing or unclear.", max_length=2000)
    why_it_matters: str = Field(..., description="Delivery or scope impact.", max_length=1000)
    clarification_question: str = Field(
        ...,
        description="Concrete question for the client.",
        max_length=500,
    )
    suggested_default_assumption: str = Field(
        ...,
        description="Reasonable assumption if unanswered.",
        max_length=500,
    )
    related_scope_section: str | None = Field(
        default=None,
        description="Optional reference to scope analysis section.",
        max_length=300,
    )


class GapAnalysisOutput(BaseModel):
    summary: str = Field(
        ...,
        description="Brief overview of overall gap posture.",
        max_length=4000,
    )
    gaps: list[GapItem] = Field(
        ...,
        description="Identified gaps with evidence from intake or scope analysis.",
    )
    client_questions: list[str] = Field(
        ...,
        description="Consolidated numbered-ready questions for the client.",
    )
