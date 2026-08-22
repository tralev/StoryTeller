"""Typed immutable macro-world boundary conditions for every local site."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields

from ..world.views import WorldView
from .numeric import identity, stable_id

LOCAL_BOUNDARY_ALGORITHM_VERSION = 1
LOCAL_BOUNDARY_SOURCE_KINDS = (
    "sites", "regions", "terrain", "geology", "hydrology", "climate", "resources",
    "routes", "civilizations", "settlements",
)
CARDINAL_EDGES = (("north", 0, -1), ("east", 1, 0), ("south", 0, 1),
                  ("west", -1, 0))


@dataclass(frozen=True)
class MacroBoundaryEdge:
    direction: str
    neighbor_cell: int | None
    elevation_mm: int
    neighbor_elevation_mm: int | None
    coastline: bool
    neighbor_coastline: bool | None
    river_edge_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    annual_temperature_millic: int
    annual_precipitation_mm: int
    deposit_ids: tuple[str, ...]
    renewable_yield: int
    region_id: str
    civilization_id: str


@dataclass(frozen=True)
class LocalBoundaryConditions:
    algorithm_version: int
    boundary_id: str
    site_id: str
    region_id: str
    macro_cell: int
    elevation_mm: int
    rock_class_id: int
    strata_id: int
    parent_material_id: int
    fault: bool
    volcanic: bool
    coastline: bool
    river_edge_ids: tuple[str, ...]
    lake_ids: tuple[str, ...]
    aquifer_capacity_mm: int
    annual_temperature_millic: int
    annual_precipitation_mm: int
    weather_regime: int
    deposit_ids: tuple[str, ...]
    renewable_yield: int
    route_ids: tuple[str, ...]
    civilization_id: str
    culture: str
    settlement_id: str
    settlement_status: str
    settlement_population: int
    building_ids: tuple[str, ...]
    workshop_ids: tuple[str, ...]
    inventory: tuple[tuple[str, int], ...]
    edges: tuple[MacroBoundaryEdge, ...]
    source_artifact_ids: tuple[str, ...]


def local_boundary_from_mapping(value: Mapping[str, object]) -> LocalBoundaryConditions:
    """Strict typed reader for one persisted local-boundary record."""
    expected = {field.name for field in fields(LocalBoundaryConditions)}
    if set(value) != expected:
        raise ValueError("WG-LOCAL-BOUNDARY-READ: field set mismatch")

    def integer(name: str) -> int:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-BOUNDARY-READ: {name} must be an integer")
        return item

    def boolean(name: str) -> bool:
        item = value[name]
        if not isinstance(item, bool):
            raise ValueError(f"WG-LOCAL-BOUNDARY-READ: {name} must be a boolean")
        return item

    def strings(name: str) -> tuple[str, ...]:
        item = value[name]
        if (not isinstance(item, Sequence) or isinstance(item, (str, bytes))
                or not all(isinstance(child, str) for child in item)):
            raise ValueError(f"WG-LOCAL-BOUNDARY-READ: {name} must contain strings")
        return tuple(item)

    inventory_raw = value["inventory"]
    if (not isinstance(inventory_raw, Sequence)
            or isinstance(inventory_raw, (str, bytes))):
        raise ValueError("WG-LOCAL-BOUNDARY-READ: inventory must be a sequence")
    inventory: list[tuple[str, int]] = []
    for pair in inventory_raw:
        if (not isinstance(pair, Sequence) or isinstance(pair, (str, bytes))
                or len(pair) != 2 or not isinstance(pair[0], str)
                or isinstance(pair[1], bool) or not isinstance(pair[1], int)):
            raise ValueError("WG-LOCAL-BOUNDARY-READ: invalid inventory entry")
        inventory.append((pair[0], pair[1]))
    edges_raw = value["edges"]
    if not isinstance(edges_raw, Sequence) or isinstance(edges_raw, (str, bytes)):
        raise ValueError("WG-LOCAL-BOUNDARY-READ: edges must be a sequence")
    edge_fields = {field.name for field in fields(MacroBoundaryEdge)}
    edges: list[MacroBoundaryEdge] = []
    for edge in edges_raw:
        if not isinstance(edge, Mapping) or set(edge) != edge_fields:
            raise ValueError("WG-LOCAL-BOUNDARY-READ: edge field set mismatch")

        def edge_integer(name: str) -> int:
            item = edge[name]
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError(f"WG-LOCAL-BOUNDARY-READ: edge {name} must be an integer")
            return int(item)

        def edge_optional_integer(name: str) -> int | None:
            item = edge[name]
            if item is None:
                return None
            return edge_integer(name)

        def edge_boolean(name: str) -> bool:
            item = edge[name]
            if not isinstance(item, bool):
                raise ValueError(f"WG-LOCAL-BOUNDARY-READ: edge {name} must be a boolean")
            return item

        def edge_optional_boolean(name: str) -> bool | None:
            if edge[name] is None:
                return None
            return edge_boolean(name)

        def edge_strings(name: str) -> tuple[str, ...]:
            item = edge[name]
            if (not isinstance(item, Sequence) or isinstance(item, (str, bytes))
                    or not all(isinstance(child, str) for child in item)):
                raise ValueError(f"WG-LOCAL-BOUNDARY-READ: edge {name} must contain strings")
            return tuple(item)

        direction, region_id, owner_id = (
            edge["direction"], edge["region_id"], edge["civilization_id"]
        )
        if (not isinstance(direction, str) or not isinstance(region_id, str)
                or not isinstance(owner_id, str)):
            raise ValueError("WG-LOCAL-BOUNDARY-READ: edge text field is invalid")
        edges.append(MacroBoundaryEdge(
            direction, edge_optional_integer("neighbor_cell"), edge_integer("elevation_mm"),
            edge_optional_integer("neighbor_elevation_mm"), edge_boolean("coastline"),
            edge_optional_boolean("neighbor_coastline"),
            edge_strings("river_edge_ids"), edge_strings("route_ids"),
            edge_integer("annual_temperature_millic"),
            edge_integer("annual_precipitation_mm"), edge_strings("deposit_ids"),
            edge_integer("renewable_yield"), region_id, owner_id,
        ))
    scalar_strings = (
        "boundary_id", "site_id", "region_id", "civilization_id", "culture",
        "settlement_id", "settlement_status",
    )
    if any(not isinstance(value[name], str) or not value[name] for name in scalar_strings):
        raise ValueError("WG-LOCAL-BOUNDARY-READ: identifier/text field is invalid")
    return LocalBoundaryConditions(
        integer("algorithm_version"), str(value["boundary_id"]), str(value["site_id"]),
        str(value["region_id"]), integer("macro_cell"), integer("elevation_mm"),
        integer("rock_class_id"), integer("strata_id"), integer("parent_material_id"),
        boolean("fault"), boolean("volcanic"), boolean("coastline"),
        strings("river_edge_ids"), strings("lake_ids"), integer("aquifer_capacity_mm"),
        integer("annual_temperature_millic"), integer("annual_precipitation_mm"),
        integer("weather_regime"), strings("deposit_ids"), integer("renewable_yield"),
        strings("route_ids"), str(value["civilization_id"]), str(value["culture"]),
        str(value["settlement_id"]), str(value["settlement_status"]),
        integer("settlement_population"), strings("building_ids"),
        strings("workshop_ids"), tuple(inventory), tuple(edges),
        strings("source_artifact_ids"),
    )


def _edge_constraints(
    world: WorldView, cell: int, region_by_cell: dict[int, str], owner_by_region: dict[str, str],
) -> tuple[MacroBoundaryEdge, ...]:
    terrain = world.terrain_elevation()
    hydrology = world.hydrology().hydrology
    climate = world.climate().climate
    resources = world.resources().resources
    routes = world.routes()
    point = terrain.spec.coordinate(cell)
    result: list[MacroBoundaryEdge] = []
    for direction, dx, dy in CARDINAL_EDGES:
        nx, ny = point.x + dx, point.y + dy
        neighbor = (terrain.spec.index(nx, ny)
                    if 0 <= nx < terrain.spec.width and 0 <= ny < terrain.spec.height
                    else None)
        pair = {cell, neighbor} if neighbor is not None else set()
        river_ids = tuple(sorted(
            f"river:{edge.upstream}:{edge.downstream}"
            for edge in hydrology.rivers if {edge.upstream, edge.downstream} == pair
        ))
        route_ids = tuple(sorted(
            route.fact_id for route in routes
            if neighbor is not None and any(
                {left, right} == pair
                for left, right in zip(route.value["cells"], route.value["cells"][1:])
            )
        ))
        boundary_cell = cell if neighbor is None else neighbor
        deposits = tuple(sorted(
            item.deposit_id for item in resources.deposits if boundary_cell in item.cells
        ))
        region_id = region_by_cell.get(boundary_cell, "")
        result.append(MacroBoundaryEdge(
            direction, neighbor, int(terrain.values[cell]),
            None if neighbor is None else int(terrain.values[neighbor]),
            bool(hydrology.coastline.values[cell]),
            None if neighbor is None else bool(hydrology.coastline.values[neighbor]),
            river_ids, route_ids, int(climate.annual_temperature_millic.values[boundary_cell]),
            int(climate.annual_precipitation_mm.values[boundary_cell]), deposits,
            int(resources.renewable_yield.values[boundary_cell]), region_id,
            owner_by_region.get(region_id, ""),
        ))
    return tuple(result)


def _derive_local_boundaries(world: WorldView) -> tuple[LocalBoundaryConditions, ...]:
    """Join every authoritative macro domain into one canonical record per site."""
    terrain = world.terrain_elevation()
    geology = world.geology().geology
    hydrology = world.hydrology().hydrology
    climate = world.climate().climate
    resources = world.resources().resources
    regions = {item.fact_id: item for item in world.regions()}
    routes = world.routes()
    civilizations = {item.fact_id: item for item in world.civilizations()}
    region_by_cell = {
        int(cell): region.fact_id for region in regions.values() for cell in region.value["cells"]
    }
    owner_by_region = {
        str(region_id): civilization.fact_id
        for civilization in civilizations.values()
        for region_id in civilization.value["territory"]
    }
    settlements = {str(item.value["site_id"]): item for item in world.settlements()}
    source_ids = tuple(world.artifact_ids[kind] for kind in LOCAL_BOUNDARY_SOURCE_KINDS)
    result: list[LocalBoundaryConditions] = []
    for site in sorted(world.sites(), key=lambda item: item.fact_id):
        cell = int(site.value["cell"])
        region_id = str(site.value["region_id"])
        region = regions.get(region_id)
        settlement = settlements.get(site.fact_id)
        if region is None or cell not in region.value["cells"] or settlement is None:
            raise ValueError(
                "WG-LOCAL-BOUNDARY: invalid site-region-settlement join "
                f"{site.fact_id}"
            )
        civilization_id = str(settlement.value["civilization_id"])
        civilization = civilizations.get(civilization_id)
        if civilization is None:
            raise ValueError(f"WG-LOCAL-BOUNDARY: unknown owner {civilization_id}")
        river_ids = tuple(sorted(
            f"river:{edge.upstream}:{edge.downstream}"
            for edge in hydrology.rivers if cell in {edge.upstream, edge.downstream}
        ))
        lake_ids = tuple(sorted(lake.lake_id for lake in hydrology.lakes if cell in lake.cells))
        deposit_ids = tuple(sorted(
            deposit.deposit_id for deposit in resources.deposits if cell in deposit.cells
        ))
        route_ids = tuple(sorted(
            route.fact_id for route in routes
            if (cell in route.value["cells"]
                or region_id in {route.value["start_region"], route.value["end_region"]})
        ))
        inventory = tuple(sorted(
            (str(item["material_id"]), int(item["quantity"]))
            for item in settlement.value["inventory"]
        ))
        workshops = tuple(sorted(
            str(item["workshop_id"]) for item in settlement.value["workshops"]
        ))
        result.append(LocalBoundaryConditions(
            LOCAL_BOUNDARY_ALGORITHM_VERSION,
            stable_id("local_boundary", int(world.payload("world_index")["seed"]),
                      identity("site_id", site.fact_id)),
            site.fact_id, region_id, cell, int(terrain.values[cell]),
            int(geology.rock_class_id.values[cell]), int(geology.strata_id.values[cell]),
            int(geology.parent_material_id.values[cell]), bool(geology.fault.values[cell]),
            bool(geology.volcano.values[cell]), bool(hydrology.coastline.values[cell]),
            river_ids, lake_ids, int(hydrology.aquifer_capacity_mm.values[cell]),
            int(climate.annual_temperature_millic.values[cell]),
            int(climate.annual_precipitation_mm.values[cell]),
            int(climate.weather_regime.values[cell]), deposit_ids,
            int(resources.renewable_yield.values[cell]), route_ids, civilization_id,
            str(civilization.value["culture"]), str(settlement.value["settlement_id"]),
            str(settlement.value["status"]), int(settlement.value["population"]),
            tuple(sorted(str(item) for item in settlement.value["buildings"])), workshops,
            inventory, _edge_constraints(world, cell, region_by_cell, owner_by_region),
            source_ids,
        ))
    return tuple(result)


def derive_local_boundaries(world: WorldView) -> tuple[LocalBoundaryConditions, ...]:
    """Return validated canonical boundary records for every registered site."""
    result = _derive_local_boundaries(world)
    validate_local_boundaries(world, result)
    return result


def validate_local_boundaries(
    world: WorldView, boundaries: tuple[LocalBoundaryConditions, ...],
) -> None:
    """Reject omissions, duplicates, noncanonical fields, and forged macro facts."""
    expected_sites = tuple(sorted(item.fact_id for item in world.sites()))
    actual_sites = tuple(item.site_id for item in boundaries)
    if actual_sites != expected_sites or len(actual_sites) != len(set(actual_sites)):
        raise ValueError("WG-LOCAL-BOUNDARY-COVERAGE: expected exactly one record per site")
    expected_sources = tuple(
        world.artifact_ids[kind] for kind in LOCAL_BOUNDARY_SOURCE_KINDS
    )
    if any(
        item.algorithm_version != LOCAL_BOUNDARY_ALGORITHM_VERSION
        or item.source_artifact_ids != expected_sources
        or item.river_edge_ids != tuple(sorted(set(item.river_edge_ids)))
        or item.lake_ids != tuple(sorted(set(item.lake_ids)))
        or item.deposit_ids != tuple(sorted(set(item.deposit_ids)))
        or item.route_ids != tuple(sorted(set(item.route_ids)))
        or item.building_ids != tuple(sorted(set(item.building_ids)))
        or item.workshop_ids != tuple(sorted(set(item.workshop_ids)))
        or item.inventory != tuple(sorted(item.inventory))
        or tuple(edge.direction for edge in item.edges)
        != tuple(direction for direction, _, _ in CARDINAL_EDGES)
        or any(
            edge.river_edge_ids != tuple(sorted(set(edge.river_edge_ids)))
            or edge.route_ids != tuple(sorted(set(edge.route_ids)))
            or edge.deposit_ids != tuple(sorted(set(edge.deposit_ids)))
            for edge in item.edges
        )
        or item.settlement_population < 0
        or item.aquifer_capacity_mm < 0
        or item.renewable_yield < 0
        for item in boundaries
    ):
        raise ValueError("WG-LOCAL-BOUNDARY-SHAPE: noncanonical boundary record")
    if len({item.boundary_id for item in boundaries}) != len(boundaries):
        raise ValueError("WG-LOCAL-BOUNDARY-ID: duplicate boundary identity")
    if boundaries != _derive_local_boundaries(world):
        raise ValueError("WG-LOCAL-BOUNDARY-MISMATCH: boundary contradicts macro authority")
