"""FRS pass outputs and stored content.

LLM pass models omit ``max_length`` on list fields: Gemini rejects JSON schemas when
array ``maxItems`` is set above 1 on nested FRS models. Limits are enforced in postprocess.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

BasisKind = Literal["stated", "derived", "proposed"]
MessageKind = Literal["error", "success", "warning", "info"]
PermissionAction = Literal[
    "view", "create", "edit", "delete", "approve", "export", "configure"
]
DetailLevel = Literal["standard", "detailed", "comprehensive"]


class RoleItem(BaseModel):
    name: str = Field(..., max_length=80)
    description: str = Field(..., max_length=800)
    typical_permissions: str = Field(..., max_length=500)


class NavigationItem(BaseModel):
    role: str = Field(..., max_length=80)
    menu_label: str = Field(..., max_length=120)
    opens_feature_title: str = Field(..., max_length=200)


class StateTransitionDraft(BaseModel):
    from_state: str = Field(..., max_length=80)
    to_state: str = Field(..., max_length=80)
    trigger: str = Field(..., max_length=300)
    guard: str = Field(..., max_length=300)
    actor: str = Field(..., max_length=80)
    terminal: bool = False


class EntityStateModelDraft(BaseModel):
    entity_name: str = Field(..., max_length=120)
    states: list[str] = Field(default_factory=list)
    state_descriptions: list[str] = Field(default_factory=list)
    transitions: list[StateTransitionDraft] = Field(default_factory=list)


class FlowStepItem(BaseModel):
    actor: str = Field(..., max_length=80)
    action: str = Field(..., max_length=500)
    system_response: str = Field(..., max_length=800)


class AlternateFlowItem(BaseModel):
    condition: str = Field(..., max_length=400)
    steps: list[FlowStepItem] = Field(default_factory=list)
    rejoin_main_step: int = Field(..., ge=1, le=15)


class ExceptionFlowItem(BaseModel):
    condition: str = Field(..., max_length=400)
    handling: str = Field(..., max_length=600)
    message_ref: str = Field(..., max_length=120)


class BusinessRuleDraft(BaseModel):
    statement: str = Field(..., max_length=800)
    basis: BasisKind
    source_ref: str = Field(..., max_length=200)


class FieldSpecDraft(BaseModel):
    name: str = Field(..., max_length=80)
    label: str = Field(..., max_length=120)
    field_type: str = Field(..., max_length=40)
    required_mode: Literal["yes", "no", "conditional"] = "no"
    validation: str = Field(..., max_length=400)
    default_value: str = Field(..., max_length=200)
    entity_ref: str = Field(default="", max_length=120)
    help_text: str = Field(default="", max_length=400)
    basis: BasisKind = "derived"


class ScreenDraft(BaseModel):
    name: str = Field(..., max_length=120)
    purpose: str = Field(..., max_length=400)
    key_components: str = Field(..., max_length=600)
    states_note: str = Field(..., max_length=400)


class MessageDraft(BaseModel):
    kind: MessageKind
    trigger: str = Field(..., max_length=300)
    text: str = Field(..., max_length=500)


class NotificationDraft(BaseModel):
    event: str = Field(..., max_length=200)
    channel: str = Field(..., max_length=40)
    recipients: str = Field(..., max_length=200)
    template_summary: str = Field(..., max_length=400)


class PermissionDraft(BaseModel):
    role: str = Field(..., max_length=80)
    allowed_actions: list[PermissionAction] = Field(default_factory=list)


class AuditEventDraft(BaseModel):
    event: str = Field(..., max_length=120)
    data_recorded: str = Field(..., max_length=400)


class IntegrationDraft(BaseModel):
    interface_name: str = Field(..., max_length=120)
    purpose: str = Field(..., max_length=400)


class AcceptanceCriterionDraft(BaseModel):
    scenario_title: str = Field(..., max_length=200)
    given: str = Field(..., max_length=600)
    when: str = Field(..., max_length=600)
    then: str = Field(..., max_length=600)
    covers_requirement_ids: list[str] = Field(default_factory=list)


class FeatureSpecDraft(BaseModel):
    feature_id: str = Field(..., max_length=32)
    summary: str = Field(..., max_length=800)
    actors: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    trigger: str = Field(..., max_length=400)
    main_flow: list[FlowStepItem] = Field(default_factory=list)
    alternate_flows: list[AlternateFlowItem] = Field(default_factory=list)
    exception_flows: list[ExceptionFlowItem] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    business_rules: list[BusinessRuleDraft] = Field(default_factory=list)
    fields: list[FieldSpecDraft] = Field(default_factory=list)
    screens: list[ScreenDraft] = Field(default_factory=list)
    messages: list[MessageDraft] = Field(default_factory=list)
    notifications: list[NotificationDraft] = Field(default_factory=list)
    permissions: list[PermissionDraft] = Field(default_factory=list)
    audit_events: list[AuditEventDraft] = Field(default_factory=list)
    integrations: list[IntegrationDraft] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterionDraft] = Field(default_factory=list)
    linked_requirement_ids: list[str] = Field(default_factory=list)
    linked_story_titles: list[str] = Field(default_factory=list)


class FrsPlanningOutput(BaseModel):
    roles: list[RoleItem] = Field(default_factory=list)
    general_behaviours: list[str] = Field(default_factory=list)
    navigation: list[NavigationItem] = Field(default_factory=list)
    screen_inventory_seed: list[str] = Field(default_factory=list)
    state_models: list[EntityStateModelDraft] = Field(default_factory=list)
    notification_conventions: list[str] = Field(default_factory=list)


class FrsModuleBatchOutput(BaseModel):
    module: str = Field(..., max_length=120)
    specifications: list[FeatureSpecDraft] = Field(default_factory=list)


class FrsCoverageRepairOutput(BaseModel):
    specifications: list[FeatureSpecDraft] = Field(default_factory=list)
    state_patches: list[EntityStateModelDraft] = Field(default_factory=list)


class FrsPasses(BaseModel):
    planning: FrsPlanningOutput | None = None
    modules: dict[str, FrsModuleBatchOutput] = Field(default_factory=dict)
    coverage_repair: FrsCoverageRepairOutput | None = None


class StoredFeatureSpecification(BaseModel):
    id: str
    feature_id: str
    module: str
    title: str
    priority: str
    phase: str
    summary: str
    actors: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    trigger: str = ""
    main_flow: list[dict[str, str]] = Field(default_factory=list)
    alternate_flows: list[dict[str, Any]] = Field(default_factory=list)
    exception_flows: list[dict[str, Any]] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    business_rules: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[dict[str, Any]] = Field(default_factory=list)
    screens: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    permissions: list[dict[str, Any]] = Field(default_factory=list)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    integrations: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_criteria: list[dict[str, Any]] = Field(default_factory=list)
    linked_requirement_ids: list[str] = Field(default_factory=list)
    linked_story_ids: list[str] = Field(default_factory=list)
    flow_ids: dict[str, str] = Field(default_factory=dict)


class FrsHealthMeta(BaseModel):
    health_rows: list[dict[str, Any]] = Field(default_factory=list)
    srs_coverage_pct: float = 0.0
    uncovered_srs_ids: list[str] = Field(default_factory=list)
    spec_count: int = 0
    placeholder_count: int = 0
    approx_pages: float = 0.0


class FrsAssembled(BaseModel):
    document_reference: str
    revision_history: list[dict[str, str]] = Field(default_factory=list)
    global_conventions: list[dict[str, str]] = Field(default_factory=list)
    roles: list[dict[str, str]] = Field(default_factory=list)
    permission_matrix: list[dict[str, Any]] = Field(default_factory=list)
    permission_module_summary: list[dict[str, Any]] = Field(default_factory=list)
    catalogs: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    state_tables: list[dict[str, Any]] = Field(default_factory=list)
    traceability: dict[str, Any] = Field(default_factory=dict)
    open_issues: list[dict[str, str]] = Field(default_factory=list)
    placeholders: list[dict[str, str]] = Field(default_factory=list)
    glossary: list[dict[str, str]] = Field(default_factory=list)
    standards_references: list[str] = Field(default_factory=list)
    feature_specs_view: list[dict[str, Any]] = Field(default_factory=list)
    revision_parts: list[str] = Field(default_factory=list)
    traceability_rows: list[dict[str, Any]] = Field(default_factory=list)


class FrsStored(BaseModel):
    schema_version: int = 1
    passes: FrsPasses
    specifications: list[StoredFeatureSpecification] = Field(default_factory=list)
    assembled: FrsAssembled
    viewer: FrsHealthMeta = Field(default_factory=FrsHealthMeta)


class FrsPlanningPassAOutput(FrsPlanningOutput):
    """Alias for step registry output_schema."""
