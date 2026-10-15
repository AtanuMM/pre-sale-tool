from app.steps.definitions import ordered_steps
from app.steps.layout_config import validate_layout_against_schema


def test_implemented_steps_layout_matches_schema() -> None:
    for step in ordered_steps():
        if not step.implemented:
            continue
        schema = step.persisted_schema or step.output_schema
        assert schema is not None
        validate_layout_against_schema(step.layout, schema)


def test_dummy_step_layout_only_needs_config() -> None:
    from pydantic import BaseModel, Field

    from app.steps.layout_config import SectionKind, SectionLayoutSpec

    class DummyOut(BaseModel):
        note: str = Field(...)
        items: list[str] = Field(...)

    good = (
        SectionLayoutSpec("note", "Note", SectionKind.TEXT),
        SectionLayoutSpec("items", "Items", SectionKind.LIST),
    )
    validate_layout_against_schema(good, DummyOut)

    bad = (SectionLayoutSpec("missing_key", "Bad", SectionKind.TEXT),)
    try:
        validate_layout_against_schema(bad, DummyOut)
        raise AssertionError("expected validation error")
    except RuntimeError:
        pass


def test_stats_and_group_layout_rules() -> None:
    from pydantic import BaseModel, Field

    from app.steps.layout_config import (
        GroupSource,
        LayoutColumn,
        SectionKind,
        SectionLayoutSpec,
        validate_layout_against_schema,
    )

    class Item(BaseModel):
        name: str
        purpose: str

    class Rec(BaseModel):
        module: str
        title: str

    class Out(BaseModel):
        modules: list[Item] = Field(...)
        features: list[Rec] = Field(...)
        stats: dict[str, int] = Field(...)

    good = (
        SectionLayoutSpec(
            "stats",
            "Overview",
            SectionKind.STATS,
            stats_groups=(LayoutColumn("by_priority", "Priority"),),
        ),
        SectionLayoutSpec(
            "features",
            "Features",
            SectionKind.RECORDS,
            record_fields=(LayoutColumn("title", "Title"),),
            group_by="module",
            group_source=GroupSource("modules", "name", "purpose"),
        ),
    )
    validate_layout_against_schema(good, Out)

    missing_stats = (SectionLayoutSpec("stats", "Overview", SectionKind.STATS),)
    try:
        validate_layout_against_schema(missing_stats, Out)
        raise AssertionError("expected validation error")
    except RuntimeError:
        pass
