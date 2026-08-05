from __future__ import annotations

import pytest

from src.domain.run_spec import SeedPlan, derive_seed
from src.worldgen.numeric import SplitMix64, checked_i64, div_round_half_up, stable_id


def test_seed_golden_vectors() -> None:
    assert derive_seed(42, "terrain", 3, 7) == 15243164972910376052
    assert [SplitMix64(0).next_u64()] == [16294208416658607535]
    rng = SplitMix64(42)
    assert [rng.next_u64() for _ in range(3)] == [
        13679457532755275413, 2949826092126892291, 5139283748462763858,
    ]


def test_seed_plan_version_and_separation() -> None:
    plan = SeedPlan(9)
    assert plan.for_domain("terrain", 1) != plan.for_domain("terrain", 2)
    assert plan.for_domain("terrain", 1) != plan.for_domain("climate", 1)
    with pytest.raises(ValueError, match="unsupported"):
        SeedPlan(9, version="future").for_domain("terrain")


def test_numeric_boundaries_and_stable_ids() -> None:
    assert div_round_half_up(5, 2) == 3
    assert stable_id("site", 42, 1) == stable_id("site", 42, 1)
    with pytest.raises(OverflowError):
        checked_i64(1 << 63)
