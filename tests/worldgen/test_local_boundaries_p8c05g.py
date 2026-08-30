"""WG-LOCAL-001 immutable macro-boundary bundle evidence."""

from dataclasses import FrozenInstanceError, asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_boundaries import (
    CARDINAL_EDGES,
    LOCAL_BOUNDARY_SOURCE_KINDS,
    derive_local_boundaries,
    local_boundary_from_mapping,
    validate_local_boundaries,
)


def test_every_site_has_a_typed_complete_immutable_boundary(phase4_world) -> None:
    world = WorldView(phase4_world)
    boundaries = derive_local_boundaries(world)

    assert tuple(item.site_id for item in boundaries) == tuple(
        sorted(item.fact_id for item in world.sites())
    )
    assert all(
        item.region_id and item.settlement_id and item.civilization_id for item in boundaries
    )
    assert all(
        item.source_artifact_ids
        == tuple(world.artifact_ids[kind] for kind in LOCAL_BOUNDARY_SOURCE_KINDS)
        for item in boundaries
    )
    assert derive_local_boundaries(world) == boundaries
    with pytest.raises(FrozenInstanceError):
        boundaries[0].macro_cell = -1


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("elevation_mm", -99_999_999),
        ("region_id", "forged-region"),
        ("civilization_id", "forged-owner"),
        ("route_ids", ("forged-route",)),
    ),
)
def test_boundary_validator_rejects_forged_macro_facts(
    phase4_world,
    field: str,
    value: object,
) -> None:
    world = WorldView(phase4_world)
    boundaries = derive_local_boundaries(world)
    forged = (replace(boundaries[0], **{field: value}), *boundaries[1:])
    with pytest.raises(ValueError, match="WG-LOCAL-BOUNDARY"):
        validate_local_boundaries(world, forged)


def test_boundary_captures_all_required_macro_domains(phase4_world) -> None:
    world = WorldView(phase4_world)
    boundary = derive_local_boundaries(world)[0]

    assert isinstance(boundary.elevation_mm, int)
    assert isinstance(boundary.rock_class_id, int)
    assert isinstance(boundary.strata_id, int)
    assert isinstance(boundary.coastline, bool)
    assert isinstance(boundary.aquifer_capacity_mm, int)
    assert isinstance(boundary.annual_temperature_millic, int)
    assert isinstance(boundary.annual_precipitation_mm, int)
    assert isinstance(boundary.renewable_yield, int)
    assert isinstance(boundary.inventory, tuple)
    assert boundary.settlement_status in {"inhabited", "abandoned", "ruined"}


def test_typed_boundary_reader_rejects_missing_extra_and_wrong_type(phase4_world) -> None:
    boundary = derive_local_boundaries(WorldView(phase4_world))[0]
    payload = asdict(boundary)
    assert local_boundary_from_mapping(payload) == boundary

    missing = dict(payload)
    missing.pop("elevation_mm")
    with pytest.raises(ValueError, match="BOUNDARY-READ"):
        local_boundary_from_mapping(missing)
    extra = {**payload, "invented": True}
    with pytest.raises(ValueError, match="BOUNDARY-READ"):
        local_boundary_from_mapping(extra)
    wrong = {**payload, "macro_cell": "0"}
    with pytest.raises(ValueError, match="BOUNDARY-READ"):
        local_boundary_from_mapping(wrong)


def test_cardinal_edges_equal_authoritative_neighbor_fields(phase4_world) -> None:
    world = WorldView(phase4_world)
    terrain = world.terrain_elevation()
    hydrology = world.hydrology().hydrology
    climate = world.climate().climate
    resources = world.resources().resources

    for boundary in derive_local_boundaries(world):
        point = terrain.spec.coordinate(boundary.macro_cell)
        assert tuple(edge.direction for edge in boundary.edges) == tuple(
            direction for direction, _, _ in CARDINAL_EDGES
        )
        for edge, (_, dx, dy) in zip(boundary.edges, CARDINAL_EDGES):
            nx, ny = point.x + dx, point.y + dy
            expected_neighbor = (
                terrain.spec.index(nx, ny)
                if 0 <= nx < terrain.spec.width and 0 <= ny < terrain.spec.height
                else None
            )
            assert edge.neighbor_cell == expected_neighbor
            assert edge.elevation_mm == terrain.values[boundary.macro_cell]
            if expected_neighbor is None:
                assert edge.neighbor_elevation_mm is None
                assert edge.neighbor_coastline is None
            else:
                assert edge.neighbor_elevation_mm == terrain.values[expected_neighbor]
                assert edge.neighbor_coastline == bool(
                    hydrology.coastline.values[expected_neighbor]
                )
                assert (
                    edge.annual_temperature_millic
                    == (climate.annual_temperature_millic.values[expected_neighbor])
                )
                assert edge.renewable_yield == resources.renewable_yield.values[expected_neighbor]


def test_boundary_validator_rejects_forged_cardinal_edge(phase4_world) -> None:
    world = WorldView(phase4_world)
    boundaries = derive_local_boundaries(world)
    forged_edge = replace(
        boundaries[0].edges[0],
        neighbor_elevation_mm=-999_999,
        route_ids=("forged-route",),
    )
    forged_boundary = replace(boundaries[0], edges=(forged_edge, *boundaries[0].edges[1:]))
    with pytest.raises(ValueError, match="WG-LOCAL-BOUNDARY"):
        validate_local_boundaries(world, (forged_boundary, *boundaries[1:]))
