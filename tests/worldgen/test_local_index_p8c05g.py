"""WG-LOCAL-008 complete retained local-world index evidence."""
from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.artifacts import canonical_json
from src.worldgen.local_index import (
    build_local_world_index,
    local_world_index_from_mapping,
    validate_local_world_index,
    validate_narrative_independent_coverage,
)
from src.worldgen.local_maps import generate_local_maps


def test_index_covers_every_registered_site_and_required_chunk(phase4_world) -> None:
    world = WorldView(phase4_world)
    local_maps = generate_local_maps(world)
    index = build_local_world_index(local_maps)
    validate_local_world_index(
        index, local_maps,
        expected_site_ids=tuple(site.fact_id for site in world.sites()),
    )
    assert index.sites == tuple(sorted(site.fact_id for site in world.sites()))
    local_by_site = {local.site_id: local for local in local_maps}
    for entry in index.entries:
        local = local_by_site[entry.site_id]
        assert entry.material_chunk_hashes == tuple(chunk.sha256 for chunk in local.chunks)
        assert entry.occupancy_chunk_hashes == tuple(
            chunk.sha256 for chunk in local.occupancy_chunks
        )
        assert entry.construction_chunk_hashes == tuple(
            chunk.sha256 for chunk in local.construction_chunks
        )


def test_index_rejects_missing_site_and_tampered_map_identity(phase4_world) -> None:
    world = WorldView(phase4_world)
    local_maps = generate_local_maps(world)
    index = build_local_world_index(local_maps)
    with pytest.raises(ValueError, match="INDEX-COVERAGE"):
        validate_local_world_index(
            replace(index, entries=index.entries[:-1], sites=index.sites[:-1]),
            local_maps[:-1], expected_site_ids=index.sites,
        )
    forged_entry = replace(index.entries[0], local_map_sha256="0" * 64)
    with pytest.raises(ValueError, match="INDEX-CONTENT"):
        validate_local_world_index(
            replace(index, entries=(forged_entry, *index.entries[1:])), local_maps,
        )


def test_persisted_index_is_strict_and_bound_to_project_bytes(phase5_project) -> None:
    world_path, _, project = phase5_project
    payload = json.loads((project / "local_index.json").read_text())
    index = local_world_index_from_mapping(payload)
    local_maps = generate_local_maps(WorldView(world_path))
    validate_local_world_index(
        index, local_maps,
        expected_site_ids=tuple(site.fact_id for site in WorldView(world_path).sites()),
        local_root=project / "local_maps",
    )
    assert local_world_index_from_mapping(asdict(index)) == index
    with pytest.raises(ValueError, match="INDEX-READ"):
        local_world_index_from_mapping({**payload, "invented": True})


def test_disjoint_narrative_selections_cannot_filter_or_change_local_bytes(
    phase4_world,
) -> None:
    world = WorldView(phase4_world)
    first_maps = generate_local_maps(world)
    second_maps = generate_local_maps(world)
    first_index = build_local_world_index(first_maps)
    second_index = build_local_world_index(second_maps)
    site_ids = first_index.sites
    midpoint = len(site_ids) // 2
    validate_narrative_independent_coverage(first_index, site_ids, site_ids[:midpoint])
    validate_narrative_independent_coverage(second_index, site_ids, site_ids[midpoint:])
    assert canonical_json(first_index) == canonical_json(second_index)
    assert tuple(canonical_json(item) for item in sorted(
        first_maps, key=lambda item: item.site_id,
    )) == tuple(canonical_json(item) for item in sorted(
        second_maps, key=lambda item: item.site_id,
    ))


def test_production_plan_does_not_depend_on_narrative_for_local_generation() -> None:
    from src.pipeline.plan import PipelinePlan

    step = next(item for item in PipelinePlan.production_v2() if item.id == "local_maps_v2")
    assert step.requires == ("world",)


def test_gm_and_package_consume_independent_local_root(tmp_path, phase5_project) -> None:
    from src.narrative.pipeline import (
        generate_narrative_index,
        generate_narrative_local_maps,
    )
    from src.storage.package_v2 import validate_v2_package
    from src.storage.project_v2 import package_project_v2

    world, bible, narrative = phase5_project
    local_root = tmp_path / "local-worlds"
    generate_narrative_local_maps(world, local_root)
    generate_narrative_index(
        world, bible / "bible.json", narrative, local_root=local_root,
    )
    package = package_project_v2(
        world, bible, narrative, tmp_path / "isolated.story",
        title="Isolation", seed=17, local_root=local_root,
    )
    assert validate_v2_package(package).accepted
