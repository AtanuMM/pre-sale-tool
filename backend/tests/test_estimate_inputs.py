from app.steps.estimate_inputs import ESTIMATE_INPUT_FIELDS
from app.steps.input_fields import (
    StepInputValidationError,
    user_inputs_audit_metadata,
    validate_step_inputs,
)


def _team_row(**overrides: object) -> dict:
    row = {
        "role": "Developer",
        "discipline": "development",
        "mode": "estimated",
        "headcount": 2,
        "hours_per_week": 40,
        "utilisation_pct": 100,
        "ai_gain_pct": 20,
    }
    row.update(overrides)
    return row


def test_valid_team_accepted() -> None:
    cleaned = validate_step_inputs(
        ESTIMATE_INPUT_FIELDS,
        {"team": [_team_row()], "phases": ["mvp", "phase_1"]},
    )
    assert cleaned["team"][0]["role"] == "Developer"
    assert "mvp" in cleaned["phases"]
    assert cleaned["domain_experience"] == "some_experience"
    assert "contingency_pct" not in cleaned


def test_missing_team_422() -> None:
    try:
        validate_step_inputs(ESTIMATE_INPUT_FIELDS, {})
        raise AssertionError("expected error")
    except StepInputValidationError as exc:
        assert any("team" in e["loc"] for e in exc.errors)


def test_unknown_key_rejected() -> None:
    try:
        validate_step_inputs(ESTIMATE_INPUT_FIELDS, {"team": [_team_row()], "nope": 1})
        raise AssertionError("expected error")
    except StepInputValidationError as exc:
        assert exc.errors[0]["loc"][-1] == "nope"


def test_duplicate_role_rejected() -> None:
    try:
        validate_step_inputs(
            ESTIMATE_INPUT_FIELDS,
            {"team": [_team_row(), _team_row(role="developer")]},
        )
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_role_pattern_rejected() -> None:
    try:
        validate_step_inputs(
            ESTIMATE_INPUT_FIELDS,
            {"team": [_team_row(role="Dev; DROP")]},
        )
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_need_estimated_role() -> None:
    try:
        validate_step_inputs(
            ESTIMATE_INPUT_FIELDS,
            {
                "team": [
                    _team_row(mode="duration_based", ai_gain_pct=0),
                ]
            },
        )
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_overhead_required_for_percent_mode() -> None:
    try:
        validate_step_inputs(
            ESTIMATE_INPUT_FIELDS,
            {
                "team": [
                    _team_row(),
                    _team_row(role="DevOps", mode="percent_of_delivery", ai_gain_pct=0),
                ]
            },
        )
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_mvp_always_included() -> None:
    cleaned = validate_step_inputs(
        ESTIMATE_INPUT_FIELDS,
        {"team": [_team_row()], "phases": ["phase_1"]},
    )
    assert cleaned["phases"][0] == "mvp"


def test_non_dev_ai_gain_forced_zero() -> None:
    cleaned = validate_step_inputs(
        ESTIMATE_INPUT_FIELDS,
        {
            "team": [
                _team_row(),
                _team_row(role="QA Engineer", discipline="qa", ai_gain_pct=40),
            ]
        },
    )
    qa = next(row for row in cleaned["team"] if row["role"] == "QA Engineer")
    assert qa["ai_gain_pct"] == 0


def test_headcount_step() -> None:
    try:
        validate_step_inputs(
            ESTIMATE_INPUT_FIELDS,
            {"team": [_team_row(headcount=1.25)]},
        )
        raise AssertionError("expected error")
    except StepInputValidationError:
        pass


def test_audit_omits_notes_rates_gains_contingency() -> None:
    values = validate_step_inputs(
        ESTIMATE_INPUT_FIELDS,
        {
            "team": [_team_row(hourly_rate=80, ai_gain_pct=30)],
            "notes": "secret client answer about SSO",
            "currency": "INR",
        },
    )
    meta = user_inputs_audit_metadata(ESTIMATE_INPUT_FIELDS, values)
    blob = str(meta)
    assert "secret" not in blob
    assert "SSO" not in blob
    assert "hourly_rate" not in blob
    assert "ai_gain" not in blob
    assert meta["notes"]["provided"] is True
    assert meta["notes"]["length"] == len("secret client answer about SSO")
    assert meta["team"] == {"rows": 1, "total_headcount": 2.0}
    assert meta["phases"]["selected"] >= 1
    assert "contingency_pct" not in meta
