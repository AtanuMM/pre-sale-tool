"""FRS post-processing fixtures."""

from __future__ import annotations

from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.frs import postprocess_frs
from app.steps.schemas.frs import (
    AcceptanceCriterionDraft,
    FeatureSpecDraft,
    FlowStepItem,
    FrsModuleBatchOutput,
    FrsPasses,
    FrsPlanningOutput,
    FrsStored,
    RoleItem,
)


def _minimal_spec(fid: str, req_ids: list[str]) -> FeatureSpecDraft:
    return FeatureSpecDraft(
        feature_id=fid,
        summary=f"Behaviour for {fid}",
        actors=["User"],
        preconditions=["User is signed in"],
        trigger="User opens the screen",
        main_flow=[
            FlowStepItem(actor="User", action="Submit", system_response="System validates"),
        ],
        linked_requirement_ids=req_ids,
        acceptance_criteria=[
            AcceptanceCriterionDraft(
                scenario_title="Happy path",
                given="Signed in",
                when="User submits",
                then="System accepts",
                covers_requirement_ids=req_ids[:1],
            )
        ],
    )


def test_coverage_fixture_three_features_seven_reqs() -> None:
    srs = {
        "functional_requirements": [
            {"id": f"FR-A-{i:03d}", "feature_id": f"F-00{(i % 3) + 1}"}
            for i in range(1, 8)
        ]
    }
    ctx = PostprocessContext(
        project_id="abc12345-0000-0000-0000-000000000001",
        version_no=1,
        feature_ids=("F-001", "F-002", "F-003"),
        feature_list_content={
            "features": [
                {"id": "F-001", "title": "A", "module": "M1", "priority": "must", "phase": "mvp"},
                {"id": "F-002", "title": "B", "module": "M1", "priority": "must", "phase": "mvp"},
                {"id": "F-003", "title": "C", "module": "M1", "priority": "must", "phase": "mvp"},
            ]
        },
        srs_content=srs,
        sprint_plan_content={"stories": []},
        user_inputs={"detail_level": "detailed"},
    )
    passes = FrsPasses(
        planning=FrsPlanningOutput(roles=[RoleItem(name="User", description="End user", typical_permissions="view")]),
        modules={
            "M1": FrsModuleBatchOutput(
                module="M1",
                specifications=[
                    _minimal_spec("F-001", ["FR-A-001", "FR-A-004"]),
                    _minimal_spec("F-002", ["FR-A-002", "FR-A-005"]),
                    _minimal_spec("F-003", ["FR-A-003", "FR-A-006"]),
                ],
            )
        },
    )
    draft = FrsStored(passes=passes, assembled={"document_reference": "pending"})  # type: ignore[arg-type]
    stored, _notes = postprocess_frs(draft, ctx)
    assert stored.viewer.srs_coverage_pct == 85.7
    assert "FR-A-007" in stored.viewer.uncovered_srs_ids
