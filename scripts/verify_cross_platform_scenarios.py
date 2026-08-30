#!/usr/bin/env python3
"""Require exact scenario-result parity across Python, Android, and iOS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast


def load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if value.get("format") != "storyteller.contract-results.v2" or not isinstance(
        value.get("scenarios"), dict
    ):
        raise SystemExit(f"invalid result contract: {path}")
    return cast(dict[str, Any], value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-results", required=True)
    parser.add_argument("--android-results", required=True)
    parser.add_argument("--ios-results", required=True)
    args = parser.parse_args()
    results = {
        name: load(getattr(args, f"{name}_results")) for name in ("python", "android", "ios")
    }
    expected = set(results["python"]["scenarios"])
    for platform, value in results.items():
        actual = set(value["scenarios"])
        if actual != expected:
            raise SystemExit(
                f"{platform}: scenario IDs differ: "
                f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
            )
    mismatches = []
    for scenario in sorted(expected):
        baseline = results["python"]["scenarios"][scenario]
        for platform in ("android", "ios"):
            if results[platform]["scenarios"][scenario] != baseline:
                mismatches.append(
                    {
                        "scenario": scenario,
                        "platform": platform,
                        "python": baseline,
                        "actual": results[platform]["scenarios"][scenario],
                    }
                )
    if mismatches:
        raise SystemExit(json.dumps({"parity": False, "mismatches": mismatches}, sort_keys=True))
    print(json.dumps({"parity": True, "platforms": 3, "scenarios": len(expected)}, sort_keys=True))


if __name__ == "__main__":
    main()
