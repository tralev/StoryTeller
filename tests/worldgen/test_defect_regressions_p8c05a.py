"""Target invariants that prevent the six archived prototype defects."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from src.domain.run_spec import WorldSpec
from src.world.views import WorldView
from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.local_maps import generate_local_maps
from src.worldgen.numeric import deterministic_map, identity, stable_id


def test_drainage_sink_regression_has_declared_termination(physical_world) -> None:
    terrain, hydrology, *_ = physical_world
    lake_cells = {cell for lake in hydrology.lakes for cell in lake.cells}
    for start in terrain.grid.indices():
        if not terrain.land.values[start]:
            continue
        cursor, seen = start, set()
        while hydrology.flow_to.values[cursor] >= 0:
            assert cursor not in seen, f"undeclared drainage cycle from {start}"
            seen.add(cursor)
            cursor = hydrology.flow_to.values[cursor]
        point = terrain.grid.coordinate(cursor)
        declared = (not terrain.land.values[cursor] or cursor in lake_cells
                    or point.x in (0, terrain.grid.width - 1)
                    or point.y in (0, terrain.grid.height - 1))
        assert declared, f"land cell {start} terminates at undeclared sink {cursor}"


def test_skipped_year_regression_preserves_exact_final_snapshot(phase4_world) -> None:
    repository = WorldArtifactRepository(phase4_world / "artifacts")
    index = repository.load_verified("simulation_index").payload
    snapshots = repository.load_verified("snapshots").payload
    assert index["present_year"] == 20
    assert snapshots[-1]["year"] == index["present_year"]
    assert [snapshot["year"] for snapshot in snapshots] == [0, 10, 20]


def test_order_dependence_regression_worker_counts_match() -> None:
    keys = tuple(reversed(range(64)))
    with ThreadPoolExecutor(max_workers=1) as one:
        first = deterministic_map(one, lambda key: stable_id("entity", 17, identity("key", key)), keys)
    with ThreadPoolExecutor(max_workers=8) as many:
        second = deterministic_map(many, lambda key: stable_id("entity", 17, identity("key", key)), keys)
    assert first == second
    assert [key for key, _ in first] == sorted(keys)


def test_incomplete_local_map_regression_covers_every_site(phase4_world) -> None:
    world = WorldView(phase4_world)
    maps = generate_local_maps(world)
    assert {local.site_id for local in maps} == {site.fact_id for site in world.sites()}
    assert len(maps) == len(world.sites())


def test_mutable_override_regression_rejects_committed_spec_changes() -> None:
    spec = WorldSpec()
    with pytest.raises(FrozenInstanceError):
        spec.width = 32


def test_inconsistent_id_regression_has_literal_stable_vector() -> None:
    expected = stable_id("region", 42, identity("cell", 7))
    assert expected == stable_id("region", 42, identity("cell", 7))
    assert expected == "region_5d4c79924b65d3b4e18e998eb614ba01"
