"""Smoke test: Gemini accepts Scope Analysis structured output (dummy data only)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from app.llm.gemini import generate_structured_result
from app.llm.prompts.scope_analysis.v1 import (
    SYSTEM_INSTRUCTION,
    AttachmentTextPayload,
    IntakeItemPayload,
    build_user_prompt,
)
from app.steps.schemas.scope_analysis import ScopeAnalysisOutput


def main() -> int:
    nonce = "smoke-test-nonce"
    prompt = build_user_prompt(
        project_name="Northwind Widgets Pilot",
        client_name="Contoso Example Ltd",
        intake_items=[
            IntakeItemPayload(
                received_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
                kind="email",
                subject="Widget portal phase 1",
                body=(
                    "We need a customer portal for order tracking and invoice download. "
                    "Must integrate with our fictional ERP called ExampleERP. "
                    "Mobile-friendly is important. Budget discussion later."
                ),
            )
        ],
        attachment_texts=[
            AttachmentTextPayload(
                label="notes.txt",
                text="Optional attachment: admin users need CSV export of orders.",
            )
        ],
        block_nonce=nonce,
    )
    result = generate_structured_result(
        prompt,
        ScopeAnalysisOutput,
        system=SYSTEM_INSTRUCTION,
    )
    data = result.data
    print(f"model_id={result.model_id}")
    print(f"tokens_in={result.tokens_in} tokens_out={result.tokens_out}")
    print(f"objectives_count={len(data.objectives)}")
    print(f"risks_count={len(data.risks)}")
    print(f"executive_summary_chars={len(data.executive_summary)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
