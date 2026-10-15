"""Optional per-step user inputs collected before generation (plan 8.4 item 6).

Kinds: ``textarea``, ``text``, ``number``, ``multi_select``, ``table``.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Any, Literal

InputFieldKind = Literal[
    "textarea", "text", "number", "select", "multi_select", "table", "date"
]
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ColumnKind = Literal["text", "number", "select"]

_ROLE_RE = re.compile(r"^[A-Za-z0-9 &/()\-]+$")


@dataclass(frozen=True)
class TableColumnSpec:
    key: str
    label: str
    kind: ColumnKind
    required: bool = True
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    default: Any = None
    options: tuple[str, ...] = ()
    max_length: int | None = None
    min_length: int | None = None
    pattern: str | None = None
    visible_when: tuple[str, str] | None = None
    enabled_when: tuple[str, str] | None = None


@dataclass(frozen=True)
class InputFieldSpec:
    key: str
    label: str
    help_text: str
    kind: InputFieldKind = "textarea"
    max_length: int = 8000
    required: bool = False
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    default: Any = None
    options: tuple[str, ...] = ()
    min_rows: int | None = None
    max_rows: int | None = None
    columns: tuple[TableColumnSpec, ...] = ()
    unique_column: str | None = None
    required_option: str | None = None
    require_estimated_row: bool = False
    pattern: str | None = None


class StepInputValidationError(ValueError):
    """Raised with a list of {loc, msg} items suitable for a 422 response."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("invalid step inputs")
        self.errors = errors


def _column_to_api(col: TableColumnSpec) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": col.key,
        "label": col.label,
        "kind": col.kind,
        "required": col.required,
    }
    if col.min_value is not None:
        item["min_value"] = col.min_value
    if col.max_value is not None:
        item["max_value"] = col.max_value
    if col.step is not None:
        item["step"] = col.step
    if col.default is not None:
        item["default"] = col.default
    if col.options:
        item["options"] = list(col.options)
    if col.max_length is not None:
        item["max_length"] = col.max_length
    if col.min_length is not None:
        item["min_length"] = col.min_length
    if col.pattern is not None:
        item["pattern"] = col.pattern
    if col.visible_when is not None:
        item["visible_when"] = {"column": col.visible_when[0], "value": col.visible_when[1]}
    if col.enabled_when is not None:
        item["enabled_when"] = {"column": col.enabled_when[0], "value": col.enabled_when[1]}
    return item


