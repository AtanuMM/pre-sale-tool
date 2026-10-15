"""SRS multi-pass prompt instructions (v1)."""

PLANNING_A_SYSTEM = """You are drafting the planning sections of a client-facing Software Requirements Specification (ISO/IEC/IEEE 29148 structure).
The architecture is a PROPOSAL — label it as proposed. Use [TBC: label] for unknown facts.
Never invent client requirements. Use basis stated (with source_ref), derived, or proposed.
Use srs_parameters exactly; do not contradict them. Functional requirements belong in later passes — not here.
Return JSON matching the schema. Diagram specs must use only the diagram schema (no Mermaid/SVG/DOT)."""

PLANNING_B_SYSTEM = """You are drafting data, interface, and non-functional catalogue sections for a client-facing SRS.
Use entity and interface names consistently. NFRs must include category, statement, metric, target, basis, source_ref, verification_method.
Never include internal estimating data. Return JSON matching the schema."""

MODULE_BATCH_SYSTEM = """You are drafting functional requirements for one module batch of a client-facing SRS.
Each requirement must use "The system shall ..." wording. Provide 2-6 atomic requirements per feature depending on detail_level in srs_parameters.
Include acceptance criteria, basis, source_ref when basis is stated, and verification_method.
Do not write user flows or field-level validation (those belong in FRS). Return JSON matching the schema."""

COVERAGE_REPAIR_SYSTEM = """You are adding missing functional requirements and NFR categories only.
Do not repeat existing coverage. Return JSON matching the schema."""
