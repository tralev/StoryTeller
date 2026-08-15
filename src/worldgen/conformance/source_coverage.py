"""Recoverable source-clause coverage for the deleted worldgen specifications.

The original specifications were deleted before P8.C05A.  The dated audit is
the retained clause-level evidence: every feature row it recovered must map to
exactly one stable requirement.  Validation fails if the archive changes, a row
is unmapped, or a mapping points outside the checked requirement catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .requirements import REQUIREMENTS

SOURCE_PATH = "docs/missing_wg_features.2026-08-05.md"


@dataclass(frozen=True)
class SourceClause:
    clause_id: str
    anchor: str
    requirement_id: str


def _clauses(prefix: str, requirement: str, anchors: tuple[str, ...]) -> tuple[SourceClause, ...]:
    return tuple(SourceClause(f"AUDIT-{prefix}-{index:02d}", anchor, requirement)
                 for index, anchor in enumerate(anchors, 1))


SOURCE_CLAUSES = (
    *_clauses("COSMO", "WG-SOC-014", (
        "Cosmological layers, afterlife claims, celestial cycles",
        "Gods, saints, spirits, demons, false entities",
        "Holy sites, relics, taboos, cults, rites, schisms, institutions",
        "Supernatural hazards/resources linked to exact places",
    )),
    SourceClause("AUDIT-COSMO-05", "Magic transformation must go through explicit events paying costs", "WG-SOC-003"),
    SourceClause("AUDIT-COSMO-06", "Every belief has `epistemic_status` (true/false/uncertain/metaphorical)", "WG-SOC-003"),
    SourceClause("AUDIT-LANG-01", "`Language` dataclass with phoneme inventory, syllable patterns, morphemes", "WG-SOC-002"),
    SourceClause("AUDIT-LANG-02", "Writing system generation", "WG-SOC-002"),
    SourceClause("AUDIT-LANG-03", "Sound shifts, language evolution over history", "WG-SOC-012"),
    SourceClause("AUDIT-LANG-04", "Profanity, duplicate, confusable, reserved-name filters", "WG-SOC-012"),
    SourceClause("AUDIT-LANG-05", "`realize_syllable` with C/V token replacement", "WG-SOC-012"),
    *_clauses("HERALDRY", "WG-SOC-013", (
        "Deterministic palette with contrast constraints", "Background division and overlay motif",
        "Motif meanings linked to cultural beliefs/history",
        "Vector-like pattern parameters (not only raster)",
    )),
    *_clauses("DEPOSIT", "WG-PHYS-012", (
        "`Deposit` with geometry (shape, cells, depth range, grade, quantity)",
        "`discovered_year` tracking per deposit",
        "`GeologyFactors` and `ClimateFactors` type-driven resource suitability",
        "Rare fantasy materials tied to geological or magical anomalies",
    )),
    *_clauses("ECOLOGY", "WG-PHYS-014", (
        "`Species` dataclass with trophic level, habitat biomes, temperature range, food species",
        "Domestication candidates", "Migration corridors as spatial artifacts",
        "Extinction tracking over history",
    )),
    SourceClause("AUDIT-MAP-01", "One region map per region", "WG-ROUTE-006"),
    *_clauses("MAPDETAIL", "WG-ROUTE-007", (
        "Frozen colour tables for all layer types", "Label placement algorithm",
        "Political, travel, hazard maps", "Derived presentation maps never replace authoritative facts",
    )),
    *_clauses("OPPORTUNITY", "WG-INTEGRATION-001", (
        "Targeted `src/worldgen/simulation/projections.py` module covering all opportunity types",
        "Interesting frontiers, chokepoints, contested resources as opportunity sources",
        "Mysteries with factual answers in history/geology",
        "Factions with goals, capacity, relationships, credible constraints",
        "Candidate protagonists, antagonists, patrons, witnesses",
        "Revealable facts indexed by story nodes",
    )),
    *_clauses("LOCAL", "WG-LOCAL-003", (
        "Building interiors as separate local-map features", "Items as local entities with ownership/stats",
        "Event scars as spatial features (ruins, abandoned roads, etc.)",
    )),
    *_clauses("PREFLIGHT", "WG-SOC-010", (
        "Explicit site-count budget and preflight formula",
        "Memory, disk, time estimates for requested world size",
        "Abort-with-diagnostic on resource overrun",
    )),
)


def extract_recoverable_feature_rows(source: str) -> set[str]:
    """Extract feature cells from normative missing-feature tables."""
    rows: set[str] = set()
    for line in source.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if (len(cells) == 3 and cells[0] not in {"Feature", "---"}
                and ("`generation.md`" in cells[1] or "`worldgen-rewrite.md`" in cells[1])):
            rows.add(cells[0])
    return rows


def validate_source_coverage(root: str | Path | None = None) -> list[str]:
    project = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    path = project / SOURCE_PATH
    if not path.is_file():
        return [f"missing retained source audit: {SOURCE_PATH}"]
    source = path.read_text()
    errors: list[str] = []
    ids = [clause.clause_id for clause in SOURCE_CLAUSES]
    if len(ids) != len(set(ids)):
        errors.append("duplicate source clause ID")
    requirement_ids = {requirement.id for requirement in REQUIREMENTS}
    mapped_anchors = {clause.anchor for clause in SOURCE_CLAUSES}
    recovered = extract_recoverable_feature_rows(source)
    for anchor in sorted(recovered - mapped_anchors):
        errors.append(f"unmapped recoverable clause: {anchor}")
    for anchor in sorted(mapped_anchors - recovered):
        errors.append(f"stale source clause anchor: {anchor}")
    for clause in SOURCE_CLAUSES:
        if clause.requirement_id not in requirement_ids:
            errors.append(f"unknown requirement for {clause.clause_id}: {clause.requirement_id}")
        if source.count(clause.anchor) != 1:
            errors.append(f"source anchor must occur exactly once: {clause.clause_id}")
    return errors
