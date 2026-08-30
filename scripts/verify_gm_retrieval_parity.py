#!/usr/bin/env python3
"""Require exact ordered GM retrieval IDs across Python, Android, and iOS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if value.get("format") != "storyteller.gm-retrieval-results.v1":
        raise SystemExit(f"invalid GM retrieval results: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs=3, type=Path, metavar=("PYTHON", "ANDROID", "IOS"))
    args = parser.parse_args()
    results = [load(path) for path in args.paths]
    baseline = results[0]["scenarios"]
    for path, result in zip(args.paths[1:], results[1:]):
        if result["scenarios"] != baseline:
            raise SystemExit(f"GM retrieval parity mismatch: {path}")
    print(json.dumps({"parity": True, "platforms": 3, "scenarios": len(baseline)}, sort_keys=True))


if __name__ == "__main__":
    main()
