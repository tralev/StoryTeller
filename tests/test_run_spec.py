"""Phase 1 domain-contract and seed-plan tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.run_spec import RunSpec, SeedPlan, WorldSpec, derive_seed


def test_world_spec_defaults_are_target_profile() -> None:
    spec = WorldSpec()
    assert (spec.width, spec.height) == (1024, 1024)
    assert spec.continent_count == 1
    assert spec.history_ticks_per_year == 12
    assert spec.snapshot_interval_years == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width": 31}, {"height": 8193}, {"continent_count": 0},
        {"plate_count": 0}, {"history_ticks_per_year": 4},
        {"snapshot_interval_years": 5}, {"local_z_levels": 3},
    ],
)
def test_world_spec_rejects_invalid_values(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        WorldSpec(**kwargs)


def test_run_spec_is_frozen_and_validated() -> None:
    spec = RunSpec(seed=42, title="The Iron Schism")
    with pytest.raises(FrozenInstanceError):
        spec.title = "changed"
    with pytest.raises(ValueError):
        RunSpec(seed=1, title=" ")


def test_seed_derivation_golden_vector() -> None:
    assert derive_seed(42, "terrain", 3, 7) == 15243164972910376052


def test_seed_domains_and_items_are_separated() -> None:
    plan = SeedPlan(42)
    values = {
        plan.for_domain("terrain", 1),
        plan.for_domain("terrain", 2),
        plan.for_domain("hydrology", 1),
    }
    assert len(values) == 3
    assert plan.for_domain("terrain", 1) == plan.for_domain("terrain", 1)
