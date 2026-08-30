from __future__ import annotations

import pytest

from src.domain.run_spec import SEED_PLAN_VERSION, SeedPlan, derive_seed
from src.worldgen.numeric import SplitMix64, checked_i64, div_round_half_up, identity, stable_id


def test_seed_derivation_contract_golden_and_separation() -> None:
    baseline = derive_seed(42, "terrain", 3, "uplift")
    assert baseline == 2417978552673304059
    assert baseline != derive_seed(42, "terrain", 4, "uplift")
    assert baseline != derive_seed(42, "terrain", 3, "erosion")
    assert baseline != derive_seed(42, "climate", 3, "uplift")
    assert baseline != derive_seed(42, "terrain", 3, "uplift", version="storyteller.seed.sha256.v2")


def test_prng_golden_vectors() -> None:
    assert [SplitMix64(0).next_u64()] == [16294208416658607535]
    rng = SplitMix64(42)
    assert [rng.next_u64() for _ in range(3)] == [
        13679457532755275413,
        2949826092126892291,
        5139283748462763858,
    ]


def test_seed_plan_version_and_separation() -> None:
    plan = SeedPlan(9)
    baseline = plan.for_decision("terrain", 1, "uplift")
    assert baseline == plan.for_decision("terrain", 1, "uplift")
    assert baseline != plan.for_decision("terrain", 2, "uplift")
    assert baseline != plan.for_decision("terrain", 1, "erosion")
    assert baseline != plan.for_decision("climate", 1, "uplift")
    assert plan.version == SEED_PLAN_VERSION
    with pytest.raises(ValueError, match="unsupported"):
        SeedPlan(9, version="future").for_domain("terrain")
    with pytest.raises(ValueError, match="version"):
        derive_seed(9, "terrain", version=" ")


def test_numeric_boundaries_and_stable_ids() -> None:
    assert div_round_half_up(5, 2) == 3
    assert stable_id("site", 42, identity("cell", 1)) == stable_id(
        "site",
        42,
        identity("cell", 1),
    )
    with pytest.raises(OverflowError):
        checked_i64(1 << 63)
