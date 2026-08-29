"""WG-INTEGRATION-013 hardening matrix ownership tests."""
from pathlib import Path

import pytest

from src.worldgen.conformance.hardening import (
    HARDENING_MATRIX,
    REQUIRED_CATEGORIES,
    cases_for_tier,
    validate_hardening_matrix,
)


def test_hardening_matrix_has_one_owned_case_per_required_category() -> None:
    validate_hardening_matrix(Path(__file__).resolve().parents[1])
    assert tuple(sorted(case.category for case in HARDENING_MATRIX)) == tuple(
        sorted(REQUIRED_CATEGORIES)
    )
    assert {case.tier for case in HARDENING_MATRIX} == {"fast", "release"}


def test_fast_and_release_tiers_are_bounded_and_monotonic() -> None:
    fast = cases_for_tier("fast")
    release = cases_for_tier("release")
    assert 1 <= len(fast) < len(release) == len(REQUIRED_CATEGORIES)
    assert set(fast) < set(release)
    with pytest.raises(ValueError, match="WG-HARDENING-TIER"):
        cases_for_tier("unknown")
