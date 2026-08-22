"""WG-LOCAL-003 natural sparse occupancy overlay evidence."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_maps import generate_local_maps, validate_local_map
from src.worldgen.local_occupancy import (
    NATURAL_OCCUPANCY_KINDS,
    local_occupancy_chunk_from_mapping,
    validate_occupancy_chunks,
)


@pytest.fixture(scope="module")
def generated_local_maps(phase4_world):
    return generate_local_maps(WorldView(phase4_world))


def test_natural_occupancy_is_canonical_provenanced_and_complete(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        records = tuple(
            record for chunk in local.occupancy_chunks for record in chunk.records
        )
        kinds = {record.kind for record in records}
        assert {"sealed_cave", "aquifer_water", "vegetation"} <= kinds
        assert ("mineral_deposit" in kinds) == bool(local.boundary.deposit_ids)
        assert kinds <= set(NATURAL_OCCUPANCY_KINDS)
        assert all(record.source_ids for record in records)
        assert tuple(
            (chunk.chunk_z, chunk.chunk_y, chunk.chunk_x)
            for chunk in local.occupancy_chunks
        ) == tuple(sorted(
            (chunk.chunk_z, chunk.chunk_y, chunk.chunk_x)
            for chunk in local.occupancy_chunks
        ))
        validate_local_map(local)


@pytest.mark.parametrize("mutation", ["hash", "record", "order", "missing"])
def test_natural_occupancy_rejects_corruption(
    generated_local_maps, mutation: str,
) -> None:
    local = generated_local_maps[0]
    chunks = list(local.occupancy_chunks)
    if mutation == "hash":
        chunks[0] = replace(chunks[0], sha256="0" * 64)
    elif mutation == "record":
        first = chunks[0]
        record = replace(first.records[0], voxel_indices=(99_999,))
        chunks[0] = replace(first, records=(record, *first.records[1:]))
    elif mutation == "order":
        chunks[0], chunks[-1] = chunks[-1], chunks[0]
    else:
        chunks.pop()
    with pytest.raises(ValueError, match="WG-LOCAL-OCCUPANCY"):
        validate_occupancy_chunks(
            local.width, local.height, local.z_levels, local.features, tuple(chunks)
        )


def test_natural_occupancy_reader_rejects_hash_and_shape_tampering(
    generated_local_maps,
) -> None:
    chunk = generated_local_maps[0].occupancy_chunks[0]
    payload = asdict(chunk)
    assert local_occupancy_chunk_from_mapping(payload) == chunk
    with pytest.raises(ValueError, match="OCCUPANCY-READ"):
        local_occupancy_chunk_from_mapping({**payload, "sha256": "f" * 64})
    with pytest.raises(ValueError, match="OCCUPANCY-READ"):
        local_occupancy_chunk_from_mapping({**payload, "invented": True})


def test_macro_river_and_coast_constraints_have_spatial_water_occupants(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        kinds = {feature.kind for feature in local.features}
        assert local.boundary is not None
        if local.boundary.coastline:
            assert "coast_water" in kinds
        if any(edge.river_edge_ids for edge in local.boundary.edges):
            assert "river_water" in kinds
