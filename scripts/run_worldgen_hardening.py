"""Validate, print, or execute the bounded worldgen hardening matrix."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.worldgen.conformance.hardening import (  # noqa: E402 -- direct script bootstrap
    HARDENING_MATRIX,
    cases_for_tier,
    validate_hardening_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("fast", "release"), default="fast")
    parser.add_argument("--list", action="store_true", help="print category, tier, and node ID")
    parser.add_argument("--run", action="store_true", help="execute the selected pytest gate")
    args = parser.parse_args()
    validate_hardening_matrix(ROOT)
    selected = cases_for_tier(args.tier)
    if args.list:
        for case in HARDENING_MATRIX:
            print(f"{case.category}\t{case.tier}\t{case.node_id}\t{case.purpose}")
    command = [str(ROOT / ".venv/bin/pytest"), "-q", *(case.node_id for case in selected)]
    if not args.run:
        print(" ".join(command))
        return 0
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
