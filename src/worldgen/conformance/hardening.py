"""Bounded, reviewable hardening matrix for WG-INTEGRATION-013."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HardeningTier = Literal["fast", "release"]

REQUIRED_CATEGORIES = (
    "property",
    "mutation",
    "fuzz",
    "hostile_input",
    "determinism",
    "worker_count",
    "cancellation",
    "crash_recovery",
    "security",
    "performance",
    "disk",
    "memory",
)


@dataclass(frozen=True, order=True)
class HardeningCase:
    category: str
    tier: HardeningTier
    node_id: str
    purpose: str


HARDENING_MATRIX = (
    HardeningCase(
        "property",
        "fast",
        "tests/worldgen/test_properties.py",
        "seeded physical-world invariant properties",
    ),
    HardeningCase(
        "mutation",
        "fast",
        "tests/worldgen/test_artifacts.py::"
        "test_invariant_evidence_rejects_adversarial_ledger_and_river_mutations",
        "domain validator mutation rejection",
    ),
    HardeningCase(
        "fuzz",
        "fast",
        "tests/worldgen/test_grid.py::"
        "test_dense_grid_reconstruction_rejects_missing_duplicate_and_corrupt_chunks",
        "malformed chunk/index matrix",
    ),
    HardeningCase(
        "hostile_input",
        "fast",
        "tests/test_numeric_kernel_p8c05b.py::"
        "test_canonical_json_rejects_hostile_keys_floats_and_surrogates",
        "hostile canonical-JSON values",
    ),
    HardeningCase(
        "determinism",
        "fast",
        "tests/worldgen/test_defect_regressions_p8c05a.py::"
        "test_order_dependence_regression_worker_counts_match",
        "stable ordering regression vector",
    ),
    HardeningCase(
        "worker_count",
        "release",
        "tests/worldgen/test_artifacts.py::"
        "test_physical_stage_dag_and_worker_counts_produce_identical_bytes",
        "one-worker versus multi-worker artifact bytes",
    ),
    HardeningCase(
        "cancellation",
        "fast",
        "tests/test_pipeline_runner.py::test_runner_propagates_cancellation_before_work",
        "typed cancellation before generation work",
    ),
    HardeningCase(
        "crash_recovery",
        "release",
        "tests/test_media_atomicity.py::"
        "test_crash_after_publish_creates_no_checkpoint_and_safe_resume",
        "atomic media publication and safe retry",
    ),
    HardeningCase(
        "security",
        "fast",
        "tests/v2/test_security.py::test_path_traversal_is_rejected",
        "archive path confinement",
    ),
    HardeningCase(
        "performance",
        "fast",
        "tests/test_run_spec.py::test_world_preflight_has_stable_resource_diagnostics",
        "bounded preflight time/RAM/disk estimates",
    ),
    HardeningCase(
        "disk",
        "release",
        "tests/worldgen/test_local_streaming_p8c05g.py::"
        "test_local_storage_audit_reports_complete_bounded_inventory",
        "complete local-world disk inventory and budget",
    ),
    HardeningCase(
        "memory",
        "fast",
        "tests/worldgen/test_grid.py::test_dense_grid_partial_edges_and_chunk_memory_bound",
        "single-chunk dense-grid memory bound",
    ),
)


def cases_for_tier(tier: HardeningTier) -> tuple[HardeningCase, ...]:
    """Fast is the iteration gate; release includes fast plus expensive evidence."""
    if tier not in ("fast", "release"):
        raise ValueError(f"WG-HARDENING-TIER: unsupported tier {tier}")
    return tuple(case for case in HARDENING_MATRIX if tier == "release" or case.tier == "fast")


def validate_hardening_matrix(root: str | Path) -> None:
    """Reject missing categories, duplicate ownership, or stale test paths."""
    repository = Path(root).resolve()
    categories = tuple(case.category for case in HARDENING_MATRIX)
    if tuple(sorted(categories)) != tuple(sorted(REQUIRED_CATEGORIES)):
        raise ValueError("WG-HARDENING-COVERAGE: every category is required exactly once")
    node_ids = tuple(case.node_id for case in HARDENING_MATRIX)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("WG-HARDENING-DUPLICATE: test ownership must be unique")
    for case in HARDENING_MATRIX:
        relative = case.node_id.split("::", 1)[0]
        if not (repository / relative).is_file():
            raise ValueError(f"WG-HARDENING-STALE: missing {relative}")
