"""Scope Analysis output schema (plan section 9.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StakeholderItem(BaseModel):
    name: str = Field(..., description="Stakeholder or user group name.")
    role_or_group: str = Field(
        ...,
        description="Role, department, or user segment (e.g. admin, end customer).",
    )
    needs_or_interest: str = Field(
        ...,
        description="What they need from the system or why they matter to scope.",
    )


class OutOfScopeItem(BaseModel):
    item: str = Field(..., description="Item explicitly out of scope or assumed away.")
    rationale: str = Field(
        ...,
        description="Why it is out of scope or treated as an assumption.",
    )


class AmbiguityItem(BaseModel):
    question: str = Field(
        ...,
        description="Clarifying question for the client (max ~500 chars).",
        max_length=500,
    )
    why_it_matters: str = Field(
        ...,
        description="Impact if this remains unanswered.",
        max_length=500,
    )


class RiskItem(BaseModel):
    risk: str = Field(..., description="Risk description.", max_length=500)
    impact: str = Field(..., description="Business or delivery impact.", max_length=500)
    suggested_mitigation: str = Field(
        ...,
        description="Practical mitigation or next step.",
        max_length=500,
    )


class ScopeAnalysisOutput(BaseModel):
    executive_summary: str = Field(
        ...,
        description="Concise summary of the client request and proposed solution framing.",
        max_length=4000,
    )
    objectives: list[str] = Field(
        ...,
        description="Business objectives (3–12 bullet strings).",
        max_length=12,
    )
    stakeholders_and_users: list[StakeholderItem] = Field(
        ...,
        description="Key stakeholders and user groups.",
        max_length=20,
    )
    in_scope: list[str] = Field(
        ...,
        description="Capabilities or deliverables clearly in scope.",
        max_length=30,
    )
    out_of_scope_or_assumed: list[OutOfScopeItem] = Field(
        ...,
        description="Explicit exclusions and assumptions.",
        max_length=25,
    )
    ambiguities_and_questions: list[AmbiguityItem] = Field(
        ...,
        description="Open questions for the client (aim for at most 25 items).",
    )
    risks: list[RiskItem] = Field(
        ...,
        description="Delivery or product risks.",
        max_length=20,
    )
    dependencies: list[str] = Field(
        ...,
        description="External systems, teams, or prerequisites (aim for at most 20).",
    )
    assumptions: list[str] = Field(
        ...,
        description="Working assumptions pending confirmation (aim for at most 20).",
    )
