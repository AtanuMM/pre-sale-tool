"""Repair missing SOW deliverables for specific bundle keys."""

from __future__ import annotations

from app.llm.prompts.scope_analysis.blocks import wrap_untrusted

PROMPT_VERSION = "repair-v1"

SYSTEM_INSTRUCTION = """Return JSON with deliverables only for the listed missing bundle keys.
Each deliverable must use the exact bundle_key provided. Keep acceptance criteria testable.
Do not invent prices, dates, durations or legal terms."""


def build_repair_prompt(
    *,
    missing_keys: list[str],
    context_excerpt: str,
    block_nonce: str,
) -> str:
    keys_block = wrap_untrusted(
        "Missing bundle keys:\n" + "\n".join(f"- {k}" for k in missing_keys),
        block_nonce=f"{block_nonce}-missing",
    )
    ctx = wrap_untrusted(context_excerpt, block_nonce=f"{block_nonce}-ctx")
    return "\n\n".join(
        [
            "Produce deliverables for the missing bundle keys only.",
            keys_block,
            ctx,
        ]
    )