def input_fields_to_api(fields: tuple[InputFieldSpec, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in fields:
        item: dict[str, Any] = {
            "key": f.key,
            "label": f.label,
            "help_text": f.help_text,
            "kind": f.kind,
            "max_length": f.max_length,
            "required": f.required,
        }
        if f.min_value is not None:
            item["min_value"] = f.min_value
        if f.max_value is not None:
            item["max_value"] = f.max_value
        if f.step is not None:
            item["step"] = f.step
        if f.default is not None:
            item["default"] = copy.deepcopy(f.default)
        if f.options:
            item["options"] = list(f.options)
        if f.min_rows is not None:
            item["min_rows"] = f.min_rows
        if f.max_rows is not None:
            item["max_rows"] = f.max_rows
        if f.columns:
            item["columns"] = [_column_to_api(c) for c in f.columns]
        if f.unique_column is not None:
            item["unique_column"] = f.unique_column
        if f.required_option is not None:
            item["required_option"] = f.required_option
        if f.require_estimated_row:
            item["require_estimated_row"] = True
        if f.pattern is not None:
            item["pattern"] = f.pattern
        out.append(item)
    return out


def _err(loc: list[Any], msg: str) -> dict[str, Any]:
    return {"loc": loc, "msg": msg}


def _is_multiple_of(value: float, step: float) -> bool:
    if step <= 0:
        return True
    quotient = value / step
    return math.isclose(quotient, round(quotient), rel_tol=0, abs_tol=1e-9)


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
        if not math.isfinite(parsed):
            return None
        return parsed
    return None


def _validate_string_field(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    if value is None:
        if spec.required:
            return None, [_err(loc, "This field is required")]
        return None, []
    if not isinstance(value, str):
        return None, [_err(loc, "Must be a string")]
    stripped = value.strip()
    if not stripped:
        if spec.required:
            return None, [_err(loc, "This field is required")]
        return None, []
    if len(stripped) > spec.max_length:
        return None, [_err(loc, f"Must be at most {spec.max_length} characters")]
    if spec.pattern and re.fullmatch(spec.pattern, stripped) is None:
        return None, [_err(loc, "Contains invalid characters")]
    return stripped, []


def _validate_number_field(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[float | None, list[dict[str, Any]]]:
    if value is None or value == "":
        if spec.required and spec.default is None:
            return None, [_err(loc, "This field is required")]
        if spec.default is not None:
            value = spec.default
        else:
            return None, []
    number = _as_number(value)
    if number is None:
        return None, [_err(loc, "Must be a number")]
    if spec.min_value is not None and number < spec.min_value:
        return None, [_err(loc, f"Must be at least {spec.min_value}")]
    if spec.max_value is not None and number > spec.max_value:
        return None, [_err(loc, f"Must be at most {spec.max_value}")]
    if spec.step is not None and not _is_multiple_of(number, spec.step):
        return None, [_err(loc, f"Must be a multiple of {spec.step}")]
    return number, []


def _validate_date_field(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    if value is None or value == "":
        if spec.required:
            return None, [_err(loc, "This field is required")]
        return None, []
    if not isinstance(value, str):
        return None, [_err(loc, "Must be an ISO date (YYYY-MM-DD)")]
    stripped = value.strip()
    if not _DATE_RE.fullmatch(stripped):
        return None, [_err(loc, "Must be an ISO date (YYYY-MM-DD)")]
    return stripped, []


def _validate_select_field(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[str | None, list[dict[str, Any]]]:
    if value is None or value == "":
        if spec.default is not None:
            value = spec.default
        elif spec.required:
            return None, [_err(loc, "This field is required")]
        else:
            return None, []
    if not isinstance(value, str) or value not in spec.options:
        return None, [_err(loc, f"Must be one of: {', '.join(spec.options)}")]
    return value, []


def _validate_multi_select(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[list[str] | None, list[dict[str, Any]]]:
    if value is None:
        if spec.default is not None:
            value = copy.deepcopy(spec.default)
        elif spec.required:
            return None, [_err(loc, "This field is required")]
        else:
            return None, []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, [_err(loc, "Must be a list of strings")]
    allowed = set(spec.options)
    selected: list[str] = []
    errors: list[dict[str, Any]] = []
    for item in value:
        if item not in allowed:
            errors.append(_err([*loc, item], "Unknown option"))
            continue
        if item not in selected:
            selected.append(item)
    if spec.required_option and spec.required_option not in selected:
        selected.insert(0, spec.required_option)
    if spec.required and not selected:
        errors.append(_err(loc, "Select at least one option"))
    if errors:
        return None, errors
    return selected, []


def _column_visible(col: TableColumnSpec, row: dict[str, Any]) -> bool:
    if col.visible_when is None:
        return True
    key, expected = col.visible_when
    return str(row.get(key) or "") == expected


def _validate_cell(
    col: TableColumnSpec, value: Any, *, loc: list[Any], row: dict[str, Any]
) -> tuple[Any, list[dict[str, Any]]]:
    visible = _column_visible(col, row)
    if not visible:
        return None, []
    if col.kind == "select":
        if value is None or value == "":
            if col.default is not None:
                value = col.default
            elif col.required:
                return None, [_err(loc, f"{col.label} is required")]
            else:
                return None, []
        if not isinstance(value, str) or value not in col.options:
            return None, [_err(loc, f"{col.label} must be one of: {', '.join(col.options)}")]
        return value, []
    if col.kind == "number":
        if value is None or value == "":
            if not col.required:
                return None, []
            if col.default is not None:
                value = col.default
            else:
                return None, [_err(loc, f"{col.label} is required")]
        number = _as_number(value)
        if number is None:
            return None, [_err(loc, f"{col.label} must be a number")]
        if col.min_value is not None and number < col.min_value:
            return None, [_err(loc, f"{col.label} must be at least {col.min_value}")]
        if col.max_value is not None and number > col.max_value:
            return None, [_err(loc, f"{col.label} must be at most {col.max_value}")]
        if col.step is not None and not _is_multiple_of(number, col.step):
            return None, [_err(loc, f"{col.label} must be a multiple of {col.step}")]
        return number, []
    # text
    if value is None:
        if not col.required:
            return None, []
        return None, [_err(loc, f"{col.label} is required")]
    if not isinstance(value, str):
        return None, [_err(loc, f"{col.label} must be a string")]
    stripped = value.strip()
    if not stripped:
        if not col.required:
            return None, []
        return None, [_err(loc, f"{col.label} is required")]
    min_len = col.min_length or 0
    max_len = col.max_length or 200
    if len(stripped) < min_len:
        return None, [_err(loc, f"{col.label} must be at least {min_len} characters")]
    if len(stripped) > max_len:
        return None, [_err(loc, f"{col.label} must be at most {max_len} characters")]
    if col.pattern:
        compiled = _ROLE_RE if col.pattern == "role_name" else re.compile(col.pattern)
        if compiled.fullmatch(stripped) is None:
            return None, [_err(loc, f"{col.label} contains invalid characters")]
    return stripped, []


def _validate_table(
    spec: InputFieldSpec, value: Any, *, loc: list[Any]
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    if value is None:
        if spec.required:
            return None, [_err(loc, "This field is required")]
        return None, []
    if not isinstance(value, list):
        return None, [_err(loc, "Must be a list of rows")]
    min_rows = spec.min_rows or 0
    max_rows = spec.max_rows or 100
    if len(value) < min_rows:
        return None, [_err(loc, f"Enter at least {min_rows} row(s)")]
    if len(value) > max_rows:
        return None, [_err(loc, f"At most {max_rows} rows are allowed")]
    columns = {c.key: c for c in spec.columns}
    errors: list[dict[str, Any]] = []
    cleaned_rows: list[dict[str, Any]] = []
    seen_unique: dict[str, int] = {}
    estimated = 0
    for index, raw_row in enumerate(value):
        row_loc = [*loc, index]
        if not isinstance(raw_row, dict):
            errors.append(_err(row_loc, "Each row must be an object"))
            continue
        unknown = [k for k in raw_row if k not in columns]
        for key in unknown:
            errors.append(_err([*row_loc, key], "Unknown column"))
        cleaned: dict[str, Any] = {}
        for col in spec.columns:
            cell, cell_errors = _validate_cell(
                col, raw_row.get(col.key), loc=[*row_loc, col.key], row=raw_row
            )
            errors.extend(cell_errors)
            if cell is not None:
                cleaned[col.key] = cell
        if spec.unique_column:
            uniq_val = cleaned.get(spec.unique_column)
            if isinstance(uniq_val, str):
                key = uniq_val.casefold()
                if key in seen_unique:
                    errors.append(
                        _err(
                            [*row_loc, spec.unique_column],
                            f"{spec.unique_column} must be unique",
                        )
                    )
                else:
                    seen_unique[key] = index
        if (
            cleaned.get("discipline")
            and cleaned.get("discipline") != "development"
            and "ai_gain_pct" in columns
        ):
            cleaned["ai_gain_pct"] = 0.0
        if cleaned.get("mode") == "estimated":
            estimated += 1
        cleaned_rows.append(cleaned)
    if spec.require_estimated_row and estimated == 0 and not errors:
        errors.append(_err(loc, "At least one estimated role is required"))
    if errors:
        return None, errors
    return cleaned_rows, []


def validate_step_inputs(
    fields: tuple[InputFieldSpec, ...], raw: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate and normalise user inputs against the step's field specs.

    Returns only set values keyed by field key. Unknown keys are rejected.
    """
    incoming = raw or {}
    by_key = {f.key: f for f in fields}
    errors: list[dict[str, Any]] = []
    unknown = [k for k in incoming if k not in by_key]
    for key in unknown:
        errors.append(_err(["body", "inputs", key], "Unknown input field"))

    cleaned: dict[str, Any] = {}
    for spec in fields:
        loc = ["body", "inputs", spec.key]
        present = spec.key in incoming
        value = incoming.get(spec.key) if present else None
        if not present and spec.default is not None and spec.kind != "textarea":
            value = copy.deepcopy(spec.default)
            present = True
        if spec.kind in ("textarea", "text"):
            text, field_errors = _validate_string_field(spec, value, loc=loc)
            errors.extend(field_errors)
            if text is not None:
                cleaned[spec.key] = text
            elif spec.required and not field_errors:
                errors.append(_err(loc, "This field is required"))
        elif spec.kind == "select":
            selected, field_errors = _validate_select_field(spec, value, loc=loc)
            errors.extend(field_errors)
            if selected is not None:
                cleaned[spec.key] = selected
        elif spec.kind == "number":
            number, field_errors = _validate_number_field(spec, value, loc=loc)
            errors.extend(field_errors)
            if number is not None:
                cleaned[spec.key] = number
        elif spec.kind == "multi_select":
            selected, field_errors = _validate_multi_select(spec, value, loc=loc)
            errors.extend(field_errors)
            if selected is not None:
                cleaned[spec.key] = selected
        elif spec.kind == "table":
            rows, field_errors = _validate_table(spec, value, loc=loc)
            errors.extend(field_errors)
            if rows is not None:
                cleaned[spec.key] = rows
        elif spec.kind == "date":
            date_val, field_errors = _validate_date_field(spec, value, loc=loc)
            errors.extend(field_errors)
            if date_val is not None:
                cleaned[spec.key] = date_val
        else:  # pragma: no cover
            errors.append(_err(loc, "Unsupported field kind"))
        if (
            spec.required
            and spec.key not in cleaned
            and spec.kind == "table"
            and not present
            and not any(e["loc"] == loc for e in errors)
        ):
            errors.append(_err(loc, "This field is required"))

    _validate_payment_schedule_totals(by_key, cleaned, errors)

    if errors:
        raise StepInputValidationError(errors)
    return cleaned


def _validate_payment_schedule_totals(
    by_key: dict[str, InputFieldSpec],
    cleaned: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    if "payment_schedule" not in by_key or "pricing_model" not in by_key:
        return
    model = cleaned.get("pricing_model", "not_specified")
    rows = cleaned.get("payment_schedule")
    if not isinstance(rows, list) or not rows:
        return
    if model not in ("fixed_price", "milestone_based"):
        return
    total = 0.0
    for row in rows:
        if isinstance(row, dict):
            pct = row.get("percent")
            if isinstance(pct, (int, float)):
                total += float(pct)
    if not math.isclose(total, 100.0, abs_tol=0.01):
        errors.append(
            _err(
                ["body", "inputs", "payment_schedule"],
                "Payment schedule percentages must total 100",
            )
        )


def user_inputs_audit_metadata(
    fields: tuple[InputFieldSpec, ...], values: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Audit-safe summary: counts only; never text, rates, gains, or contingency."""
    out: dict[str, dict[str, Any]] = {}
    for spec in fields:
        val = values.get(spec.key)
        if spec.kind in ("textarea", "text"):
            text = val if isinstance(val, str) else ""
            out[spec.key] = {"provided": bool(text), "length": len(text)}
        elif spec.kind == "select" or spec.kind == "date":
            out[spec.key] = {"provided": isinstance(val, str) and bool(val)}
        elif spec.kind == "number":
            out[spec.key] = {"provided": val is not None}
        elif spec.kind == "multi_select":
            selected = val if isinstance(val, list) else []
            out[spec.key] = {"selected": len(selected)}
        elif spec.kind == "table":
            rows = val if isinstance(val, list) else []
            meta: dict[str, Any] = {"rows": len(rows)}
            if spec.key == "payment_schedule":
                meta["percent_total"] = sum(
                    float(row.get("percent", 0))
                    for row in rows
                    if isinstance(row, dict) and isinstance(row.get("percent"), (int, float))
                )
            elif spec.key == "team":
                headcount = 0.0
                for row in rows:
                    if isinstance(row, dict):
                        hc = row.get("headcount")
                        if isinstance(hc, (int, float)):
                            headcount += float(hc)
                meta["total_headcount"] = headcount
            out[spec.key] = meta
    return out
