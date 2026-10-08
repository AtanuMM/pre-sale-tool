from app.steps.definitions import ordered_steps
from app.steps.layout_config import validate_layout_against_schema


def test_implemented_steps_layout_matches_schema() -> None:
    for step in ordered_steps():
        if not step.implemented or step.output_schema is None:
            continue
        validate_layout_against_schema(step.layout, step.output_schema)


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
