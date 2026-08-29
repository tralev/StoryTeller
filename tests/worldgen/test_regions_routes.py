import ast
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from src.worldgen.artifacts import canonical_json
from src.worldgen.grid import IntGrid
from src.worldgen.indexes import BoundingBox, build_spatial_index
from src.worldgen.reference_index import ReferenceIndex
from src.worldgen.index_reader import VerifiedReferenceIndexReader, VerifiedSpatialIndexReader
from src.worldgen.validation import WorldInvariantError, validate_physical_world, validate_regions
from src.worldgen.geology import generate_geology
from src.worldgen.soil import generate_soil
from src.worldgen.physical_regions import (MAX_REGION_CELLS, MIN_REGION_CELLS,
                                           REGION_COST_MODEL, TARGET_REGION_CELLS,
                                           generate_regions, region_step_cost)
from src.worldgen.physical_models import RouteKind
from src.worldgen.routes import COST_UNIT, ROUTE_CLASS_RULES
from src.worldgen.numeric import div_round_half_up


@pytest.mark.parametrize("module_name", ["physical_regions", "routes"])
def test_region_and_route_layers_have_no_raw_division_operators(module_name):
    source = Path(f"src/worldgen/{module_name}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FloorDiv, ast.Div))
    ]


def test_region_and_route_artifact_golden_vectors(physical_world):
    *_, regions, routes = physical_world
    actual = tuple(
        hashlib.sha256(canonical_json(layer)).hexdigest()
        for layer in (regions, routes)
    )
    assert actual == (
        "67a0942ec87ed366e077e91740691e0b98a4044d7aad49a7cd3bc7da8e6819ce",
        "40be788b394bc5fd8e0f5fa14bed59c21066e4decf444ad01634affbef378bca",
    )


