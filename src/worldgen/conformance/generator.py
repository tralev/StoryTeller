"""P8.C05A step 1 — Coverage ledger generator.

Reads requirements from `src/worldgen/conformance/requirements.py` and
produces `docs/worldgen-coverage.generated.md`. The generator fails on
duplicate IDs, missing columns, unknown statuses, or a completed row
without a real test.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .requirements import REQUIREMENTS, Status, requirement_owner, validate_requirements
from .source_coverage import SOURCE_CLAUSES, validate_source_coverage
from .evidence import validate_evidence


def _count_by_status(reqs: list[Any]) -> dict[Status, int]:
    c: Counter[str] = Counter()
    for r in reqs:
        c[r.status] += 1
    return {k: c.get(k, 0) for k in ("complete", "partial", "missing", "obsolete")}  # type: ignore[misc]


def _sorted_by_id(reqs: list[Any]) -> list[Any]:
    # Sort: kernel first, then phys, route, soc, hist, local, integration
    # ECO is absent — ecology requirements are filed under PHYS and ROUTE.
    order = {prefix: i for i, prefix in enumerate(
        ("KERNEL", "PHYS", "ROUTE", "SOC", "HIST", "LOCAL", "INTEGRATION"),
    )}
    def sort_key(r: Any) -> tuple[int, str]:
        for prefix, idx in order.items():
            if prefix in r.id:
                return (idx, r.id)
        return (999, r.id)
    return sorted(reqs, key=sort_key)


def generate_markdown() -> str:
    """Produce the complete worldgen-coverage.generated.md content."""
    errors = validate_requirements()
    errors.extend(validate_source_coverage())
    errors.extend(validate_evidence())
    if errors:
        raise ValueError("requirement catalog invalid:\n" + "\n".join(errors))

    rows_by_domain: dict[str, list[str]] = {}
    for req in _sorted_by_id(REQUIREMENTS):
        domain = req.id.split("-")[1]  # e.g. WG-KERNEL-001 → KERNEL
        row = (
            f"| `{req.id}` | {req.description} | `{req.target_symbol}` | "
            f"`{req.artifact_kind}` | `{req.validator}` | "
            f"`{req.test}` | {requirement_owner(req.id)} | {req.status} |"
        )
        rows_by_domain.setdefault(domain, []).append(row)

    counts = _count_by_status(REQUIREMENTS)
    active_total = counts.get("complete", 0) + counts.get("partial", 0) + counts.get("missing", 0)
    complete_pct = counts.get("complete", 0) / max(active_total, 1) * 100

    lines: list[str] = []
    lines.extend([
        "# Worldgen Coverage Ledger",
        "",
        f"> Generated from `src/worldgen/conformance/requirements.py`. "
        f"This is evidence, not authority. "
        f"The three absorbed specifications (`generation.md`, `worldgen-rewrite.md`, "
        f"`worldgen-legacy.generated.md`) were deleted after their recoverable "
        f"clauses mapped into this checked replacement.",
        "",
        f"**Status:** {counts['complete']} complete, {counts['partial']} partial, "
        f"{counts['missing']} missing, {counts['obsolete']} obsolete "
        f"({complete_pct:.0f}% of active requirements complete)",
        "",
        "| Requirement ID | Description | Target Symbol | Artifact | Validator | Test | Owner | Status |",
        "|---|---|---|---|---|---|---|---|",
    ])

    domain_labels = {
        "KERNEL": "WG-KERNEL — Deterministic Foundation",
        "PHYS": "WG-PHYS — Physical World, Climate, Geology, Ecology",
        "ROUTE": "WG-ROUTE — Regions, Routes, Maps, Spatial Indexes",
        "ECO": "WG-ECO — Regions, Routes, Maps, Spatial/Reference Indexes",
        "SOC": "WG-SOC — Peoples, Identities, Magic, Settlement, Economy",
        "HIST": "WG-HIST — Monthly Causal History, Events, Snapshots, Replay",
        "LOCAL": "WG-LOCAL — Local 3D Worlds, Macro/Micro Reconciliation",
        "INTEGRATION": "WG-INTEGRATION — Story Projection, Production, Hardening",
    }

    for domain, label in domain_labels.items():
        rows = rows_by_domain.get(domain)
        if not rows:
            continue
        lines.append("")
        lines.append(f"### {label}")
        lines.append("")
        lines.append(
            "| Requirement ID | Description | Target Symbol | Artifact | Validator | Test | Owner | Status |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.extend(rows)

    lines.append("")
    lines.append("## Recoverable Source-Clause Coverage")
    lines.append("")
    lines.append("Every normative feature row recoverable from the retained 2026-08-05 audit maps")
    lines.append("to exactly one stable requirement; generation fails on unmapped or stale anchors.")
    lines.append("")
    lines.append("| Clause ID | Retained source anchor | Requirement ID |")
    lines.append("|---|---|---|")
    for clause in SOURCE_CLAUSES:
        lines.append(f"| `{clause.clause_id}` | {clause.anchor} | `{clause.requirement_id}` |")
    lines.append("")
    lines.append("## Known Defects (Characterization Only)")
    lines.append("")
    lines.append("These rows carry `obsolete` status because the prototype behavior is not a")
    lines.append("target contract. Each now links to an executable target-invariant regression")
    lines.append("test proving the replacement does not reproduce that defect.")
    lines.append("")
    lines.append(
        "| Requirement ID | Description | Target Symbol | Artifact | Validator | Test | Owner | Status |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for req in _sorted_by_id(REQUIREMENTS):
        if req.status == "obsolete":
            lines.append(
                f"| `{req.id}` | {req.description} | `{req.target_symbol}` | "
                f"`{req.artifact_kind}` | `{req.validator}` | "
                f"`{req.test}` | {requirement_owner(req.id)} | {req.status} |"
            )

    lines.append("")
    total_reqs = len(REQUIREMENTS)
    source_md = hashlib.sha256(
        Path(__file__).parent.joinpath("requirements.py").read_bytes()
    ).hexdigest()[:12]
    lines.append(f"*{total_reqs} requirements across {len(rows_by_domain)} domains. "
                 f"Source hash: {source_md}*")

    return "\n".join(lines) + "\n"


def write_coverage_doc(output_path: str | Path) -> int:
    """Write the coverage ledger and return the total requirement count."""
    content = generate_markdown()
    path = Path(output_path)
    path.write_text(content)
    return len(REQUIREMENTS)


def check_coverage_doc(output_path: str | Path) -> bool:
    """Return True if the on-disk coverage doc matches the generated one."""
    path = Path(output_path)
    if not path.exists():
        return False
    expected = generate_markdown()
    return path.read_text() == expected


if __name__ == "__main__":
    write_coverage_doc("docs/worldgen-coverage.generated.md")
    print(f"Wrote {len(REQUIREMENTS)} requirements to docs/worldgen-coverage.generated.md")
