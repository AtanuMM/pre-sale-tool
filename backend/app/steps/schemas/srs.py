"""SRS pass output and stored schemas (ISO/IEC/IEEE 29148-oriented)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

BasisKind = Literal["stated", "derived", "proposed"]
VerificationMethod = Literal["test", "demonstration", "inspection", "analysis"]
DiagramKind = Literal["context", "architecture", "deployment", "er"]
NodeType = Literal[
    "person",
    "web_app",
    "mobile_app",
    "service",
    "api_gateway",
    "database",
    "cache",
    "queue",
    "storage",
    "external_system",
    "cdn",
    "load_balancer",
    "monitoring",
    "identity",
    "other",
]
EdgeStyle = Literal["solid", "dashed"]
EdgeDirection = Literal["one_way", "both"]
ErCardinality = Literal["1:1", "1:N", "N:M"]
NfrCategory = Literal[
    "performance",
    "scalability",
    "availability_and_reliability",
    "security",
    "privacy_and_compliance",
    "usability_and_accessibility",
    "maintainability",
    "compatibility",
    "observability_and_logging",
    "backup_and_dr",
    "localisation",
]

MANDATORY_NFR_CATEGORIES: tuple[str, ...] = (
    "performance",
    "scalability",
    "availability_and_reliability",
    "security",
    "privacy_and_compliance",
    "usability_and_accessibility",
    "maintainability",
    "compatibility",
    "observability_and_logging",
    "backup_and_dr",
)


class DiagramLane(BaseModel):
    name: str = Field(..., max_length=40)
    order: int = Field(..., ge=0, le=20)


class DiagramNode(BaseModel):
    id: str = Field(..., max_length=40)
    label: str = Field(..., max_length=40)
    lane: str = Field(..., max_length=40)
    node_type: NodeType
    zone: str | None = Field(default=None, max_length=40)


class DiagramEdge(BaseModel):
    from_id: str = Field(..., alias="from", max_length=40)
    to_id: str = Field(..., alias="to", max_length=40)
    label: str = Field(default="", max_length=30)
    style: EdgeStyle = "solid"
    direction: EdgeDirection = "one_way"

    model_config = {"populate_by_name": True}


class ErEntity(BaseModel):
    name: str = Field(..., max_length=60)
    attributes: list[str] = Field(default_factory=list, max_length=12)
    primary_key: str = Field(..., max_length=40)


class ErRelationship(BaseModel):
    from_entity: str = Field(..., alias="from", max_length=60)
    to_entity: str = Field(..., alias="to", max_length=60)
    cardinality: ErCardinality
    label: str = Field(default="", max_length=40)

    model_config = {"populate_by_name": True}


class DiagramSpec(BaseModel):
    kind: DiagramKind
    title: str = Field(..., max_length=120)
    caption: str = Field(..., max_length=300)
    lanes: list[DiagramLane] = Field(default_factory=list)
    nodes: list[DiagramNode] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
    entities: list[ErEntity] = Field(default_factory=list)
    relationships: list[ErRelationship] = Field(default_factory=list)


class ArchitectureDecisionItem(BaseModel):
    decision: str = Field(..., max_length=300)
    options_considered: list[str] = Field(default_factory=list)
    chosen_option: str = Field(..., max_length=200)
    rationale: str = Field(..., max_length=800)
    status: Literal["proposed"] = "proposed"


class TechnologyStackItem(BaseModel):
    layer: str = Field(..., max_length=80)
    technology: str = Field(..., max_length=120)
    basis: BasisKind


class ArchitectureComponentItem(BaseModel):
    name: str = Field(..., max_length=80)
    layer: str = Field(..., max_length=80)
    responsibilities: str = Field(..., max_length=600)


class SrsPlanningPassAOutput(BaseModel):
    purpose: str = Field(..., max_length=4000)
    scope_statement: str = Field(..., max_length=4000)
    overview: str = Field(..., max_length=4000)
    product_perspective: str = Field(..., max_length=4000)
    user_classes: list[str] = Field(default_factory=list)
    operating_environment: str = Field(..., max_length=3000)
    constraints: list[str] = Field(default_factory=list)
    assumptions_and_dependencies: list[str] = Field(default_factory=list)
    architecture_style: str = Field(..., max_length=500)
    architecture_principles: list[str] = Field(default_factory=list)
    components: list[ArchitectureComponentItem] = Field(default_factory=list)
    data_stores: list[str] = Field(default_factory=list)
    queues: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    architecture_decisions: list[ArchitectureDecisionItem] = Field(default_factory=list)
    technology_stack: list[TechnologyStackItem] = Field(default_factory=list)
    deployment_environments: list[str] = Field(default_factory=list)
    network_zones: list[str] = Field(default_factory=list)
    scaling_ha_approach: str = Field(..., max_length=2000)
    backup_dr_approach: str = Field(..., max_length=2000)
    monitoring_logging: str = Field(..., max_length=2000)
    cicd_approach: str = Field(..., max_length=2000)
    security_architecture: str = Field(..., max_length=3000)
    context_diagram: DiagramSpec
    architecture_diagram: DiagramSpec
    deployment_diagram: DiagramSpec
    er_diagram: DiagramSpec


class DataEntityItem(BaseModel):
    name: str = Field(..., max_length=60)
    key_attributes: list[str] = Field(default_factory=list)
    retention_hint: str = Field(default="", max_length=300)


class DataRelationshipItem(BaseModel):
    from_entity: str = Field(..., alias="from", max_length=60)
    to_entity: str = Field(..., alias="to", max_length=60)
    cardinality: ErCardinality
    label: str = Field(default="", max_length=80)

    model_config = {"populate_by_name": True}


class ExternalInterfaceItem(BaseModel):
    system: str = Field(..., max_length=120)
    direction: str = Field(..., max_length=40)
    protocol: str = Field(..., max_length=80)
    purpose: str = Field(..., max_length=400)
    authentication: str = Field(..., max_length=200)


class NfrCatalogueItem(BaseModel):
    category: NfrCategory
    statement: str = Field(..., max_length=800)
    metric: str = Field(default="", max_length=200)
    target: str = Field(default="", max_length=200)
    basis: BasisKind
    source_ref: str = Field(default="", max_length=40)
    verification_method: VerificationMethod


class ComplianceRequirementItem(BaseModel):
    standard: str = Field(..., max_length=40)
    requirement: str = Field(..., max_length=800)
    basis: BasisKind


class SrsPlanningPassBOutput(BaseModel):
    data_entities: list[DataEntityItem] = Field(default_factory=list)
    data_relationships: list[DataRelationshipItem] = Field(default_factory=list)
    external_interfaces: list[ExternalInterfaceItem] = Field(default_factory=list)
    api_standards: str = Field(..., max_length=2000)
    nfr_catalogue: list[NfrCatalogueItem] = Field(default_factory=list)
    compliance_requirements: list[ComplianceRequirementItem] = Field(default_factory=list)
    glossary_terms: list[GlossaryTermItem] = Field(default_factory=list)


class GlossaryTermItem(BaseModel):
    term: str = Field(..., max_length=80)
    definition: str = Field(..., max_length=400)


class FunctionalRequirementDraft(BaseModel):
    feature_id: str = Field(..., max_length=16)
    title: str = Field(..., max_length=200)
    statement: str = Field(..., max_length=1200)
    rationale: str = Field(..., max_length=800)
    acceptance_criteria: list[str] = Field(default_factory=list)
    basis: BasisKind
    source_ref: str = Field(default="", max_length=40)
    verification_method: VerificationMethod


class PermissionSummaryItem(BaseModel):
    role: str = Field(..., max_length=80)
    allowed_actions: list[str] = Field(default_factory=list)


class SrsModuleBatchOutput(BaseModel):
    module_name: str = Field(..., max_length=120)
    module_overview: str = Field(..., max_length=2000)
    actors: list[str] = Field(default_factory=list)
    functional_requirements: list[FunctionalRequirementDraft] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    data_entities_used: list[str] = Field(default_factory=list)
    interfaces_used: list[str] = Field(default_factory=list)
    permission_summary: list[PermissionSummaryItem] = Field(default_factory=list)


class SrsCoverageRepairOutput(BaseModel):
    functional_requirements: list[FunctionalRequirementDraft] = Field(default_factory=list)
    nfr_items: list[NfrCatalogueItem] = Field(default_factory=list)


class StoredFunctionalRequirement(BaseModel):
    id: str
    feature_id: str
    module: str
    title: str
    statement: str
    rationale: str
    acceptance_criteria: list[str]
    basis: BasisKind
    source_ref: str
    source_requirement_ids: list[str] = Field(default_factory=list)
    priority: str
    phase: str
    verification_method: VerificationMethod
    proposed_target: bool = False
    weak_language: bool = False
    missing_shall: bool = False


class StoredNfrRequirement(BaseModel):
    id: str
    category: str
    statement: str
    metric: str
    target: str
    basis: BasisKind
    source_ref: str
    verification_method: VerificationMethod
    proposed_target: bool = False


class DiagramStatusItem(BaseModel):
    key: str
    kind: str
    title: str
    caption: str
    status: Literal["ok", "repaired", "fallback_table", "invalid"]
    warning: str = ""


class SrsHealthMeta(BaseModel):
    requirements_per_feature: float = 0.0
    features_covered_pct: float = 0.0
    basis_stated: int = 0
    basis_derived: int = 0
    basis_proposed: int = 0
    weak_language_warnings: int = 0
    missing_shall: int = 0
    nfr_categories_covered: int = 0
    nfr_categories_required: int = 0
    proposed_target_pct: float = 0.0
    placeholder_count: int = 0
    approx_pages: float = 0.0
    diagrams: list[DiagramStatusItem] = Field(default_factory=list)


class SrsAssembled(BaseModel):
    document_reference: str
    revision_history: list[dict[str, str]] = Field(default_factory=list)
    status_text: str = "In review"
    parameter_table: list[dict[str, str]] = Field(default_factory=list)
    standards_references: list[str] = Field(default_factory=list)
    figures: list[dict[str, str]] = Field(default_factory=list)
    tables: list[dict[str, str]] = Field(default_factory=list)
    placeholders: list[dict[str, str]] = Field(default_factory=list)
    open_issues: list[dict[str, str]] = Field(default_factory=list)
    glossary: list[dict[str, str]] = Field(default_factory=list)
    traceability: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    diagram_specs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    module_sections: list[dict[str, Any]] = Field(default_factory=list)


class SrsPasses(BaseModel):
    planning_a: SrsPlanningPassAOutput | None = None
    planning_b: SrsPlanningPassBOutput | None = None
    modules: dict[str, SrsModuleBatchOutput] = Field(default_factory=dict)
    coverage_repair: SrsCoverageRepairOutput | None = None


class SrsStored(BaseModel):
    schema_version: int = 1
    passes: SrsPasses
    functional_requirements: list[StoredFunctionalRequirement] = Field(default_factory=list)
    nfr_requirements: list[StoredNfrRequirement] = Field(default_factory=list)
    interfaces: list[ExternalInterfaceItem] = Field(default_factory=list)
    entities: list[DataEntityItem] = Field(default_factory=list)
    assembled: SrsAssembled
    viewer: SrsHealthMeta = Field(default_factory=SrsHealthMeta)
