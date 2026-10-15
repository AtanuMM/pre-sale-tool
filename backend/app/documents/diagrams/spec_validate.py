"""Validate diagram specs before rendering."""

from __future__ import annotations

from dataclasses import dataclass

from app.steps.schemas.srs import DiagramSpec


@dataclass(frozen=True)
class DiagramValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


def validate_layered_diagram(spec: DiagramSpec) -> DiagramValidationResult:
    errors: list[str] = []
    if spec.kind == "er":
        return validate_er_diagram(spec)
    if len(spec.nodes) > 25:
        errors.append("too_many_nodes")
    if len(spec.edges) > 40:
        errors.append("too_many_edges")
    node_ids = {n.id for n in spec.nodes}
    if len(node_ids) != len(spec.nodes):
        errors.append("duplicate_node_ids")
    lane_names = {lane.name for lane in spec.lanes}
    for node in spec.nodes:
        if node.lane and node.lane not in lane_names and spec.lanes:
            errors.append(f"unknown_lane:{node.lane}")
    connected: set[str] = set()
    for edge in spec.edges:
        if edge.from_id not in node_ids or edge.to_id not in node_ids:
            errors.append("invalid_edge_endpoint")
        connected.add(edge.from_id)
        connected.add(edge.to_id)
    if spec.nodes and len(connected) < len(spec.nodes):
        errors.append("isolated_nodes")
    return DiagramValidationResult(ok=not errors, errors=tuple(errors))


def validate_er_diagram(spec: DiagramSpec) -> DiagramValidationResult:
    errors: list[str] = []
    if len(spec.entities) > 12:
        errors.append("too_many_entities")
    names = {e.name for e in spec.entities}
    if len(names) != len(spec.entities):
        errors.append("duplicate_entities")
    for rel in spec.relationships:
        if rel.from_entity not in names or rel.to_entity not in names:
            errors.append("invalid_relationship_endpoint")
    return DiagramValidationResult(ok=not errors, errors=tuple(errors))
