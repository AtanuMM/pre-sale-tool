"""SRS requirements register CSV export."""

from __future__ import annotations

from typing import Any

from app.documents.csv_export import csv_safe_cell
from app.steps.schemas.srs import SrsStored


def build_srs_csv(content: dict[str, Any]) -> bytes:
    stored = SrsStored.model_validate(content)
    lines = ["ID,Type,Module,Statement,Priority,Phase,Basis,Verification"]
    for fr in stored.functional_requirements:
        lines.append(
            ",".join(
                csv_safe_cell(v)
                for v in (
                    fr.id,
                    "FR",
                    fr.module,
                    fr.statement,
                    fr.priority,
                    fr.phase,
                    fr.basis,
                    fr.verification_method,
                )
            )
        )
    for nfr in stored.nfr_requirements:
        lines.append(
            ",".join(
                csv_safe_cell(v)
                for v in (
                    nfr.id,
                    "NFR",
                    nfr.category,
                    nfr.statement,
                    "",
                    "",
                    nfr.basis,
                    nfr.verification_method,
                )
            )
        )
    body = "\r\n".join(lines) + "\r\n"
    return ("\ufeff" + body).encode("utf-8")
