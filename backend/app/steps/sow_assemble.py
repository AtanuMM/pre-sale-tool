"""Build code-owned SOW assembled block from upstream outputs and user inputs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.steps.schemas.sow import (
    COMMITTED_PHASES,
    CommercialsBlock,
    PlaceholderItem,
    ScopeBundleItem,
    SowAssembled,
    TimelineRow,
)
from app.steps.sow_projection import (
    bundle_key_commit,
    bundle_key_optional,
    bundle_key_package,
)
from app.steps.sow_standard_terms import build_standard_terms

TBC = "[TBC: {label}]"


def _tbc(label: str) -> str:
    return TBC.format(label=label)


def _parse_date(raw: Any) -> date | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _pricing_label(model: str) -> str:
    return {
        "fixed_price": "Fixed price",
        "time_and_materials": "Time and materials",
        "milestone_based": "Milestone-based",
        "not_specified": "Not specified",
    }.get(model, model.replace("_", " ").title())


def _build_bundles(
    estimate: dict[str, Any],
) -> tuple[list[ScopeBundleItem], list[str]]:
    bundles: list[ScopeBundleItem] = []
    keys: list[str] = []
    by_commit: dict[tuple[str, str], list[tuple[str, str]]] = {}
    by_optional: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for feat in estimate.get("feature_estimates") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("feature_id") or "")
        title = str(feat.get("title") or fid)
        phase = str(feat.get("phase") or "mvp")
        component = str(feat.get("component") or "Other")
        priority = str(feat.get("priority") or "must")
        bucket = by_optional if priority == "could" else by_commit
        if phase == "future_scope" or priority == "wont":
            continue
        bucket.setdefault((phase, component), []).append((fid, title))
    for (phase, component), items in sorted(by_commit.items()):
        key = bundle_key_commit(phase, component)
        keys.append(key)
        bundles.append(
            ScopeBundleItem(
                bundle_key=key,
                kind="committed",
                phase=phase,
                component=component,
                title=f"{component} ({phase.replace('_', ' ')})",
                feature_ids=[i[0] for i in items],
                feature_titles=[i[1] for i in items],
            )
        )
    for (phase, component), items in sorted(by_optional.items()):
        key = bundle_key_optional(phase, component)
        keys.append(key)
        bundles.append(
            ScopeBundleItem(
                bundle_key=key,
                kind="optional",
                phase=phase,
                component=component,
                title=f"Optional: {component} ({phase.replace('_', ' ')})",
                feature_ids=[i[0] for i in items],
                feature_titles=[i[1] for i in items],
            )
        )
    for pkg in estimate.get("work_packages") or []:
        if not isinstance(pkg, dict):
            continue
        pid = str(pkg.get("id") or "")
        if not pid:
            continue
        key = bundle_key_package(pid)
        keys.append(key)
        bundles.append(
            ScopeBundleItem(
                bundle_key=key,
                kind="work_package",
                phase=str(pkg.get("phase") or "mvp"),
                component=str(pkg.get("component") or "Other"),
                title=str(pkg.get("title") or pid),
                feature_ids=[],
                feature_titles=[],
            )
        )
    return bundles, keys


def _timeline(
    estimate: dict[str, Any],
    kickoff: date | None,
) -> tuple[list[TimelineRow], float, float]:
    computed = estimate.get("computed") if isinstance(estimate.get("computed"), dict) else {}
    phase_rows = computed.get("phase_rows") if isinstance(computed.get("phase_rows"), list) else []
    rows: list[TimelineRow] = []
    start = 0.0
    total = 0.0
    settings = get_settings()
    for phase_key in COMMITTED_PHASES:
        if phase_key == "future_scope":
            continue
        match = next(
            (r for r in phase_rows if isinstance(r, dict) and r.get("phase") == phase_key),
            None,
        )
        weeks = float(match.get("weeks_planned") or 0) if match else 0.0
        if weeks <= 0:
            continue
        end = start + weeks
        indicative_start = None
        indicative_end = None
        if kickoff is not None:
            d0 = kickoff + timedelta(weeks=start)
            d1 = kickoff + timedelta(weeks=end)
            indicative_start = d0.isoformat()
            indicative_end = d1.isoformat()
        rows.append(
            TimelineRow(
                phase=phase_key,
                planned_weeks=round(weeks, 2),
                start_week=round(start, 2),
                end_week=round(end, 2),
                indicative_start=indicative_start,
                indicative_end=indicative_end,
            )
        )
        start = end
        total += weeks
    months = round(total / settings.ESTIMATE_WEEKS_PER_MONTH, 1) if total else 0.0
    return rows, round(total, 2), months


def _commercials(user_inputs: dict[str, Any]) -> CommercialsBlock:
    model = str(user_inputs.get("pricing_model") or "not_specified")
    fee = user_inputs.get("total_fee")
    fee_val = float(fee) if isinstance(fee, (int, float)) else None
    currency = str(user_inputs.get("currency") or "").strip() or None
    if fee_val is None:
        fee_display = _tbc("total contract fee")
    elif currency:
        fee_display = f"{currency} {fee_val:,.2f}"
    else:
        fee_display = f"{fee_val:,.2f}"
    payment_rows: list[dict[str, Any]] = []
    schedule = user_inputs.get("payment_schedule")
    if isinstance(schedule, list):
        for row in schedule:
            if not isinstance(row, dict):
                continue
            pct = float(row.get("percent") or 0)
            amount = round(fee_val * pct / 100.0, 2) if fee_val is not None else None
            payment_rows.append(
                {
                    "label": row.get("label") or "",
                    "percent": pct,
                    "trigger": row.get("trigger") or "",
                    "trigger_detail": row.get("trigger_detail") or "",
                    "amount": amount,
                    "amount_display": (
                        f"{currency} {amount:,.2f}"
                        if amount is not None and currency
                        else (f"{amount:,.2f}" if amount is not None else _tbc("payment amount"))
                    ),
                }
            )
    elif model in ("fixed_price", "milestone_based"):
        fee_display = fee_display  # keep
    return CommercialsBlock(
        pricing_model=model,
        pricing_model_label=_pricing_label(model),
        total_fee=fee_val,
        currency=currency,
        fee_display=fee_display,
        payment_rows=payment_rows,
    )


def _delivery_team(
    estimate_user_inputs: dict[str, Any], user_inputs: dict[str, Any]
) -> list[dict[str, Any]]:
    show_hc = user_inputs.get("team_display") == "roles_and_headcount"
    team = estimate_user_inputs.get("team")
    if not isinstance(team, list):
        team = []
    rows: list[dict[str, Any]] = []
    for row in team:
        if not isinstance(row, dict) or row.get("mode") != "estimated":
            continue
        role = str(row.get("role") or "").strip()
        if not role:
            continue
        item: dict[str, Any] = {"role": role, "discipline": str(row.get("discipline") or "other")}
        if show_hc:
            item["headcount"] = row.get("headcount")
        rows.append(item)
    return rows


def _effort_table(estimate: dict[str, Any], show: bool) -> list[dict[str, Any]]:
    if not show:
        return []
    computed = estimate.get("computed") if isinstance(estimate.get("computed"), dict) else {}
    matrix = computed.get("matrix_rows") if isinstance(computed.get("matrix_rows"), list) else []
    components = computed.get("matrix_components")
    if not isinstance(components, list):
        components = []
    out: list[dict[str, Any]] = []
    for row in matrix:
        if not isinstance(row, dict):
            continue
        phase = str(row.get("phase") or "")
        if phase not in COMMITTED_PHASES or phase == "future_scope":
            continue
        for comp in components:
            if not isinstance(comp, str):
                continue
            hours = row.get(comp)
            if isinstance(hours, (int, float)) and hours > 0:
                out.append(
                    {
                        "phase": phase,
                        "component": comp,
                        "recommended_hours": hours,
                        "label": "Estimated effort (hours)",
                    }
                )
    return out


def _appendix_a(feature_list: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    features = feature_list.get("features")
    if not isinstance(features, list):
        return rows
    for item in features:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "")
        if len(desc) > 200:
            desc = desc[:197] + "..."
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "description": desc,
                "priority": str(item.get("priority") or ""),
                "module": str(item.get("module") or ""),
                "phase": "",
            }
        )
    return rows


def _appendix_c(estimate: dict[str, Any], gap: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for a in estimate.get("assumptions_and_solutions") or []:
        if not isinstance(a, dict):
            continue
        confirm = str(a.get("confirm_with_client") or "").strip()
        if not confirm:
            continue
        rows.append(
            {
                "ref": str(a.get("gap_ref") or ""),
                "question": confirm,
                "proposed_assumption": str(a.get("topic") or "") + ": " + str(a.get("solution") or ""),
            }
        )
    gaps = gap.get("gaps")
    if isinstance(gaps, list):
        for index, item in enumerate(gaps, start=1):
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity") or "")
            if sev not in ("high", "medium"):
                continue
            ref = f"G-{index}"
            if any(r.get("ref") == ref for r in rows):
                continue
            rows.append(
                {
                    "ref": ref,
                    "question": str(item.get("clarification_question") or ""),
                    "proposed_assumption": str(item.get("suggested_default_assumption") or ""),
                }
            )
    return rows


def _hypercare_text(estimate: dict[str, Any]) -> str:
    for pkg in estimate.get("work_packages") or []:
        if not isinstance(pkg, dict):
            continue
        if pkg.get("package_type") == "hypercare":
            weeks = float(pkg.get("lead_time_weeks") or 0)
            if weeks > 0:
                return f"{weeks:g} weeks hypercare support following go-live"
            title = str(pkg.get("title") or "Hypercare")
            return f"{title} as described in the work packages"
    return _tbc("hypercare duration")


def _collect_placeholders(assembled_partial: dict[str, Any]) -> list[PlaceholderItem]:
    found: list[PlaceholderItem] = []
    counter = 0

    def walk(obj: Any, location: str) -> None:
        nonlocal counter
        if isinstance(obj, str) and "[TBC:" in obj:
            counter += 1
            found.append(
                PlaceholderItem(
                    placeholder_id=f"P-{counter:03d}",
                    location=location,
                    label=obj,
                )
            )
        elif isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{location}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{location}[{i}]")

    walk(assembled_partial, "assembled")
    return found


def _allowed_numbers(
    user_inputs: dict[str, Any],
    timeline: list[TimelineRow],
    commercials: CommercialsBlock,
) -> list[str]:
    nums: set[str] = set()
    for key in (
        "review_period_business_days",
        "warranty_days",
        "sprint_length_weeks",
    ):
        val = user_inputs.get(key)
        if isinstance(val, (int, float)):
            nums.add(str(int(val) if float(val).is_integer() else val))
    for row in timeline:
        for attr in ("planned_weeks", "start_week", "end_week"):
            v = getattr(row, attr)
            nums.add(str(int(v) if float(v).is_integer() else v))
    if commercials.total_fee is not None:
        nums.add(str(commercials.total_fee))
    for prow in commercials.payment_rows:
        pct = prow.get("percent")
        if isinstance(pct, (int, float)):
            nums.add(str(pct))
    return sorted(nums)


def build_assembled(
    *,
    project_id: str,
    version_no: int,
    status_text: str,
    user_inputs: dict[str, Any],
    scope: dict[str, Any],
    gap: dict[str, Any],
    feature_list: dict[str, Any],
    estimate: dict[str, Any],
    estimate_user_inputs: dict[str, Any] | None = None,
) -> SowAssembled:
    estimate_user_inputs = estimate_user_inputs or {}
    settings = get_settings()
    bundles, bundle_keys = _build_bundles(estimate)
    kickoff = _parse_date(user_inputs.get("kickoff_date"))
    timeline, total_weeks, total_months = _timeline(estimate, kickoff)
    commercials = _commercials(user_inputs)
    optional_items: list[dict[str, str]] = []
    future_items: list[dict[str, str]] = []
    for feat in estimate.get("feature_estimates") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("feature_id") or "")
        title = str(feat.get("title") or fid)
        priority = str(feat.get("priority") or "must")
        phase = str(feat.get("phase") or "")
        if priority == "could":
            optional_items.append({"id": fid, "title": title, "phase": phase})
        if phase == "future_scope" or priority == "wont":
            future_items.append({"id": fid, "title": title, "phase": phase})
    exclusions = [
        str(e) for e in (estimate.get("exclusions") or []) if isinstance(e, str) and e.strip()
    ]
    show_hours = user_inputs.get("show_effort_hours") == "yes"
    effort = _effort_table(estimate, show_hours)
    appendix_b = (
        [
            {
                "phase": r["phase"],
                "component": r["component"],
                "recommended_hours": str(r["recommended_hours"]),
            }
            for r in effort
        ]
        if show_hours
        else []
    )
    hypercare = _hypercare_text(estimate)
    payment_text = (
        "Invoices are due within [TBC: payment days] days of invoice date."
        if not commercials.payment_rows
        else "Payment follows the schedule in section 14."
    )
    standard = build_standard_terms(
        version=settings.SOW_STANDARD_TERMS_VERSION,
        review_days=int(user_inputs.get("review_period_business_days") or 5),
        warranty_days=int(user_inputs.get("warranty_days") or 30),
        sprint_weeks=int(user_inputs.get("sprint_length_weeks") or 2),
        governing_agreement=user_inputs.get("governing_agreement")
        if isinstance(user_inputs.get("governing_agreement"), str)
        else None,
        hypercare_text=hypercare,
        payment_terms_text=payment_text,
    )
    now = datetime.now(UTC).date().isoformat()
    short_id = project_id.replace("-", "")[:6]
    doc_ref = f"SOW-{datetime.now(UTC).year}-{datetime.now(UTC).month:02d}-{short_id}-v{version_no}"
    contents = [
        "1 Introduction",
        "2 Objectives and success criteria",
        "3 Scope of work",
        "4 Deliverables and acceptance criteria",
        "5 Approach and methodology",
        "6 Timeline and milestones",
        "7 Project team and responsibilities",
        "8 Assumptions and constraints",
        "9 Risks",
        "10 Acceptance procedure",
        "11 Change control",
        "12 Governance and communication",
        "13 Warranty, hypercare and support",
        "14 Commercials",
        "15 Confidentiality, IP, liability and termination",
        "16 Signatures",
        "Appendix A — Features",
    ]
    if show_hours:
        contents.append("Appendix B — Effort summary")
    contents.append("Appendix C — Clarifications required")
    assembled = SowAssembled(
        standard_terms_version=settings.SOW_STANDARD_TERMS_VERSION,
        document_reference=doc_ref,
        issue_date=now,
        status_text=status_text,
        bundle_keys=bundle_keys,
        scope_bundles=bundles,
        timeline_table=timeline,
        total_weeks=total_weeks,
        total_months=total_months,
        optional_items=optional_items,
        future_scope_items=future_items,
        exclusions=exclusions,
        delivery_team=_delivery_team(estimate_user_inputs, user_inputs),
        effort_by_phase_component=effort,
        commercials=commercials,
        standard_terms=standard,
        appendix_a=_appendix_a(feature_list),
        appendix_b=appendix_b,
        appendix_c=_appendix_c(estimate, gap),
        allowed_numbers=_allowed_numbers(user_inputs, timeline, commercials),
        placeholders=[],
        contents_list=contents,
    )
    placeholders = _collect_placeholders(assembled.model_dump(mode="json"))
    return assembled.model_copy(update={"placeholders": placeholders})
