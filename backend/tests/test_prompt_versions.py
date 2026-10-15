from app.llm.prompts import generic_revise, generic_revise_v4
from app.llm.prompts.estimate import v1 as estimate_v1
from app.llm.prompts.estimate import v2 as estimate_v2
from app.llm.prompts.feature_list import v1 as feature_v1
from app.llm.prompts.feature_list import v2 as feature_v2
from app.llm.prompts.gap_analysis import v1 as gap_v1
from app.llm.prompts.gap_analysis import v2 as gap_v2

_BANNED = (
    "sipit",
    "hyderabad",
    "razorpay",
    "cashfree",
    "contoso",
    "exampleerp",
    "unknown-indian",
)


def _blob(*parts: str) -> str:
    return "\n".join(parts).casefold()


def test_released_v1_prompts_untouched() -> None:
    assert gap_v1.PROMPT_VERSION == "v1"
    assert "Find only gaps supported by evidence" in gap_v1.SYSTEM_INSTRUCTION
    assert feature_v1.PROMPT_VERSION == "v1"
    assert "Break the approved scope into modules" in feature_v1.SYSTEM_INSTRUCTION
    assert generic_revise.PROMPT_VERSION == "generic-revise-v3"
    assert estimate_v1.PROMPT_VERSION == "v1"
    assert "Propose BASE effort in hours" in estimate_v1.SYSTEM_INSTRUCTION


def test_v2_prompt_versions_and_generic_revise_v4() -> None:
    assert gap_v2.PROMPT_VERSION == "v2"
    assert feature_v2.PROMPT_VERSION == "v2"
    assert generic_revise_v4.PROMPT_VERSION == "generic-revise-v4"
    assert "source_requirement_ids" in generic_revise_v4.SYSTEM_INSTRUCTION
    assert "two readings" in gap_v2.SYSTEM_INSTRUCTION.casefold()
    assert "implied-work checklist" in feature_v2.SYSTEM_INSTRUCTION.casefold()
    assert "never drop a could" in feature_v2.SYSTEM_INSTRUCTION.casefold()
    assert estimate_v2.PROMPT_VERSION == "v2"
    assert "best / likely / worst" in estimate_v2.SYSTEM_INSTRUCTION.casefold()
    assert "ai-gain" in estimate_v2.SYSTEM_INSTRUCTION.casefold()
    blob = estimate_v2.SYSTEM_INSTRUCTION.casefold()
    assert "headcount" in blob
    assert "do not mention" in blob


def test_v2_prompts_have_no_client_specific_names() -> None:
    text = _blob(
        gap_v2.SYSTEM_INSTRUCTION,
        gap_v2.build_user_prompt(
            project_name="P", client_name="C", untrusted_preamble="U"
        ),
        feature_v2.SYSTEM_INSTRUCTION,
        feature_v2.build_user_prompt(
            project_name="P",
            client_name="C",
            untrusted_preamble="U",
            notes_block="",
        ),
        generic_revise_v4.SYSTEM_INSTRUCTION,
    )
    for word in _BANNED:
        assert word not in text
