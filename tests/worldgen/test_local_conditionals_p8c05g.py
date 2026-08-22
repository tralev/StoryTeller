"""WG-LOCAL-003 forcing matrix for every conditional feature family."""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_boundaries import derive_local_boundaries
from src.worldgen.local_conditionals import (
    ConditionalFeatureSpec,
    plan_local_conditionals,
    synthesize_conditional_features,
)
from src.worldgen.local_construction import (
    generate_construction_chunks,
    validate_construction_chunks,
)
from src.worldgen.local_maps import generate_local_maps
from src.worldgen.local_occupancy import (
    generate_occupancy_chunks,
    validate_occupancy_chunks,
)


@pytest.fixture(scope="module")
def base_boundary(phase4_world):
    return derive_local_boundaries(WorldView(phase4_world))[0]


def test_forced_coast_river_route_bridge_and_deposit_plan(base_boundary) -> None:
    cleared = tuple(
        replace(edge, river_edge_ids=(), route_ids=()) for edge in base_boundary.edges
    )
    east = replace(
        cleared[1],
        river_edge_ids=("forced-river",),
        route_ids=("forced-route",),
    )
    forced = replace(
        base_boundary,
        coastline=True,
        deposit_ids=("forced-deposit",),
        edges=(cleared[0], east, *cleared[2:]),
    )
    plan = plan_local_conditionals(forced, "east_west")
    assert plan.coastline
    assert plan.river_directions == ("east",)
    assert plan.route_directions == ("east",)
    assert plan.bridge_directions == ("east",)
    assert plan.deposit_ids == ("forced-deposit",)


def test_bridge_requires_river_route_and_aligned_street(base_boundary) -> None:
    cleared = tuple(
        replace(edge, river_edge_ids=(), route_ids=()) for edge in base_boundary.edges
    )
    east = replace(
        cleared[1],
        river_edge_ids=("forced-river",), route_ids=("forced-route",),
    )
    forced = replace(
        base_boundary, edges=(cleared[0], east, *cleared[2:])
    )
    assert plan_local_conditionals(forced, "east_west").bridge_directions == ("east",)
    assert plan_local_conditionals(forced, "north_south").bridge_directions == ()
    no_route = replace(
        forced, edges=(forced.edges[0], replace(east, route_ids=()), *forced.edges[2:])
    )
    assert plan_local_conditionals(no_route, "east_west").bridge_directions == ()


@pytest.mark.parametrize("status", ["inhabited", "abandoned", "ruined"])
def test_each_settlement_form_is_forced(base_boundary, status: str) -> None:
    plan = plan_local_conditionals(
        replace(base_boundary, settlement_status=status), "east_west"
    )
    assert plan.settlement_form == status


def test_generated_bridges_share_river_column_and_street_voxel(phase4_world) -> None:
    maps = generate_local_maps(WorldView(phase4_world))
    for local in maps:
        bridges = {
            cell for feature in local.features if feature.kind == "bridge"
            for cell in feature.cells
        }
        if not bridges:
            continue
        roads = {
            cell for feature in local.features if feature.kind == "road"
            for cell in feature.cells
        }
        rivers = {
            (x, y) for feature in local.features if feature.kind == "river_water"
            for x, y, _ in feature.cells
        }
        assert bridges <= roads
        assert {(x, y) for x, y, _ in bridges} <= rivers


def test_forced_plan_synthesizes_exact_hashed_feature_chunks(base_boundary) -> None:
    cleared = tuple(
        replace(edge, river_edge_ids=(), route_ids=()) for edge in base_boundary.edges
    )
    east = replace(
        cleared[1], river_edge_ids=("forced-river",), route_ids=("forced-route",),
    )
    boundary = replace(
        base_boundary, coastline=True, deposit_ids=("forced-deposit",),
        settlement_status="ruined", edges=(cleared[0], east, *cleared[2:]),
    )
    artifacts = {
        "hydrology": "src-hydrology", "routes": "src-routes",
        "resources": "src-resources", "settlements": "src-settlements",
        "civilizations": "src-civilizations",
    }
    width, height, z_levels = 16, 16, 8
    center, building = (8, 8, 4), ((8, 8, 4), (9, 8, 4))
    surface = (4,) * (width * height)
    cave = tuple((x, 6, 2) for x in range(4, 12))
    anchors = ((8, 0, 4), (15, 8, 4), (8, 15, 4), (0, 8, 4))
    plan = plan_local_conditionals(boundary, "east_west")
    forced = synthesize_conditional_features(
        boundary, plan, width, height, z_levels, surface, center, cave, building,
        anchors, artifacts,
    )
    assert {item.kind for item in forced} == {
        "coast_water", "river_water", "route_connection", "bridge",
        "mineral_deposit", "ruin",
    }
    river = next(item for item in forced if item.kind == "river_water")
    bridge = next(item for item in forced if item.kind == "bridge")
    assert river.cells[0][:2] == (15, 8)
    assert (15, 8) in {(x, y) for x, y, _ in bridge.cells}
    assert river.source_ids == ("src-hydrology", "forced-river")
    assert next(item for item in forced if item.kind == "mineral_deposit").source_ids == (
        "src-resources", "forced-deposit",
    )
    natural_chunks = generate_occupancy_chunks(width, height, z_levels, forced)
    validate_occupancy_chunks(width, height, z_levels, forced, natural_chunks)

    road = tuple((x, 8, 4) for x in range(width))
    parcel = tuple((x, y, 4) for x in range(6, 11) for y in range(6, 11))
    base = (
        ConditionalFeatureSpec("road", "road", road, ("src-routes",)),
        ConditionalFeatureSpec("parcel", "parcel", parcel, ("src-settlements",)),
        ConditionalFeatureSpec("building", "supported_building", building,
                               ("src-settlements",)),
        ConditionalFeatureSpec("wall", "wall", building, ("src-settlements",)),
        ConditionalFeatureSpec("workshop", "workshop", (building[0],),
                               ("src-settlements",)),
        ConditionalFeatureSpec("stockpile", "stockpile", (building[1],),
                               ("src-settlements",)),
        ConditionalFeatureSpec("interior", "interior", building,
                               ("src-settlements",)),
        ConditionalFeatureSpec("item", "item", (building[1],), ("src-settlements",)),
    )
    all_features = (*base, *forced)
    construction = generate_construction_chunks(
        width, height, z_levels, all_features, boundary
    )
    validate_construction_chunks(
        width, height, z_levels, all_features, boundary, construction
    )
    assert all(len(chunk.sha256) == 64 for chunk in (*natural_chunks, *construction))
