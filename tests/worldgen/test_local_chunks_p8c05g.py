"""WG-LOCAL-003 chunked surface and strata foundation evidence."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_chunks import (
    LOCAL_CHUNK_DEPTH,
    LOCAL_CHUNK_HEIGHT,
    LOCAL_CHUNK_WIDTH,
    generate_material_chunks,
    local_voxel_chunk_from_mapping,
    validate_material_chunks,
)
from src.worldgen.local_maps import generate_local_maps, validate_local_map


@pytest.fixture(scope="module")
def generated_local_maps(phase4_world):
    return generate_local_maps(WorldView(phase4_world))


def test_material_chunks_cover_every_voxel_once_in_canonical_order(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        expected_count = (
            ((local.width + LOCAL_CHUNK_WIDTH - 1) // LOCAL_CHUNK_WIDTH)
            * ((local.height + LOCAL_CHUNK_HEIGHT - 1) // LOCAL_CHUNK_HEIGHT)
            * ((local.z_levels + LOCAL_CHUNK_DEPTH - 1) // LOCAL_CHUNK_DEPTH)
        )
        assert len(local.chunks) == expected_count
        assert tuple(
            (chunk.chunk_z, chunk.chunk_y, chunk.chunk_x) for chunk in local.chunks
        ) == tuple(sorted(
            (chunk.chunk_z, chunk.chunk_y, chunk.chunk_x) for chunk in local.chunks
        ))
        assert sum(
            chunk.width * chunk.height * chunk.depth for chunk in local.chunks
        ) == local.width * local.height * local.z_levels
        validate_local_map(local)


def test_material_chunks_encode_surface_and_strata_without_empty_space_forgery(
    generated_local_maps,
) -> None:
    local = generated_local_maps[0]
    assert local.chunks == generate_material_chunks(
        local.width, local.height, local.z_levels, local.surface_height, local.strata
    )
    first = local.chunks[0]
    assert all(material >= 0 for material in first.materials)
    assert any(material > 0 for material in first.materials)


@pytest.mark.parametrize("mutation", ["hash", "material", "order", "missing"])
def test_material_chunk_validator_rejects_corruption(
    generated_local_maps, mutation: str,
) -> None:
    local = generated_local_maps[0]
    chunks = list(local.chunks)
    if mutation == "hash":
        chunks[0] = replace(chunks[0], sha256="0" * 64)
    elif mutation == "material":
        chunks[0] = replace(chunks[0], materials=(999, *chunks[0].materials[1:]))
    elif mutation == "order":
        chunks[0], chunks[1] = chunks[1], chunks[0]
    else:
        chunks.pop()
    with pytest.raises(ValueError, match="WG-LOCAL-CHUNK"):
        validate_material_chunks(
            local.width, local.height, local.z_levels, local.surface_height,
            local.strata, tuple(chunks),
        )


def test_material_chunk_reader_is_strict_and_hash_verified(generated_local_maps) -> None:
    chunk = generated_local_maps[0].chunks[0]
    payload = asdict(chunk)
    assert local_voxel_chunk_from_mapping(payload) == chunk
    with pytest.raises(ValueError, match="CHUNK-READ"):
        local_voxel_chunk_from_mapping({**payload, "sha256": "f" * 64})
    with pytest.raises(ValueError, match="CHUNK-READ"):
        local_voxel_chunk_from_mapping({**payload, "unexpected": 1})
