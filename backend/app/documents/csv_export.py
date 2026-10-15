"""CSV export for estimate item rows with formula-injection prefixing."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(value)
    else:
        text = str(value)
    if text.startswith(_INJECTION_PREFIXES):
        return "'" + text
    return text


def build_estimate_csv(content: dict[str, Any]) -> bytes:
    computed = content.get("computed") if isinstance(content.get("computed"), dict) else {}
    v2 = isinstance(content, dict) and content.get("schema_version") == 2
    roles = [str(r) for r in (computed.get("estimated_roles") or []) if isinstance(r, str)]
    headers = [
        "Status",
        "Phase",
        "Component",
        "ID",
        "Title",
        "Kind",
        "Confidence",
        "AI leverage",
    ]
    if v2:
        headers.extend(["Best", "Likely", "Worst", "With AI", "Recommended"])
        for role in roles:
            headers.append(f"{role} likely")
            headers.append(f"{role} with AI")
            headers.append(f"{role} recommended")
    else:
        for role in roles:
            headers.append(f"{role} base")
            headers.append(f"{role} with AI")
        headers.extend(["Total with AI", "Total buffered"])

    rows = (
        computed.get("item_export_rows")
        if isinstance(computed.get("item_export_rows"), list)
        else []
    )
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for item in rows:
        if not isinstance(item, dict):
            continue
        line = [
            csv_safe_cell(item.get("status")),
            csv_safe_cell(item.get("phase")),
            csv_safe_cell(item.get("component")),
            csv_safe_cell(item.get("id")),
            csv_safe_cell(item.get("title")),
            csv_safe_cell(item.get("kind")),
            csv_safe_cell(item.get("confidence")),
            csv_safe_cell(item.get("ai_leverage")),
        ]
        per_role = item.get("per_role") if isinstance(item.get("per_role"), dict) else {}
        if v2:
            line.extend(
                [
                    csv_safe_cell(item.get("total_best")),
                    csv_safe_cell(item.get("total_likely")),
                    csv_safe_cell(item.get("total_worst")),
                    csv_safe_cell(item.get("total_ai")),
                    csv_safe_cell(item.get("total_recommended")),
                ]
            )
            for role in roles:
                hours = per_role.get(role) if isinstance(per_role.get(role), dict) else {}
                if not isinstance(hours, dict):
                    line.extend(["", "", ""])
                    continue
                line.append(csv_safe_cell(hours.get("likely")))
                line.append(csv_safe_cell(hours.get("ai_adjusted")))
                line.append(csv_safe_cell(hours.get("recommended")))
        else:
            for role in roles:
                hours = per_role.get(role) if isinstance(per_role.get(role), dict) else {}
                line.append(csv_safe_cell(hours.get("base") if isinstance(hours, dict) else ""))
                line.append(
                    csv_safe_cell(hours.get("ai_adjusted") if isinstance(hours, dict) else "")
                )
            line.append(csv_safe_cell(item.get("total_ai")))
            line.append(csv_safe_cell(item.get("total_buffered")))
        writer.writerow(line)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