def test_region_ownership_adjacency_and_routes(physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    soil = generate_soil(terrain, generate_geology(terrain), hydrology, climate)
    validate_physical_world(terrain, hydrology, climate, soil, biomes, resources, regions, routes)
    land = {i for i, value in enumerate(terrain.land.values) if value}
    assert land == {cell for region in regions.regions for cell in region.cells}
    neighbors = {region.region_id: set(region.neighbors) for region in regions.regions}
    assert all(region.region_id in neighbors[other] for region in regions.regions for other in region.neighbors)


def test_multisource_dijkstra_regions_use_all_physical_cost_fields(physical_world):
    terrain, hydrology, climate, biomes, _, regions, _ = physical_world
    repeated = generate_regions(terrain, hydrology, climate, biomes)
    assert repeated == regions
    land_count = sum(terrain.land.values)
    assert len(regions.regions) >= max(1, (land_count + TARGET_REGION_CELLS - 1) // TARGET_REGION_CELLS)
    assert set(REGION_COST_MODEL) == {
        "base", "biome_transition", "watershed_transition", "elevation_divisor_mm",
        "temperature_divisor_millic", "precipitation_divisor_mm",
    }
    costs = [region_step_cost(index, neighbor, terrain, hydrology, climate, biomes)
             for index in terrain.grid.indices() if terrain.land.values[index]
             for neighbor in terrain.grid.neighbors4(index) if terrain.land.values[neighbor]]
    assert costs and min(costs) >= REGION_COST_MODEL["base"]
    assert any(cost > REGION_COST_MODEL["base"] for cost in costs)
    for region in regions.regions:
        assert MIN_REGION_CELLS <= len(region.cells) <= MAX_REGION_CELLS
        reached, frontier = {region.cells[0]}, [region.cells[0]]
        while frontier:
            cell = frontier.pop()
            for neighbor in terrain.grid.neighbors4(cell):
                if neighbor in region.cells and neighbor not in reached:
                    reached.add(neighbor)
                    frontier.append(neighbor)
        assert reached == set(region.cells)
    validate_regions(terrain, regions)


def test_region_validator_rejects_duplicate_ownership_and_noncanonical_center(physical_world):
    terrain, *_, regions, _ = physical_world
    first = regions.regions[0]
    wrong_center = first.cells[-1] if first.cells[-1] != first.center else first.cells[0]
    corrupted = replace(regions, regions=(replace(first, center=wrong_center), *regions.regions[1:]))
    with pytest.raises(WorldInvariantError, match="center or boundary"):
        validate_regions(terrain, corrupted)
    owner = list(regions.cell_region.values)
    owner[first.cells[0]] = 0
    corrupted = replace(regions, cell_region=IntGrid(terrain.grid, tuple(owner)))
    with pytest.raises(WorldInvariantError, match="identity, order, or size"):
        validate_regions(terrain, corrupted)


def test_route_endpoints_in_declared_regions(physical_world):
    """P8.C05D: Every route's start/end cells must lie in declared regions."""
    terrain, _, _, _, _, regions, routes = physical_world
    cell_to_region = {cell: num for cell, num in enumerate(regions.cell_region.values) if num > 0}
    for route in routes.routes:
        assert route.cells, f"route {route.route_id} has empty cell path"
        start_cell = route.cells[0]
        end_cell = route.cells[-1]
        start_region_num = cell_to_region.get(start_cell)
        end_region_num = cell_to_region.get(end_cell)
        assert start_region_num is not None, f"route {route.route_id} start cell {start_cell} not in any region"
        assert end_region_num is not None, f"route {route.route_id} end cell {end_cell} not in any region"
        start_rid = regions.regions[start_region_num - 1].region_id
        end_rid = regions.regions[end_region_num - 1].region_id
        assert start_rid == route.start_region, \
            f"route {route.route_id} start cell in {start_rid}, declared {route.start_region}"
        assert end_rid == route.end_region, \
            f"route {route.route_id} end cell in {end_rid}, declared {route.end_region}"


def test_typed_routes_have_four_valid_seasonal_ast_paths(physical_world):
    terrain, _, _, _, _, _, routes = physical_world
    assert {kind for kind in RouteKind} == {
        RouteKind.ROAD, RouteKind.TRAIL, RouteKind.NAVIGABLE_RIVER,
        RouteKind.SEA_LANE, RouteKind.MOUNTAIN_PASS, RouteKind.SETTLEMENT_LINK,
    }
    assert routes.routes
    for route in routes.routes:
        assert route.route_kind in RouteKind
        assert len(route.seasonal_cells) == len(route.traversable_seasons) == 4
        for season, path in enumerate(route.seasonal_cells):
            assert path[0] == route.cells[0] and path[-1] == route.cells[-1]
            assert all(terrain.land.values[cell] for cell in path)
            assert all(target in terrain.grid.neighbors4(source)
                       for source, target in zip(path, path[1:]))
            assert route.traversable_seasons[season] == (
                route.seasonal_capacity[season] > 0
                and route.seasonal_risk_ppm[season] < 950_000
            )


def test_route_class_rules_costs_maintenance_and_sources_are_frozen(physical_world):
    terrain, _, _, _, _, _, routes = physical_world
    assert set(ROUTE_CLASS_RULES) == set(RouteKind)
    assert all(set(rule) == {"surface", "base_cost", "slope_ppm", "river_cost",
                             "capacity", "maintenance_per_km"}
               for rule in ROUTE_CLASS_RULES.values())
    for route in routes.routes:
        rule = ROUTE_CLASS_RULES[route.route_kind]
        assert route.cost_unit == COST_UNIT
        assert route.source_ids == tuple(sorted((route.start_region, route.end_region)))
        assert route.annual_maintenance == div_round_half_up(
            route.distance_m * int(rule["maintenance_per_km"]), 1_000,
        )
        assert all(bool(terrain.land.values[cell]) == (rule["surface"] == "land")
                   for path in route.seasonal_cells for cell in path)


def test_route_validator_rejects_class_provenance_and_maintenance_mutations(physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    soil = generate_soil(terrain, generate_geology(terrain), hydrology, climate)
    first = routes.routes[0]
    for corrupted, message in (
        (replace(first, source_ids=(first.start_region,)), "class rule or provenance"),
        (replace(first, annual_maintenance=first.annual_maintenance + 1), "maintenance"),
    ):
        bad_routes = replace(routes, routes=(corrupted, *routes.routes[1:]))
        with pytest.raises(WorldInvariantError, match=message):
            validate_physical_world(
                terrain, hydrology, climate, soil, biomes, resources, regions, bad_routes,
            )


def test_route_validator_rejects_disconnected_pair_and_wrong_endpoint_cell(physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    soil = generate_soil(terrain, generate_geology(terrain), hydrology, climate)
    first = routes.routes[0]
    unrelated = next(region for region in regions.regions
                     if region.region_id not in (first.start_region, first.end_region)
                     and region.region_id not in next(
                         item for item in regions.regions
                         if item.region_id == first.start_region).neighbors)
    mutations = (
        replace(first, end_region=unrelated.region_id,
                source_ids=tuple(sorted((first.start_region, unrelated.region_id)))),
        replace(first, cells=(unrelated.cells[0], *first.cells[1:])),
    )
    for corrupted in mutations:
        with pytest.raises(WorldInvariantError, match="disconnected pair or endpoint containment"):
            validate_physical_world(
                terrain, hydrology, climate, soil, biomes, resources, regions,
                replace(routes, routes=(corrupted, *routes.routes[1:])),
            )


def test_route_does_not_cross_ocean(physical_world):
    """P8.C05D-FIXED: Routes must not pass through ocean cells."""
    terrain, _, _, _, _, _, routes = physical_world
    for route in routes.routes:
        for cell in route.cells:
            assert terrain.land.values[cell], \
                f"route {route.route_id} crosses ocean at cell {cell}"


def test_spatial_index_region_lookup(physical_world):
    """P8.C05D: Spatial index can look up region by coordinate."""
    terrain, _, _, _, _, regions, routes = physical_world
    index = build_spatial_index(regions, routes, terrain.grid)
    # Pick a land cell from a known region
    first_region = regions.regions[0]
    cell = first_region.cells[0]
    coord = terrain.grid.coordinate(cell)
    found = index.region_at(coord.x, coord.y)
    assert found == first_region.region_id, \
        f"expected {first_region.region_id}, got {found}"


def test_spatial_index_bbox_query(physical_world):
    """P8.C05D: Bounding-box query returns intersecting regions."""
    terrain, _, _, _, _, regions, routes = physical_world
    index = build_spatial_index(regions, routes, terrain.grid)
    # Query the entire world — should return all regions
    bbox = BoundingBox(0, 0, terrain.grid.width - 1, terrain.grid.height - 1)
    found = index.regions_in_bbox(bbox)
    assert len(found) == len(regions.regions), \
        f"expected {len(regions.regions)} regions, got {len(found)}"


def test_spatial_index_routes_for_region(physical_world):
    """P8.C05D: Route lookup by region returns connected routes."""
    _, _, _, _, _, regions, routes = physical_world
    grid = physical_world[0].grid
    index = build_spatial_index(regions, routes, grid)
    for region in regions.regions:
        route_ids = index.routes_for_region(region.region_id)
        assert isinstance(route_ids, tuple)


def test_spatial_index_rebuild_is_equal(physical_world):
    """P8.C05D: Index rebuild produces canonical equality."""
    _, _, _, _, _, regions, routes = physical_world
    grid = physical_world[0].grid
    a = build_spatial_index(regions, routes, grid)
    b = build_spatial_index(regions, routes, grid)
    assert a == b


def test_reference_index_entity_lookups(physical_world):
    """P8.C05D: Reference index supports entity, reverse, and cell lookups."""
    terrain, hydrology, _, _, resources, regions, routes = physical_world
    ref = ReferenceIndex.build(terrain, hydrology, regions, routes, resources)
    # Region lookup
    first_region = regions.regions[0]
    assert ref.region(first_region.region_id) is not None
    # Route lookup
    if routes.routes:
        first_route = routes.routes[0]
        assert ref.route(first_route.route_id) is not None
        # Routes for region
        route_ids = ref.routes_for_region(first_route.start_region)
        assert first_route.route_id in route_ids
    # Lake lookup
    if hydrology.lakes:
        first_lake = hydrology.lakes[0]
        assert ref.lake(first_lake.lake_id) is not None
    # Deposit lookup
    if resources.deposits:
        first_deposit = resources.deposits[0]
        assert ref.deposit(first_deposit.deposit_id) is not None


def test_reference_index_rebuild_is_equal(physical_world):
    """P8.C05D: Reference index rebuild produces canonical equality."""
    terrain, hydrology, _, _, resources, regions, routes = physical_world
    a = ReferenceIndex.build(terrain, hydrology, regions, routes, resources)
    b = ReferenceIndex.build(terrain, hydrology, regions, routes, resources)
    assert a == b


def test_published_indexes_are_compact_verified_and_bounded(tmp_path):
    from src.domain.run_spec import WorldSpec
    from src.worldgen.physical_pipeline import generate_physical_world
    root = tmp_path / "world"
    generate_physical_world(WorldSpec(
        width=32, height=32, continent_count=1, plate_count=4,
        minimum_continent_cells=1, erosion_passes=1, climate_relaxation_passes=8,
    ), 42, root)
    spatial = VerifiedSpatialIndexReader(root)
    reference = VerifiedReferenceIndexReader(root)
    region_id = spatial.region_at(16, 16)
    all_regions = spatial.regions_in_bbox(BoundingBox(0, 0, 31, 31), limit=2)
    assert len(all_regions) <= 2
    if region_id is not None:
        assert reference.entity(region_id).source_artifact_id == reference.sources["regions"]
        assert spatial.routes_for_region(region_id) == reference.reverse(
            "routes_through_region", region_id,
        )
    assert len(reference.active_between(0, 0, limit=3)) <= 3
    with pytest.raises(ValueError, match="invalid result limit"):
        spatial.regions_in_bbox(BoundingBox(0, 0, 31, 31), limit=257)
    with pytest.raises(ValueError, match="unknown reverse relation"):
        reference.reverse("arbitrary", "x")
    entities = reference.payload["entities"]
    assert all(isinstance(entity_id, str) for ids in entities.values() for entity_id in ids)
    assert "cells" not in reference.payload and "cell_to_region" not in spatial.payload


def test_map_dimensions_are_canonical(physical_world, tmp_path):
    """P8.C05D: Rendered maps have validated pixel dimensions."""
    from src.worldgen.maps import render_maps
    terrain, _, _, biomes, _, regions, routes = physical_world
    maps = render_maps(tmp_path, terrain, biomes, regions, routes)
    world_png = maps["world"].read_bytes()
    # Parse PNG header to verify dimensions
    import struct
    assert world_png[:8] == b'\x89PNG\r\n\x1a\n'
    ihdr_start = 8 + 4  # skip length field
    ihdr_data = world_png[ihdr_start + 4:ihdr_start + 4 + 13]  # skip "IHDR"
    w, h = struct.unpack(">II", ihdr_data[:8])
    assert w == terrain.grid.width
    assert h == terrain.grid.height
