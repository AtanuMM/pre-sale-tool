"""Print a fictional ~25k character scope document for live smoke tests (stdout)."""

from __future__ import annotations

import argparse

TARGET_DEFAULT = 25_000

PARAGRAPH = (
    "Fictional client Acme Example Corp requests a purely imaginary widget portal "
    "for the Northwind training environment. This paragraph is synthetic test data "
    "only and must not be treated as a real engagement. "
    "Integration points include ExampleERP, SampleCRM, and the MockAuth service. "
    "Non-functional needs: accessibility, audit logging, and export to CSV. "
)


def compose(target_chars: int) -> str:
    parts: list[str] = []
    total = 0
    n = 0
    while total < target_chars:
        n += 1
        chunk = f"[Section {n}] {PARAGRAPH}"
        parts.append(chunk)
        total += len(chunk) + 1
    text = "\n".join(parts)
    if len(text) > target_chars:
        text = text[:target_chars]
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chars",
        type=int,
        default=TARGET_DEFAULT,
        help="Approximate character count (default 25000)",
    )
    args = parser.parse_args()
    print(compose(args.chars), end="")


if __name__ == "__main__":
    main()
