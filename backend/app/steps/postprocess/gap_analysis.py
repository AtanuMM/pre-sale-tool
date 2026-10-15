"""Gap Analysis post-processing: count missing evidence, keep every gap."""

from __future__ import annotations

from pydantic import BaseModel

from app.steps.postprocess import PostprocessContext, PostprocessError
from app.steps.schemas.gap_analysis import GapAnalysisOutput, GapItem


def postprocess_gap_analysis(
    output: BaseModel, _ctx: PostprocessContext
) -> tuple[BaseModel, dict[str, int]]:
    if not isinstance(output, GapAnalysisOutput):
        raise PostprocessError("unexpected output type for gap_analysis")

    gaps: list[GapItem] = []
    without = 0
    for gap in output.gaps:
        evidence = gap.evidence.strip()
        if not evidence:
            without += 1
        gaps.append(gap.model_copy(update={"evidence": evidence}))

    stored = GapAnalysisOutput(
        summary=output.summary.strip(),
        gaps=gaps,
        client_questions=list(output.client_questions),
    )
    return stored, {"gaps_without_evidence": without}
