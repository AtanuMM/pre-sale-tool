from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.postprocess.feature_list import postprocess_feature_list
from app.steps.schemas.feature_list import FeatureItem, FeatureListOutput, ModuleItem

CTX = PostprocessContext(ref_counts={"G": 3, "A": 2}, max_features=150)


def _item(**overrides) -> FeatureItem:
    base = {
        "ref": 1,
        "module": "Auth",
        "title": "Sign in",
        "description": "Users sign in.",
        "platforms": ["web"],
        "priority": "must",
        "origin": "stated",
        "depends_on_refs": [],
        "linked_gap_refs": [],
        "linked_assumption_refs": [],
    }
    base.update(overrides)
    return FeatureItem.model_validate(base)


def _output(features: list[FeatureItem], modules: list[ModuleItem] | None = None) -> FeatureListOutput:
    return FeatureListOutput(
        summary="Overview",
        modules=modules or [ModuleItem(name="Auth", purpose="Identity")],
        features=features,
        coverage_notes="None",
    )


def test_duplicate_and_malformed_refs_renumbered_and_remapped() -> None:
    stored, notes = postprocess_feature_list(
        _output(
            [
                _item(ref=7, title="A", depends_on_refs=[7, 9]),
                _item(ref=7, title="B", depends_on_refs=[9]),
                _item(ref=9, title="C", depends_on_refs=[]),
            ]
        ),
        CTX,
    )
    assert notes["refs_renumbered"] == 3
    ids = [f.id for f in stored.features]
    assert ids == ["F-001", "F-002", "F-003"]
    # 7 was duplicated so depends_on 7 is dropped; 9 uniquely mapped to position 3
    assert stored.features[0].depends_on_ids == ["F-003"]
    assert stored.features[1].depends_on_ids == ["F-003"]


def test_unknown_self_and_cyclic_dependencies_dropped() -> None:
    stored, notes = postprocess_feature_list(
        _output(
            [
                _item(ref=1, title="A", depends_on_refs=[2]),
                _item(ref=2, title="B", depends_on_refs=[1, 2, 99]),
            ]
        ),
        CTX,
    )
    assert stored.features[0].depends_on_ids == ["F-002"]
    assert stored.features[1].depends_on_ids == []
    assert notes["deps_dropped_self"] == 1
    assert notes["deps_dropped_unknown"] == 1
    assert notes["deps_dropped_cycle"] == 1


def test_invalid_gap_and_assumption_refs_dropped() -> None:
    stored, notes = postprocess_feature_list(
        _output(
            [
                _item(
                    linked_gap_refs=["G-1", "G-9", "gap-1", "G-1"],
                    linked_assumption_refs=["A-2", "A-0", "B-1"],
                )
            ]
        ),
        CTX,
    )
    assert stored.features[0].linked_gap_refs == ["G-1"]
    assert stored.features[0].linked_assumption_refs == ["A-2"]
    assert notes["gap_refs_dropped"] == 3
    assert notes["assumption_refs_dropped"] == 2


def test_trim_appends_coverage_note_when_missing() -> None:
    features = [_item(ref=i, title=f"F{i}") for i in range(1, 6)]
    stored, notes = postprocess_feature_list(
        _output(features), PostprocessContext(ref_counts={"G": 0, "A": 0}, max_features=3)
    )
    assert notes["features_trimmed"] == 2
    assert len(stored.features) == 3
    assert "trimmed" in stored.coverage_notes.lower()


def test_trim_does_not_duplicate_existing_note() -> None:
    features = [_item(ref=i, title=f"F{i}") for i in range(1, 5)]
    stored, _notes = postprocess_feature_list(
        FeatureListOutput(
            summary="s",
            modules=[ModuleItem(name="Auth", purpose="p")],
            features=features,
            coverage_notes="Already truncated due to a limit.",
        ),
        PostprocessContext(ref_counts={}, max_features=2),
    )
    assert stored.coverage_notes.count("trimmed to the configured") == 0


def test_zero_features_fails() -> None:
    try:
        postprocess_feature_list(
            FeatureListOutput(
                summary="s",
                modules=[ModuleItem(name="Auth", purpose="p")],
                features=[],
                coverage_notes="",
            ),
            CTX,
        )
        raise AssertionError("expected PostprocessError")
    except PostprocessError:
        pass


def test_ids_sequential_and_stats() -> None:
    stored, _notes = postprocess_feature_list(
        _output(
            [
                _item(ref=1, module="Auth", priority="must", origin="stated"),
                _item(ref=2, module="Billing", title="Invoices", priority="could", origin="suggested"),
            ],
            modules=[ModuleItem(name="Auth", purpose="Identity")],
        ),
        CTX,
    )
    assert [f.id for f in stored.features] == ["F-001", "F-002"]
    assert stored.stats.by_priority["must"] == 1
    assert stored.stats.by_priority["could"] == 1
    assert stored.stats.by_origin["stated"] == 1
    assert stored.stats.by_origin["suggested"] == 1
    assert stored.stats.by_module["Auth"] == 1
    assert stored.stats.by_module["Billing"] == 1
    assert any(m.name == "Billing" for m in stored.modules)
    assert stored.source_requirements_total == 0
    assert stored.warnings == []
    assert stored.features[0].source_priority == "not specified"
    assert stored.features[0].source_requirement_ids == []
    assert stored.features[0].primary_risk_domain == "none"


def test_v1_shaped_feature_output_still_validates() -> None:
    item = FeatureItem.model_validate(
        {
            "ref": 1,
            "module": "Auth",
            "title": "Sign in",
            "description": "Users sign in.",
            "platforms": ["web"],
            "priority": "must",
            "origin": "stated",
            "depends_on_refs": [],
            "linked_gap_refs": [],
            "linked_assumption_refs": [],
        }
    )
    assert item.source_requirement_ids == []
    assert item.source_priority == "not specified"


def test_quality_warnings_ratio_implied_and_could() -> None:
    stored, notes = postprocess_feature_list(
        FeatureListOutput(
            summary="s",
            modules=[ModuleItem(name="Auth", purpose="p")],
            features=[
                _item(
                    ref=1,
                    origin="stated",
                    priority="must",
                    source_priority="Could",
                    source_requirement_ids=["REQ-01", " REQ-01 ", ""],
                ),
                _item(ref=2, origin="stated", priority="must", title="Two"),
            ],
            coverage_notes="",
            source_requirements_total=10,
        ),
        CTX,
    )
    assert stored.source_requirements_total == 10
    assert stored.features[0].source_requirement_ids == ["REQ-01"]
    codes = {w.code: w for w in stored.warnings}
    assert "features_below_source_ratio" in codes
    assert codes["features_below_source_ratio"].count > 0
    assert notes["features_below_source_ratio"] == codes["features_below_source_ratio"].count
    assert notes["zero_implied_and_suggested"] == 1
    assert notes["could_missing_while_source_has_could"] == 1
    assert any(w.code == "could_missing_while_source_has_could" for w in stored.warnings)


def test_could_preserved_skips_could_warning() -> None:
    stored, notes = postprocess_feature_list(
        _output(
            [
                _item(ref=1, origin="stated", priority="must"),
                _item(
                    ref=2,
                    title="Optional export",
                    origin="stated",
                    priority="could",
                    source_priority="Could",
                ),
                _item(ref=3, title="Audit", origin="implied", priority="should"),
            ]
        ),
        CTX,
    )
    assert stored.stats.by_priority["could"] == 1
    assert notes["could_missing_while_source_has_could"] == 0
    assert notes["zero_implied_and_suggested"] == 0
    assert stored.warnings == []
