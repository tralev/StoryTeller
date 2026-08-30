"""WG-LOCAL-004 macro/micro contradiction gate evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_maps import LocalFeature, generate_local_maps
from src.worldgen.local_occupancy import generate_occupancy_chunks
from src.worldgen.local_reconciliation import validate_local_reconciliation
from src.worldgen.local_summary import derive_local_macro_summary


@pytest.fixture(scope="module")
def world_and_maps(phase4_world):
    world = WorldView(phase4_world)
    return world, generate_local_maps(world)


def test_every_generated_local_map_reconciles_with_macro_authority(world_and_maps) -> None:
    world, maps = world_and_maps
    for local in maps:
        validate_local_reconciliation(world, local)


def test_reconciliation_rejects_forged_owner_and_present_state(world_and_maps) -> None:
    world, maps = world_and_maps
    local = maps[0]
    assert local.boundary is not None
    forged = replace(
        local,
        boundary=replace(
            local.boundary, civilization_id="forged-owner", settlement_population=999_999
        ),
    )
    with pytest.raises(ValueError, match="RECONCILE-BOUNDARY"):
        validate_local_reconciliation(world, forged)


def test_reconciliation_rejects_internally_valid_invented_deposit(world_and_maps) -> None:
    world, maps = world_and_maps
    local = maps[0]
    feature = LocalFeature(
        "forged-deposit",
        "mineral_deposit",
        ((1, 1, 1),),
        (world.artifact_ids["resources"], "invented-deposit"),
    )
    features = (*local.features, feature)
    forged_without_summary = replace(
        local,
        features=features,
        occupancy_chunks=generate_occupancy_chunks(
            local.width, local.height, local.z_levels, features
        ),
    )
    forged = replace(
        forged_without_summary,
        macro_summary=derive_local_macro_summary(forged_without_summary),
    )
    with pytest.raises(ValueError, match="RECONCILE-RESOURCE"):
        validate_local_reconciliation(world, forged)


def test_reconciliation_rejects_erased_coast_or_route_constraint(world_and_maps) -> None:
    world, maps = world_and_maps
    constrained = next(
        (
            item
            for item in maps
            if item.boundary
            and (item.boundary.coastline or any(edge.route_ids for edge in item.boundary.edges))
        ),
        None,
    )
    if constrained is None:
        pytest.skip("fixture has no coast or macro-route site")
    assert constrained.boundary is not None
    erased_kind = "coast_water" if constrained.boundary.coastline else "route_connection"
    features = tuple(item for item in constrained.features if item.kind != erased_kind)
    forged = replace(
        constrained,
        features=features,
        occupancy_chunks=generate_occupancy_chunks(
            constrained.width, constrained.height, constrained.z_levels, features
        ),
    )
    with pytest.raises(ValueError, match="WG-LOCAL"):
        validate_local_reconciliation(world, forged)
