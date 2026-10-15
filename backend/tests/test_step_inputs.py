from app.steps.input_fields import (
    InputFieldSpec,
    StepInputValidationError,
    user_inputs_audit_metadata,
    validate_step_inputs,
)

FIELDS = (
    InputFieldSpec(
        key="team_notes",
        label="Notes and client answers (optional)",
        help_text="help",
        kind="textarea",
        max_length=8000,
    ),
)


def test_unknown_key_rejected() -> None:
    try:
        validate_step_inputs(FIELDS, {"nope": "x"})
        raise AssertionError("expected error")
    except StepInputValidationError as exc:
        assert exc.errors[0]["loc"][-1] == "nope"


def test_unknown_key_on_step_without_fields() -> None:
    try:
        validate_step_inputs((), {"team_notes": "x"})
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_too_long_rejected() -> None:
    try:
        validate_step_inputs(FIELDS, {"team_notes": "a" * 8001})
        raise AssertionError("expected error")
    except StepInputValidationError as exc:
        assert "8000" in exc.errors[0]["msg"]


def test_whitespace_only_treated_as_empty() -> None:
    assert validate_step_inputs(FIELDS, {"team_notes": "   \n  "}) == {}
    assert validate_step_inputs(FIELDS, None) == {}
    assert validate_step_inputs(FIELDS, {}) == {}


def test_stripped_text_kept() -> None:
    assert validate_step_inputs(FIELDS, {"team_notes": "  hello  "}) == {
        "team_notes": "hello"
    }


def test_audit_metadata_has_no_text() -> None:
    values = {"team_notes": "secret client answer"}
    meta = user_inputs_audit_metadata(FIELDS, values)
    blob = str(meta)
    assert "secret" not in blob
    assert meta["team_notes"]["provided"] is True
    assert meta["team_notes"]["length"] == len("secret client answer")
    empty = user_inputs_audit_metadata(FIELDS, {})
    assert empty["team_notes"]["provided"] is False
    assert empty["team_notes"]["length"] == 0
