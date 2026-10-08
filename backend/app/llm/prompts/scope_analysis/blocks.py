"""Delimiter helpers for scope_analysis prompts (revise path; v1 unchanged)."""

from __future__ import annotations


def block_markers(block_nonce: str) -> tuple[str, str]:
    open_marker = f"-----BEGIN UNTRUSTED DATA {block_nonce}-----"
    close_marker = f"-----END UNTRUSTED DATA {block_nonce}-----"
    return open_marker, close_marker


def sanitize_for_block(text: str, *, open_marker: str, close_marker: str) -> str:
    sanitized = text.replace(open_marker, "[removed delimiter]")
    sanitized = sanitized.replace(close_marker, "[removed delimiter]")
    return sanitized


def wrap_untrusted(text: str, *, block_nonce: str) -> str:
    open_marker, close_marker = block_markers(block_nonce)
    inner = sanitize_for_block(text, open_marker=open_marker, close_marker=close_marker)
    return f"{open_marker}\n{inner}\n{close_marker}"
