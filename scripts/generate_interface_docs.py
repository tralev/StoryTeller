"""Generate/check plan and CLI snapshots used by the authoritative docs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.plan import PipelinePlan  # noqa: E402


def _pipeline_table(plan: PipelinePlan, *, header_md: str) -> str:
    plan.validate()
    rows = [
        "| Order | Step | Output | Requires | Model | Failure | Checkpoint |",
        "|---:|---|---|---|---|---|---|",
    ]
    for order, step in enumerate(plan, 1):
        rows.append(
            f"| {order} | `{step.id}` | `{step.output_key}` | "
            f"{', '.join(f'`{key}`' for key in step.requires) or '—'} | "
            f"{step.model_role or 'none'} | {step.failure_policy} | "
            f"{'yes' if step.checkpoint else 'no'} |"
        )
    return header_md + "\n".join(rows) + "\n"


def pipeline_markdown() -> str:
    return _pipeline_table(
        PipelinePlan.production_v2(),
        header_md="""# Generated Production Pipeline Plan

> `PipelinePlan.production_v2()` is the sole product generation and resume plan.
> This file is generated implementation evidence; see `arch.md` for authority.

""",
    )


def cli_help() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = {
        ROOT / "docs" / "pipeline.generated.md": pipeline_markdown(),
        ROOT / "docs" / "cli-help.generated.txt": cli_help(),
    }
    stale = [
        path
        for path, content in outputs.items()
        if not path.exists() or path.read_text() != content
    ]
    if args.check and stale:
        raise SystemExit("stale generated docs: " + ", ".join(str(path) for path in stale))
    if not args.check:
        for path, content in outputs.items():
            path.write_text(content)


if __name__ == "__main__":
    main()
