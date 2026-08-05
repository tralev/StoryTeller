#!/usr/bin/env python3
"""Fail when caches or build products escape the repository tmp/ directory."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "pytest-of-tralev", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "droid/.gradle", "droid/.kotlin", "droid/app/.cxx", "droid/app/build",
    "ios/.build", "ios/build", "ios/llama",
    "lin/build", "lin/dist", "mac/build", "mac/dist", "win/build", "win/dist",
)


def violations() -> list[str]:
    found = [relative for relative in FORBIDDEN if (ROOT / relative).exists()]
    for cache in ROOT.rglob("__pycache__"):
        parts = cache.relative_to(ROOT).parts
        if "tmp" not in parts and ".venv" not in parts:
            found.append(str(cache.relative_to(ROOT)))
    return sorted(set(found))


def main() -> None:
    found = violations()
    if found:
        raise SystemExit("generated state outside tmp/:\n" + "\n".join(f"- {item}" for item in found))
    print("workspace hygiene: clean")


if __name__ == "__main__":
    main()
