from __future__ import annotations

from app.steps.client_safe import FORBIDDEN_PROMPT_SUBSTRINGS
from app.steps.sprint_plan_projection import build_sprint_plan_context


def test_projection_is_client_safe() -> None:
    ctx = build_sprint_plan_context(
        scope={"executive_summary": "Summary", "objectives": [], "risks": []},
        gap={"gaps": [{"severity": "high", "title": "Gap", "clarification_question": "Q?"}]},
        feature_list={
            "modules": [{"name": "Auth"}],
            "features": [
                {
                    "id": "F-001",
                    "title": "Login",
                    "description": "Sign in",
                    "module": "Auth",
                    "priority": "must",
                    "depends_on_ids": [],
                    "primary_risk_domain": "none",
                    "source_requirement_ids": [],
                    "phase": "mvp",
                }
            ],
        },
        estimate={
            "schema_version": 2,
            "phases": [{"phase": "mvp", "label": "MVP"}],
            "components": [{"name": "Web"}],
            "work_packages": [
                {
                    "id": "WP-1",
                    "title": "Setup",
                    "package_type": "project_setup_architecture",
                    "phase": "mvp",
                    "component": "Web",
                }
            ],
        },
        estimate_user_inputs={
            "team": [{"role": "Developer", "discipline": "development", "mode": "estimated"}]
        },
        sow={"narrative": {"milestones": []}, "assembled": {"deliverables": []}},
        srs={"functional_requirements": [{"id": "FR-1", "feature_id": "F-001", "title": "Login"}]},
        sprint_user_inputs={"sprint_length_weeks": 2, "notes": "Plan notes"},
    )
    blob = str(ctx).casefold()
    for token in FORBIDDEN_PROMPT_SUBSTRINGS:
        assert token.casefold() not in blob
