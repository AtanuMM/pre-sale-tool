"""Parameterised standard terms (not legal advice). Version bumps when text changes."""

from __future__ import annotations

from typing import Any


def build_standard_terms(
    *,
    version: str,
    review_days: int,
    warranty_days: int,
    sprint_weeks: int,
    governing_agreement: str | None,
    hypercare_text: str,
    payment_terms_text: str,
) -> dict[str, Any]:
    gov = governing_agreement.strip() if governing_agreement else ""
    gov_clause = (
        gov
        if gov
        else "[TBC: governing master services agreement reference]"
    )
    return {
        "version": version,
        "acceptance": {
            "title": "Acceptance procedure",
            "paragraphs": [
                "The supplier will submit deliverables for review as they become available.",
                f"The client has {review_days} business days from receipt to provide written "
                "feedback or accept each submission.",
                "If feedback is provided, the supplier will address it and resubmit within a "
                "reasonable time.",
                f"If no written feedback is received within {review_days} business days, the "
                "submission is deemed accepted unless material defects were notified in writing.",
            ],
        },
        "change_control": {
            "title": "Change control",
            "paragraphs": [
                "Changes to scope, timeline or fees must be requested in writing.",
                "The supplier will assess impact on scope, timeline and fees and respond with a "
                "written change proposal.",
                "Work on the change starts only after written approval from both parties.",
            ],
        },
        "governance": {
            "title": "Governance and communication",
            "paragraphs": [
                f"Sprint demonstrations will be held every {sprint_weeks} weeks.",
                "A written status report will be provided weekly.",
                "A joint review meeting will be held monthly.",
                "Escalation: [TBC: client escalation contact name and role] and "
                "[TBC: supplier escalation contact name and role].",
            ],
        },
        "warranty": {
            "title": "Warranty, hypercare and support",
            "paragraphs": [
                f"Defects against accepted acceptance criteria will be remediated at no "
                f"additional charge for {warranty_days} days after acceptance of the "
                "relevant deliverable.",
                f"Hypercare: {hypercare_text}",
            ],
        },
        "legal": {
            "title": "Confidentiality, IP, liability and termination",
            "paragraphs": [
                f"Confidentiality, intellectual property, limitation of liability and "
                f"termination are governed by {gov_clause}.",
            ],
        },
        "payment": {
            "title": "Payment terms",
            "paragraphs": [payment_terms_text],
        },
    }
