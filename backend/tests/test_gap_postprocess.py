from app.steps.postprocess import PostprocessContext
from app.steps.postprocess.gap_analysis import postprocess_gap_analysis
from app.steps.schemas.gap_analysis import GapAnalysisOutput


def _gap(**overrides) -> dict:
    base = {
        "title": "Auth provider unknown",
        "category": "ambiguity",
        "severity": "high",
        "description": "Scope mentions SSO but not IdP.",
        "why_it_matters": "Blocks security design.",
        "clarification_question": "Which identity provider?",
        "suggested_default_assumption": "Assume a hosted directory.",
        "related_scope_section": "In scope",
    }
    base.update(overrides)
    return base


def test_v1_gap_without_evidence_still_validates_and_is_kept() -> None:
    output = GapAnalysisOutput.model_validate(
        {
            "summary": "Several clarifications needed.",
            "gaps": [_gap()],
            "client_questions": ["Which identity provider will be used?"],
        }
    )
    assert output.gaps[0].evidence == ""
    stored, notes = postprocess_gap_analysis(output, PostprocessContext())
    assert len(stored.gaps) == 1
    assert stored.gaps[0].title == "Auth provider unknown"
    assert notes["gaps_without_evidence"] == 1


def test_evidence_present_is_counted_zero() -> None:
    output = GapAnalysisOutput.model_validate(
        {
            "summary": "One gap.",
            "gaps": [_gap(evidence="REQ-04 SSO section")],
            "client_questions": ["Which identity provider?"],
        }
    )
    stored, notes = postprocess_gap_analysis(output, PostprocessContext())
    assert stored.gaps[0].evidence == "REQ-04 SSO section"
    assert notes["gaps_without_evidence"] == 0
