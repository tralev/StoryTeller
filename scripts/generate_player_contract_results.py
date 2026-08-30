#!/usr/bin/env python3
"""Generate the authoritative Python scenario outcomes for native comparison."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.storage.package_v2 import validate_v2_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    catalog = json.loads((ROOT / "tests/fixtures/v2/catalog.json").read_text())
    out = {}
    for item in catalog["scenarios"]:
        result = validate_v2_package(ROOT / "tests/fixtures/v2" / item["path"])
        out[item["id"]] = {
            "outcome": "accepted" if result.accepted else "invalid",
            "issue_codes": [issue.code for issue in result.issues],
        }
    value = {"format": "storyteller.contract-results.v2", "scenarios": out}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    print(json.dumps({"output": str(path), "scenarios": len(out)}, sort_keys=True))


if __name__ == "__main__":
    main()
