from __future__ import annotations

import pytest

from src.domain.run_spec import WorldSpec
from src.worldgen.artifacts import (
    DependencyGraph, GridChunk, WorldArtifact, WorldArtifactRepository, canonical_json,
)
from src.worldgen.stages import WorldStageRunner
from src.worldgen.generator import generate_world
from src.worldgen.models import Site


def test_canonical_json_and_envelope_are_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    left = WorldArtifact.build("terrain", {"b": 2, "a": 1}, producer_fingerprint="v1")
    right = WorldArtifact.build("terrain", {"a": 1, "b": 2}, producer_fingerprint="v1")
    assert left == right


def test_dependency_closure_and_cycle_detection() -> None:
    graph = DependencyGraph({"terrain": (), "climate": ("terrain",), "biomes": ("climate",)})
    assert graph.invalidation_closure({"terrain"}) == {"terrain", "climate", "biomes"}
    with pytest.raises(ValueError, match="cycle"):
        DependencyGraph({"a": ("b",), "b": ("a",)})


def test_atomic_world_repository_detects_tampering(tmp_path) -> None:
    repository = WorldArtifactRepository(tmp_path)
    artifact = WorldArtifact.build("terrain", {"cells": [1, 2]}, producer_fingerprint="v1")
    path = repository.put(artifact)
    assert repository.load_verified("terrain").artifact_id == artifact.artifact_id
    path.write_text(path.read_text().replace("[1,2]", "[2,1]"))
    with pytest.raises(ValueError, match="WG-HASH"):
        repository.load_verified("terrain")


def test_grid_chunk_round_trip_is_canonical() -> None:
    chunk = GridChunk("elevation", 2, 3, 2, 2, (-10, 0, 20, 30))
    assert GridChunk.decode(chunk.encode()) == chunk


def test_world_stage_checkpoints_skip_matching_work() -> None:
    class Stage:
        id = "terrain"
        requires: tuple[str, ...] = ()
        max_retries = 0
        calls = 0

        def generate(self, spec, dependencies):
            self.calls += 1
            return {"width": spec.width}

        def validate(self, value, spec) -> None:
            assert value["width"] == spec.width

    stage = Stage()
    checkpoints = {}
    runner = WorldStageRunner((stage,), "v1", checkpoints=checkpoints)
    runner.run(WorldSpec(width=32, height=32))
    runner.run(WorldSpec(width=32, height=32))
    assert stage.calls == 1


def test_world_resource_preflight() -> None:
    spec = WorldSpec(width=32, height=32)
    spec.preflight(max_ram_bytes=spec.estimated_working_set_bytes())
    with pytest.raises(ValueError, match="exceeding RAM budget"):
        spec.preflight(max_ram_bytes=1)


def test_legacy_characterization_has_no_unassigned_land_cells() -> None:
    from src.worldgen.biomes import classify_biomes
    from src.worldgen.climate import generate_climate
    from src.worldgen.regions import segment_regions
    from src.worldgen.terrain import generate_terrain
    grid = generate_terrain(32, 32, 42)
    generate_climate(grid, 42)
    classify_biomes(grid)
    segment_regions(grid, 42)
    for row in grid:
        for cell in row:
            if cell.elevation > 0 and cell.biome:
                assert cell.region_id


def test_expansion_names_use_owner_race_without_population_duplication() -> None:
    with pytest.deprecated_call():
        snapshot = generate_world(17, width=32, height=32, max_civs=3, history_years=20)
    sites_by_civ: dict[str, list[Site]] = {}
    for site in snapshot.sites:
        sites_by_civ.setdefault(site.civilization_id, []).append(site)
    for civilization in snapshot.civilizations:
        owned_sites = sites_by_civ.get(civilization.id, [])
        assert sum(site.population for site in owned_sites) <= civilization.population
        assert all(site.name.startswith(civilization.race.capitalize() + "-") for site in owned_sites)
