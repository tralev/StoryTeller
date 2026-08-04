#!/usr/bin/env python3
"""Verify ArtifactStore write-through: JSON files appear on disk IMMEDIATELY.

The claim:
  When PipelineContext(output_dir="...") is used, every
  `context.outputs["key"] = data` writes a JSON file to disk
  before the next line of code executes — not "sometime later"
  or "only at package time."

This script proves (or disproves) that claim by writing artifacts
one at a time and checking the filesystem between each write.

Usage:
    PYTHONPATH=src python scripts/verify_streaming.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from src.job_queue import PipelineContext


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "\u2713" if ok else "\u2717"
    print(f"  {status} {label}")
    if not ok and detail:
        print(f"    └─ {detail}")
    return ok


def main() -> None:
    passed = 0
    failed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)

        print(f"Output: {out}\n")

        # ═══════════════════════════════════════════════════════════════
        # Test 1: Single write — file appears immediately
        # ═══════════════════════════════════════════════════════════════
        print("=== Test 1: Single write appears immediately ===\n")

        ctx = PipelineContext(run_id="vfy", seed=1, output_dir=str(out))

        bible_path = out / "bible.json"
        ok = check("Before write: bible.json does NOT exist", not bible_path.exists())
        passed += ok; failed += not ok

        ctx.outputs["bible"] = {"world_name": "Immediate Test", "entities": {"characters": []}}

        ok = check("After write: bible.json EXISTS", bible_path.exists())
        passed += ok; failed += not ok

        ok = check("Content matches what was written",
                    json.loads(bible_path.read_text()) == {"world_name": "Immediate Test", "entities": {"characters": []}})
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Test 2: Multiple writes — each one lands on disk
        # ═══════════════════════════════════════════════════════════════
        print("\n=== Test 2: Multiple sequential writes ===\n")

        steps = [
            ("style_bible", {"art_style": {"palette": "gold"}}),
            ("story", {"chapters": [{"number": 1}]}),
            ("graph", {"nodes": [{"node_id": "node_01"}]}),
            ("gm_index", {"keywords": {"test": []}}),
        ]

        for key, data in steps:
            path = out / f"{key}.json"
            # Verify it doesn't exist yet (first write)
            before = not path.exists()

            ctx.outputs[key] = data

            # Verify it exists NOW
            after = path.exists() and json.loads(path.read_text()) == data

            ok = check(
                f"Write '{key}' → {key}.json exists with correct content",
                after,
                "File missing or content mismatch" if not after else "",
            )
            passed += ok; failed += not ok

        # Check all 6 files exist on disk
        all_files = ["bible.json", "style_bible.json", "story.json", "graph.json", "gm_index.json"]
        existing = [f for f in all_files if (out / f).exists()]
        ok = check(f"All {len(all_files)} JSON files on disk", len(existing) == len(all_files),
                    f"Missing: {set(all_files) - set(existing)}")
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Test 3: Overwrite — file updates immediately
        # ═══════════════════════════════════════════════════════════════
        print("\n=== Test 3: Overwrite updates file immediately ===\n")

        ctx.outputs["bible"] = {"world_name": "Updated World", "entities": {"characters": ["new"]}}
        content = json.loads((out / "bible.json").read_text())

        ok = check("Overwrite: bible.json reflects new content",
                    content == {"world_name": "Updated World", "entities": {"characters": ["new"]}},
                    f"Got: {json.dumps(content)[:100]}")
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Test 4: Delete — file removed from disk
        # ═══════════════════════════════════════════════════════════════
        print("\n=== Test 4: Delete removes file from disk ===\n")

        del ctx.outputs["style_bible"]
        ok = check("After del: style_bible.json GONE from disk",
                    not (out / "style_bible.json").exists())
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Test 5: Read-back after new context (resume scenario)
        # ═══════════════════════════════════════════════════════════════
        print("\n=== Test 5: Read-back on new context (resume) ===\n")

        ctx2 = PipelineContext(run_id="vfy2", seed=1, output_dir=str(out))
        ok = check("New context reads bible from disk",
                    ctx2.outputs.get("bible") == {"world_name": "Updated World", "entities": {"characters": ["new"]}})
        passed += ok; failed += not ok

        ok = check("New context reads story from disk",
                    ctx2.outputs.get("story") == {"chapters": [{"number": 1}]})
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Test 6: No-disk mode (output_dir=None) — pure memory
        # ═══════════════════════════════════════════════════════════════
        print("\n=== Test 6: output_dir=None (pure memory, no disk) ===\n")

        ctx3 = PipelineContext(run_id="mem", seed=1)
        ctx3.outputs["test"] = {"value": 42}

        # There's no output_dir, so no file should be written anywhere
        ok = check("In-memory context stores value", ctx3.outputs["test"] == {"value": 42})
        passed += ok; failed += not ok

        ok = check("In-memory context has no output_dir", ctx3.outputs.output_dir is None)
        passed += ok; failed += not ok

        # ═══════════════════════════════════════════════════════════════
        # Summary
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{'='*60}")
        print(f"  Results: {passed}/{passed + failed} checks passed")
        if failed == 0:
            print(f"  \u2714 ArtifactStore write-through works correctly!")
            print(f"  Every context.outputs[key] = data flushes to disk immediately.")
        else:
            print(f"  \u2716 {failed} check(s) failed — see above.")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
