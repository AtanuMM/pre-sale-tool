"""Seed approved step versions for workflow E2E tests."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.steps import StepVersion


def seed_approved_step(
    session: Session,
    *,
    project_id: uuid.UUID,
    step_key: str,
    content: dict[str, Any],
    created_by: uuid.UUID | None,
    version_no: int = 1,
) -> StepVersion:
    row = StepVersion(
        project_id=project_id,
        step_key=step_key,
        version_no=version_no,
        status="approved",
        source="generated",
        content=content,
        inputs={},
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row


def minimal_feature_list_content() -> dict[str, Any]:
    return {
        "summary": "E2E feature list.",
        "modules": [{"name": "Auth", "purpose": "Sign-in"}],
        "features": [
            {
                "id": "F-001",
                "module": "Auth",
                "title": "Sign in",
                "description": "Users sign in.",
                "platforms": ["web"],
                "priority": "must",
                "phase": "mvp",
                "origin": "stated",
                "depends_on_ids": [],
                "primary_risk_domain": "none",
            }
        ],
    }


def minimal_estimate_v2_content() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "phases": [{"phase": "mvp", "label": "MVP", "goal": "Core"}],
        "components": [{"name": "API", "description": "Backend"}],
        "work_packages": [],
        "feature_estimates": [
            {
                "feature_id": "F-001",
                "title": "Sign in",
                "phase": "mvp",
                "component": "API",
                "priority": "must",
            }
        ],
        "computed": {
            "feature_rows": [
                {
                    "id": "F-001",
                    "per_role": {
                        "Developer": {"recommended": 40},
                        "QA": {"recommended": 12},
                    },
                }
            ],
            "phase_rows": [{"phase": "mvp", "weeks_planned": 4.0}],
            "totals": {"weeks_planned": 4.0, "hours_without_ai": 52.0},
        },
    }


def minimal_sow_content() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "assembled": {"document_reference": "SOW-E2E-001", "sections": []},
    }


def minimal_srs_content() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "assembled": {"document_reference": "SRS-E2E-001"},
        "functional_requirements": [],
    }


def seed_sprint_plan_prerequisites(
    session: Session,
    *,
    project_id: uuid.UUID,
    admin_id: uuid.UUID | None,
) -> None:
    """Approved steps 1–6 so sprint_plan is ready to generate."""
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="scope_analysis",
        content={"executive_summary": "E2E scope.", "objectives": ["Deliver MVP"]},
        created_by=admin_id,
    )
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="gap_analysis",
        content={"summary": "No gaps.", "gaps": [], "client_questions": []},
        created_by=admin_id,
    )
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="feature_list",
        content=minimal_feature_list_content(),
        created_by=admin_id,
    )
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="estimate",
        content=minimal_estimate_v2_content(),
        created_by=admin_id,
        version_no=1,
    )
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="sow",
        content=minimal_sow_content(),
        created_by=admin_id,
    )
    seed_approved_step(
        session,
        project_id=project_id,
        step_key="srs",
        content=minimal_srs_content(),
        created_by=admin_id,
    )
    session.commit()
