"""WG-LOCAL-003 constructed occupancy and containment evidence."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_construction import (
    construction_chunk_from_mapping,
    validate_construction_chunks,
)
from src.worldgen.local_maps import generate_local_maps, validate_local_map


@pytest.fixture(scope="module")
def generated_local_maps(phase4_world):
    return generate_local_maps(WorldView(phase4_world))


def test_construction_is_owned_cultural_contained_and_accessible(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        assert local.boundary is not None
        records = tuple(record for chunk in local.construction_chunks for record in chunk.records)
        kinds = {record.kind for record in records}
        assert {
            "parcel",
            "road",
            "wall",
            "supported_building",
            "workshop",
            "interior",
            "stockpile",
            "item",
        } <= kinds
        assert all(
            record.civilization_id == local.boundary.civilization_id
            and record.culture == local.boundary.culture
            and record.settlement_status == local.boundary.settlement_status
            and record.source_ids
            for record in records
        )
        validate_local_map(local)


@pytest.mark.parametrize("mutation", ["hash", "owner", "order", "missing"])
def test_construction_validator_rejects_corruption(
    generated_local_maps,
    mutation: str,
) -> None:
    local = generated_local_maps[0]
    assert local.boundary is not None
    chunks = list(local.construction_chunks)
    if mutation == "hash":
        chunks[0] = replace(chunks[0], sha256="0" * 64)
    elif mutation == "owner":
        first = chunks[0]
        record = replace(first.records[0], civilization_id="forged-owner")
        chunks[0] = replace(first, records=(record, *first.records[1:]))
    elif mutation == "order":
        chunks[0], chunks[-1] = chunks[-1], chunks[0]
    else:
        chunks.pop()
    with pytest.raises(ValueError, match="WG-LOCAL-CONSTRUCTION"):
        validate_construction_chunks(
            local.width,
            local.height,
            local.z_levels,
            local.features,
            local.boundary,
            tuple(chunks),
        )


def test_construction_reader_rejects_hash_and_shape_tampering(
    generated_local_maps,
) -> None:
    chunk = generated_local_maps[0].construction_chunks[0]
    payload = asdict(chunk)
    assert construction_chunk_from_mapping(payload) == chunk
    with pytest.raises(ValueError, match="CONSTRUCTION-READ"):
        construction_chunk_from_mapping({**payload, "sha256": "f" * 64})
    with pytest.raises(ValueError, match="CONSTRUCTION-READ"):
        construction_chunk_from_mapping({**payload, "invented": True})


def test_ruins_follow_present_settlement_status(generated_local_maps) -> None:
    for local in generated_local_maps:
        assert local.boundary is not None
        kinds = {feature.kind for feature in local.features}
        assert ("ruin" in kinds) == (local.boundary.settlement_status != "inhabited")
