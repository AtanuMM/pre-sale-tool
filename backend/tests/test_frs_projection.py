"""FRS client-safe projection tests."""

from app.steps.client_safe import FORBIDDEN_PROMPT_SUBSTRINGS
from app.steps.frs_projection import build_frs_context


def test_frs_projection_is_client_safe() -> None:
    payload = build_frs_context(
        scope={"executive_summary": "Summary", "objectives": []},
        gap={"gaps": []},
        feature_list={
            "features": [
                {
                    "id": "F-001",
                    "title": "Login",
                    "module": "Auth",
                    "priority": "must",
                    "phase": "mvp",
                    "description": "Sign in",
                }
            ]
        },
        estimate={"assumptions_and_solutions": []},
        sow={"narrative": {}},
        srs={"functional_requirements": [], "entities": [], "interfaces": []},
        sprint_plan={"stories": [{"id": "US-0001", "title": "Login story", "feature_id": "F-001"}]},
        frs_user_inputs={"detail_level": "detailed"},
    )
    blob = str(payload).casefold()
    for token in FORBIDDEN_PROMPT_SUBSTRINGS:
        assert token.casefold() not in blob
