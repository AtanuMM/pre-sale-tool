from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.llm.prompts.scope_analysis import revise_v1
from app.llm.prompts.scope_analysis.blocks import block_markers, wrap_untrusted
from app.llm.prompts.scope_analysis.v1 import IntakeItemPayload


def test_wrap_untrusted_strips_delimiter_injection() -> None:
    nonce = "test-nonce"
    open_m, _ = block_markers(nonce)
    inner = f"hello {open_m} world"
    wrapped = wrap_untrusted(inner, block_nonce=nonce)
    assert "[removed delimiter]" in wrapped
    assert open_m in wrapped


def test_revise_user_prompt_includes_instructions_and_previous_json() -> None:
    nonce = str(uuid.uuid4())
    prompt = revise_v1.build_revise_user_prompt(
        project_name="Demo",
        client_name="Client",
        intake_items=[
            IntakeItemPayload(
                received_at=datetime.now(UTC),
                kind="email",
                subject="Subj",
                body="Body text",
            )
        ],
        attachment_texts=[],
        client_block_nonce=f"{nonce}-client",
        previous_analysis_json='{"executive_summary":"old"}',
        previous_block_nonce=f"{nonce}-prev",
        reviewer_instructions="Expand risks section",
        instructions_block_nonce=f"{nonce}-instr",
    )
    assert "Expand risks section" in prompt
    assert "executive_summary" in prompt
    assert revise_v1.PROMPT_VERSION
