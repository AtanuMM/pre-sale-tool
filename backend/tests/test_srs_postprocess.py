from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.srs import postprocess_srs
from app.steps.schemas.srs import (
    DiagramEdge,
    DiagramLane,
    DiagramNode,
    DiagramSpec,
    FunctionalRequirementDraft,
    SrsAssembled,
    SrsHealthMeta,
    SrsModuleBatchOutput,
    SrsPasses,
    SrsPlanningPassAOutput,
    SrsPlanningPassBOutput,
    SrsStored,
)


def _minimal_diagram(kind: str) -> DiagramSpec:
    return DiagramSpec(
        kind=kind,  # type: ignore[arg-type]
        title=f"{kind} diagram",
        caption=f"Caption for {kind}",
        lanes=[DiagramLane(name="App", order=0)],
        nodes=[
            DiagramNode(id="n1", label="User", lane="App", node_type="person"),
            DiagramNode(id="n2", label="System", lane="App", node_type="web_app"),
        ],
        edges=[DiagramEdge(**{"from": "n1", "to": "n2", "label": "uses"})],
    )


def _planning_a() -> SrsPlanningPassAOutput:
    return SrsPlanningPassAOutput(
        purpose="Purpose",
        scope_statement="Scope",
        overview="Overview",
        product_perspective="Perspective",
        user_classes=["Admin"],
        operating_environment="Cloud",
        constraints=[],
        assumptions_and_dependencies=[],
        architecture_style="Layered",
        architecture_principles=["Separation of concerns"],
        components=[],
        data_stores=["PostgreSQL"],
        queues=[],
        integrations=[],
        architecture_decisions=[],
        technology_stack=[],
        deployment_environments=["production"],
        network_zones=["DMZ"],
        scaling_ha_approach="Horizontal scaling",
        backup_dr_approach="Daily backups",
        monitoring_logging="Centralised logs",
        cicd_approach="Pipeline per environment",
        security_architecture="Role-based access",
        context_diagram=_minimal_diagram("context"),
        architecture_diagram=_minimal_diagram("architecture"),
        deployment_diagram=_minimal_diagram("deployment"),
        er_diagram=DiagramSpec(
            kind="er",
            title="ER",
            caption="ER caption",
            entities=[],
            relationships=[],
        ),
    )


def test_postprocess_assigns_fr_ids_and_health() -> None:
    passes = SrsPasses(
        planning_a=_planning_a(),
        planning_b=SrsPlanningPassBOutput(
            data_entities=[],
            data_relationships=[],
            external_interfaces=[],
            api_standards="REST JSON",
            nfr_catalogue=[],
            compliance_requirements=[],
            glossary_terms=[],
        ),
        modules={
            "Auth": SrsModuleBatchOutput(
                module_name="Auth",
                module_overview="Authentication module",
                actors=["User"],
                functional_requirements=[
                    FunctionalRequirementDraft(
                        feature_id="F-001",
                        title="Login",
                        statement="The system shall allow users to sign in.",
                        rationale="Required by scope.",
                        acceptance_criteria=["User can sign in with valid credentials."],
                        basis="stated",
                        source_ref="REQ-1",
                        verification_method="test",
                    )
                ],
            )
        },
    )
    draft = SrsStored(
        passes=passes,
        functional_requirements=[],
        nfr_requirements=[],
        interfaces=[],
        entities=[],
        assembled=SrsAssembled(document_reference="pending"),
        viewer=SrsHealthMeta(),
    )
    ctx = PostprocessContext(
        feature_ids=("F-001",),
        feature_titles={"F-001": "Login"},
        feature_priorities={"F-001": "must"},
        project_id="00000000-0000-0000-0000-000000000001",
        version_no=1,
        feature_list_content={
            "features": [
                {
                    "id": "F-001",
                    "module": "Auth",
                    "priority": "must",
                    "source_requirement_ids": ["REQ-1"],
                }
            ]
        },
        estimate_content={
            "schema_version": 2,
            "feature_estimates": [{"feature_id": "F-001", "phase": "mvp", "priority": "must"}],
        },
        user_inputs={"detail_level": "detailed"},
    )
    stored, notes = postprocess_srs(draft, ctx)
    assert stored.functional_requirements[0].id.startswith("FR-")
    assert notes["functional_requirements"] == 1
    assert stored.viewer.features_covered_pct == 100.0
