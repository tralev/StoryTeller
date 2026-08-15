"""Phase 1 domain-contract and seed-plan tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.run_spec import (
    WORLD_BUDGET_ALGORITHM_VERSION, RunSpec, SeedPlan, WorldBudgetError, WorldSpec,
    derive_seed,
)


def test_world_spec_defaults_are_target_profile() -> None:
    spec = WorldSpec()
    assert (spec.width, spec.height) == (1024, 1024)
    assert spec.continent_count == 1
    assert spec.history_ticks_per_year == 12
    assert spec.snapshot_interval_years == 10


def test_world_budget_estimate_counts_every_site_and_is_stable() -> None:
    spec = WorldSpec(width=32, height=32, civilization_count=3,
                     local_site_width=32, local_site_height=32, local_z_levels=4,
                     history_years=10, erosion_passes=2, climate_relaxation_passes=8,
                     minimum_continent_cells=1, plate_count=4)
    estimate = spec.budget_estimate()
    assert estimate.algorithm_version == WORLD_BUDGET_ALGORITHM_VERSION == "world-budget-v1"
    assert estimate.site_count == 3
    assert estimate.world_cells == 1_024
    assert estimate.local_cells_per_site == 4_096
    assert estimate.total_local_cells == 12_288
    assert estimate.peak_ram_bytes == spec.estimated_working_set_bytes()
    assert estimate.disk_bytes > estimate.total_local_cells * 4
    assert estimate.time_milliseconds > 0
    assert estimate == spec.budget_estimate()


@pytest.mark.parametrize(("budget_name", "code", "field"), (
    ("max_ram_bytes", "WG-BUDGET-RAM", "peak_ram_bytes"),
    ("max_disk_bytes", "WG-BUDGET-DISK", "disk_bytes"),
    ("max_time_milliseconds", "WG-BUDGET-TIME", "time_milliseconds"),
))
def test_world_preflight_has_stable_resource_diagnostics(budget_name, code, field) -> None:
    spec = WorldSpec(width=32, height=32, civilization_count=2,
                     local_site_width=32, local_site_height=32, local_z_levels=4,
                     minimum_continent_cells=1, plate_count=4)
    estimate = spec.budget_estimate()
    budgets = {"max_ram_bytes": estimate.peak_ram_bytes,
               "max_disk_bytes": estimate.disk_bytes,
               "max_time_milliseconds": estimate.time_milliseconds}
    budgets[budget_name] = getattr(estimate, field) - 1
    with pytest.raises(WorldBudgetError) as failure:
        spec.preflight(**budgets)
    assert failure.value.diagnostic.code == code
    assert failure.value.diagnostic.resource == budget_name.removeprefix("max_").removesuffix(
        "_bytes"
    ).removesuffix("_milliseconds")
    assert failure.value.diagnostic.required == getattr(estimate, field)
    assert failure.value.diagnostic.site_count == 2


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
    assert derive_seed(42, "terrain", 3, "uplift") == 2417978552673304059


def test_seed_domains_and_items_are_separated() -> None:
    plan = SeedPlan(42)
    values = {
        plan.for_domain("terrain", 1),
        plan.for_domain("terrain", 2),
        plan.for_domain("hydrology", 1),
    }
    assert len(values) == 3
    assert plan.for_domain("terrain", 1) == plan.for_domain("terrain", 1)
