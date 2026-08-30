"""Phase 2 physical-world invariants."""

from __future__ import annotations

from ..domain.run_spec import WorldSpec
from .numeric import div_floor_exact, div_round_half_up
from .physical_models import (
    BiomeLayer,
    ClimateLayer,
    DrainageTerminalKind,
    EcologyLayer,
    Hydrology,
    PlateBoundaryClass,
    RegionLayer,
    ResourceLayer,
    RouteLayer,
    SoilLayer,
    Terrain,
)
from .physical_regions import MAX_REGION_CELLS, MIN_REGION_CELLS
from .physical_terrain import (
    LAND_FRACTION_TOLERANCE_PPM,
    MAX_ELEVATION_MM,
    MIN_ELEVATION_MM,
    classify_plate_boundary,
)
from .resources import RESOURCE_DENSITY_KG_M2
from .routes import COST_UNIT, ROUTE_CLASS_RULES


class WorldInvariantError(ValueError):
    pass


def validate_terrain_contract(terrain: Terrain, spec: WorldSpec) -> None:
    elevations = terrain.elevation_mm.values
    if any(not MIN_ELEVATION_MM <= value <= MAX_ELEVATION_MM for value in elevations):
        raise WorldInvariantError("WG-ELEVATION-BOUNDS: elevation outside contract")
    actual_land_ppm = div_round_half_up(
        sum(terrain.land.values) * 1_000_000, terrain.grid.cell_count
    )
    if abs(actual_land_ppm - (1_000_000 - spec.sea_level_ppm)) > LAND_FRACTION_TOLERANCE_PPM:
        raise WorldInvariantError("WG-LAND-FRACTION: output does not satisfy specification")
    continents = {value for value in terrain.continent_id.values if value}
    if continents != set(range(1, spec.continent_count + 1)):
        raise WorldInvariantError("WG-CONTINENTS: output count does not satisfy specification")


def validate_regions(terrain: Terrain, regions: RegionLayer) -> None:
    owner = regions.cell_region.values
    land = {index for index, value in enumerate(terrain.land.values) if value}
    cells = [cell for region in regions.regions for cell in region.cells]
    if set(cells) != land or len(cells) != len(set(cells)):
        raise WorldInvariantError("WG-REGIONS: land ownership is not an exact partition")
    neighbor_map = {region.region_id: set(region.neighbors) for region in regions.regions}
    from .physical_regions import physical_region_id

    for number, region in enumerate(regions.regions, 1):
        if (
            region.region_id != physical_region_id(terrain, region.cells)
            or not MIN_REGION_CELLS <= len(region.cells) <= MAX_REGION_CELLS
            or tuple(sorted(region.cells)) != region.cells
            or any(owner[cell] != number for cell in region.cells)
        ):
            raise WorldInvariantError("WG-REGIONS: identity, order, or size bounds invalid")
        reached, frontier = {region.cells[0]}, [region.cells[0]]
        while frontier:
            cell = frontier.pop()
            for neighbor in terrain.grid.neighbors4(cell):
                if owner[neighbor] == number and neighbor not in reached:
                    reached.add(neighbor)
                    frontier.append(neighbor)
        if reached != set(region.cells):
            raise WorldInvariantError("WG-REGIONS: region is disconnected")
        expected_boundary = tuple(
            cell
            for cell in region.cells
            if any(owner[neighbor] != number for neighbor in terrain.grid.neighbors4(cell))
        )
        mean_x = div_round_half_up(
            sum(terrain.grid.coordinate(cell).x for cell in region.cells), len(region.cells)
        )
        mean_y = div_round_half_up(
            sum(terrain.grid.coordinate(cell).y for cell in region.cells), len(region.cells)
        )
        expected_center = min(
            region.cells,
            key=lambda cell: (
                abs(terrain.grid.coordinate(cell).x - mean_x)
                + abs(terrain.grid.coordinate(cell).y - mean_y),
                cell,
            ),
        )
        if region.boundary_cells != expected_boundary or region.center != expected_center:
            raise WorldInvariantError("WG-REGIONS: noncanonical center or boundary")
        if any(
            region.region_id not in neighbor_map.get(neighbor, set())
            for neighbor in region.neighbors
        ):
            raise WorldInvariantError("WG-REGIONS: adjacency is not symmetric")


def validate_ecology(ecology: EcologyLayer, regions: RegionLayer) -> None:
    region_ids = {region.region_id for region in regions.regions}
    species_ids = {species.species_id for species in ecology.species}
    keys = {(item.species_id, item.region_id) for item in ecology.regional_populations}
    if keys != {(species_id, region_id) for species_id in species_ids for region_id in region_ids}:
        raise WorldInvariantError("WG-ECOLOGY: population coverage mismatch")
    if any(
        not 0 <= item.habitat_suitability_ppm <= 1_000_000
        or item.carrying_capacity < 0
        or item.population < 0
        or item.extinct != (item.population == 0)
        for item in ecology.regional_populations
    ):
        raise WorldInvariantError("WG-ECOLOGY: invalid regional population")
    if any(
        entry.year < 1
        or entry.species_id not in species_ids
        or entry.region_id not in region_ids
        or min(
            entry.population_before,
            entry.births,
            entry.deaths,
            entry.immigrants,
            entry.emigrants,
            entry.population_after,
        )
        < 0
        or entry.population_before
        + entry.births
        - entry.deaths
        + entry.immigrants
        - entry.emigrants
        != entry.population_after
        for entry in ecology.transition_ledger
    ):
        raise WorldInvariantError("WG-ECOLOGY: invalid transition ledger")
    for year in {entry.year for entry in ecology.transition_ledger}:
        entries = [entry for entry in ecology.transition_ledger if entry.year == year]
        if sum(entry.immigrants for entry in entries) != sum(entry.emigrants for entry in entries):
            raise WorldInvariantError("WG-ECOLOGY: migration is not conservative")


def validate_physical_world(
    terrain: Terrain,
    hydrology: Hydrology,
    climate: ClimateLayer,
    soil: SoilLayer,
    biomes: BiomeLayer,
    resources: ResourceLayer,
    regions: RegionLayer,
    routes: RouteLayer,
) -> None:
    count = terrain.grid.cell_count
    grids = (
        terrain.elevation_mm,
        terrain.land,
        terrain.continent_id,
        hydrology.flow_to,
        hydrology.accumulation,
        hydrology.watershed_id,
        hydrology.delta,
        climate.annual_temperature_millic,
        climate.annual_precipitation_mm,
        soil.depth_mm,
        soil.fertility_ppm,
        soil.drainage_ppm,
        soil.erosion_class,
        biomes.biome_id,
        resources.geology_id,
        regions.cell_region,
    )
    if any(len(layer.values) != count for layer in grids):
        raise WorldInvariantError("WG-COVERAGE: a physical layer does not cover every cell")
    for index in terrain.grid.indices():
        values = (
            soil.depth_mm.values[index],
            soil.fertility_ppm.values[index],
            soil.drainage_ppm.values[index],
            soil.erosion_class.values[index],
        )
        if not terrain.land.values[index]:
            if values != (0, 0, 0, 0):
                raise WorldInvariantError("WG-SOIL: ocean soil must be empty")
        elif (
            not 100 <= values[0] <= 5_000
            or not 20_000 <= values[1] <= 1_000_000
            or not 0 <= values[2] <= 1_000_000
            or values[3] not in (1, 2, 3)
        ):
            raise WorldInvariantError("WG-SOIL: invalid land soil state")
    if len(climate.seasons) != 4 or len(climate.water_ledger) != 4:
        raise WorldInvariantError("WG-CLIMATE-WATER: exactly four seasonal ledgers required")
    for season_index, (season, ledger) in enumerate(zip(climate.seasons, climate.water_ledger)):
        seasonal_grids = (
            season.temperature_millic,
            season.precipitation_mm,
            season.evaporation_mm,
            season.snowpack_mm,
            season.ice,
            season.storm_ppm,
            season.wind_x_mmps,
            season.wind_y_mmps,
            season.hazard_ppm,
        )
        if any(len(layer.values) != count for layer in seasonal_grids):
            raise WorldInvariantError("WG-CLIMATE-WATER: seasonal grid coverage mismatch")
        if (
            ledger.season != season_index
            or ledger.precipitation_total_mm != sum(season.precipitation_mm.values)
            or ledger.evaporation_total_mm != sum(season.evaporation_mm.values)
            or ledger.snowpack_total_mm != sum(season.snowpack_mm.values)
            or ledger.ice_cell_count != sum(season.ice.values)
            or ledger.final_atmospheric_moisture_mm < 0
        ):
            raise WorldInvariantError("WG-CLIMATE-WATER: invalid seasonal ledger")
        for index in range(count):
            rain = season.precipitation_mm.values[index]
            evaporation = season.evaporation_mm.values[index]
            snow = season.snowpack_mm.values[index]
            ice = season.ice.values[index]
            storm = season.storm_ppm.values[index]
            if (
                not 0 <= evaporation <= rain
                or not 0 <= snow <= rain - evaporation
                or ice not in (0, 1)
                or not 0 <= storm <= 1_000_000
            ):
                raise WorldInvariantError("WG-CLIMATE-WATER: invalid seasonal water state")
    for pass_index, entry in enumerate(terrain.erosion_ledger):
        if (
            entry.pass_index != pass_index
            or entry.mass_before_mm != entry.mass_after_mm
            or entry.thermal_moved_mm < 0
            or entry.hydraulic_moved_mm < 0
            or entry.thermal_moved_mm > count * 16
            or entry.hydraulic_moved_mm > count * 8
        ):
            raise WorldInvariantError("WG-EROSION: invalid mass ledger")
        if (
            pass_index
            and terrain.erosion_ledger[pass_index - 1].mass_after_mm != entry.mass_before_mm
        ):
            raise WorldInvariantError("WG-EROSION: discontinuous mass ledger")
    if terrain.erosion_ledger and terrain.erosion_ledger[-1].mass_after_mm != sum(
        terrain.elevation_mm.values
    ):
        raise WorldInvariantError("WG-EROSION: final mass ledger mismatch")
    centers = tuple(plate.center for plate in terrain.plates)
    if len(centers) != len(set(centers)) or any(
        center not in terrain.grid.indices() for center in centers
    ):
        raise WorldInvariantError("WG-PLATES: plate centres must be unique and in bounds")
    for index in terrain.grid.indices():
        point = terrain.grid.coordinate(index)
        expected_owner = (
            min(
                range(len(terrain.plates)),
                key=lambda plate_index: (
                    (point.x - terrain.grid.coordinate(centers[plate_index]).x) ** 2
                    + (point.y - terrain.grid.coordinate(centers[plate_index]).y) ** 2,
                    plate_index,
                ),
            )
            + 1
        )
        owner = terrain.plate_id.values[index]
        if owner != expected_owner:
            raise WorldInvariantError("WG-PLATES: non-Voronoi plate ownership")
        neighbors = sorted(
            {
                terrain.plate_id.values[cell]
                for cell in terrain.grid.neighbors4(index)
                if terrain.plate_id.values[cell] != owner
            }
        )
        expected_boundary = PlateBoundaryClass.INTERIOR
        if neighbors:
            expected_boundary = classify_plate_boundary(
                terrain.grid,
                terrain.plates[owner - 1],
                terrain.plates[neighbors[0] - 1],
            )
        if terrain.plate_boundary.values[index] != expected_boundary:
            raise WorldInvariantError("WG-PLATES: invalid plate boundary class")
    continents = {value for value in terrain.continent_id.values if value}
    if continents != set(range(1, len(continents) + 1)):
        raise WorldInvariantError("WG-CONTINENTS: noncanonical continent labels")
    for river in hydrology.rivers:
        if river.discharge_m3s <= 0 or river.upstream == river.downstream:
            raise WorldInvariantError("WG-RIVER: invalid river edge")
        if hydrology.flow_to.values[river.upstream] != river.downstream:
            raise WorldInvariantError("WG-RIVER: discontinuous river")
    for index, target in enumerate(hydrology.flow_to.values):
        if target < 0:
            continue
        source = terrain.grid.coordinate(index)
        destination = terrain.grid.coordinate(target)
        if max(abs(source.x - destination.x), abs(source.y - destination.y)) != 1:
            raise WorldInvariantError("WG-HYDROLOGY-D8: flow target is not adjacent")
        if (
            hydrology.filled_elevation_mm.values[target]
            > hydrology.filled_elevation_mm.values[index]
        ):
            raise WorldInvariantError("WG-HYDROLOGY-D8: flow target is uphill after filling")
    incoming = [0] * count
    expected_accumulation = [1 if terrain.land.values[index] else 0 for index in range(count)]
    for target in hydrology.flow_to.values:
        if target >= 0:
            incoming[target] += 1
    ready = [index for index, degree in enumerate(incoming) if degree == 0]
    processed = 0
    while ready:
        index = ready.pop()
        processed += 1
        target = hydrology.flow_to.values[index]
        if target >= 0:
            expected_accumulation[target] += expected_accumulation[index]
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if processed != count or tuple(expected_accumulation) != hydrology.accumulation.values:
        raise WorldInvariantError("WG-HYDROLOGY-ACCUMULATION: invalid drainage accumulation")
    terminal = [-1] * count
    for index in terrain.grid.indices():
        if not terrain.land.values[index]:
            continue
        cursor = index
        while hydrology.flow_to.values[cursor] >= 0:
            cursor = hydrology.flow_to.values[cursor]
        terminal[index] = cursor
    terminal_ids = {
        outlet: number
        for number, outlet in enumerate(
            sorted(
                {terminal[index] for index in terrain.grid.indices() if terrain.land.values[index]}
            ),
            1,
        )
    }
    if any(
        hydrology.watershed_id.values[index]
        != (terminal_ids[terminal[index]] if terrain.land.values[index] else 0)
        for index in terrain.grid.indices()
    ):
        raise WorldInvariantError("WG-HYDROLOGY-WATERSHED: noncanonical outlet ownership")
    expected_terminals = tuple(sorted(terminal_ids.items(), key=lambda item: item[1]))
    if len(hydrology.terminals) != len(expected_terminals):
        raise WorldInvariantError("WG-HYDROLOGY-TERMINAL: incomplete terminal registry")
    for terminal_record, (cell, watershed_id) in zip(hydrology.terminals, expected_terminals):
        expected_kind = (
            DrainageTerminalKind.OCEAN
            if not terrain.land.values[cell]
            else DrainageTerminalKind.CLOSED_BASIN
        )
        if (
            terminal_record.terminal_id != f"terminal_{watershed_id:04d}"
            or terminal_record.cell != cell
            or terminal_record.kind != expected_kind
            or terminal_record.watershed_id != watershed_id
            or hydrology.flow_to.values[cell] != -1
        ):
            raise WorldInvariantError("WG-HYDROLOGY-TERMINAL: invalid declared terminal")
    depressed = {
        index
        for index in terrain.grid.indices()
        if terrain.land.values[index]
        and hydrology.filled_elevation_mm.values[index] > terrain.elevation_mm.values[index]
    }
    lake_cells = [cell for lake in hydrology.lakes for cell in lake.cells]
    if set(lake_cells) != depressed or len(lake_cells) != len(set(lake_cells)):
        raise WorldInvariantError("WG-HYDROLOGY-LAKE: lake coverage is not an exact partition")
    for number, lake in enumerate(hydrology.lakes, 1):
        if (
            lake.lake_id != f"lake_{number:04d}"
            or not lake.cells
            or tuple(sorted(lake.cells)) != lake.cells
            or len({hydrology.filled_elevation_mm.values[cell] for cell in lake.cells}) != 1
            or lake.surface_elevation_mm != hydrology.filled_elevation_mm.values[lake.cells[0]]
        ):
            raise WorldInvariantError("WG-HYDROLOGY-LAKE: noncanonical lake body")
        if (lake.spillway_cell is None) != (lake.outlet is None):
            raise WorldInvariantError("WG-HYDROLOGY-LAKE: incomplete spillway")
        if lake.spillway_cell is not None and (
            lake.spillway_cell not in lake.cells
            or hydrology.flow_to.values[lake.spillway_cell] != lake.outlet
            or lake.outlet in lake.cells
        ):
            raise WorldInvariantError("WG-HYDROLOGY-LAKE: invalid spillway edge")
    threshold = max(4, div_floor_exact(count, 200))
    for index in terrain.grid.indices():
        expected_coast = int(
            bool(terrain.land.values[index])
            and any(not terrain.land.values[cell] for cell in terrain.grid.neighbors4(index))
        )
        if hydrology.coastline.values[index] != expected_coast:
            raise WorldInvariantError("WG-HYDROLOGY-COAST: invalid coastline")
        aquifer = hydrology.aquifer_capacity_mm.values[index]
        if aquifer < 0 or aquifer > 2_000 or (not terrain.land.values[index] and aquifer != 0):
            raise WorldInvariantError("WG-HYDROLOGY-AQUIFER: invalid capacity")
        expected_delta = int(
            bool(expected_coast)
            and hydrology.flow_to.values[index] >= 0
            and not terrain.land.values[hydrology.flow_to.values[index]]
            and hydrology.accumulation.values[index] >= threshold
        )
        if hydrology.delta.values[index] != expected_delta:
            raise WorldInvariantError("WG-HYDROLOGY-DELTA: invalid river-mouth delta")
    occupied_deposit_cells: set[int] = set()
    deposit_ids: set[str] = set()
    for deposit in resources.deposits:
        if (
            deposit.deposit_id in deposit_ids
            or deposit.resource not in RESOURCE_DENSITY_KG_M2
            or len(deposit.cells) < 2
            or tuple(sorted(set(deposit.cells))) != deposit.cells
            or not 10_000 <= deposit.depth_mm <= 1_000_000
            or not 50_000 <= deposit.grade_ppm <= 500_000
        ):
            raise WorldInvariantError("WG-RESOURCE-DEPOSIT: invalid identity or scalar bounds")
        deposit_ids.add(deposit.deposit_id)
        cells = set(deposit.cells)
        if cells & occupied_deposit_cells or any(not terrain.land.values[cell] for cell in cells):
            raise WorldInvariantError("WG-RESOURCE-DEPOSIT: overlap or ocean cell")
        occupied_deposit_cells.update(cells)
        reached = {deposit.cells[0]}
        frontier = [deposit.cells[0]]
        while frontier:
            cell = frontier.pop()
            for neighbor in terrain.grid.neighbors4(cell):
                if neighbor in cells and neighbor not in reached:
                    reached.add(neighbor)
                    frontier.append(neighbor)
        rock = {resources.geology_id.values[cell] for cell in cells}
        strata = {resources.strata_id.values[cell] for cell in cells}
        fault = any(resources.fault.values[cell] for cell in cells)
        volcano = any(resources.volcano.values[cell] for cell in cells)
        if (
            reached != cells
            or rock != {deposit.rock_class_id}
            or strata != {deposit.strata_id}
            or fault != deposit.fault_related
            or volcano != deposit.volcanic_related
        ):
            raise WorldInvariantError("WG-RESOURCE-DEPOSIT: geometry or provenance mismatch")
        expected_resource = (
            "gems"
            if volcano
            else ("copper" if deposit.rock_class_id % 2 == 0 else "tin")
            if fault
            else {1: "coal", 2: "iron", 3: "flux_stone", 4: "copper", 5: "iron"}[
                deposit.rock_class_id
            ]
        )
        expected_quantity = div_round_half_up(
            len(cells)
            * terrain.grid.metres_per_world_cell**2
            * RESOURCE_DENSITY_KG_M2[deposit.resource]
            * deposit.grade_ppm,
            1_000_000,
        )
        if deposit.resource != expected_resource or deposit.quantity_kg != expected_quantity:
            raise WorldInvariantError("WG-RESOURCE-DEPOSIT: incompatible material or quantity")
    land = {i for i, value in enumerate(terrain.land.values) if value}
    owned = {cell for region in regions.regions for cell in region.cells}
    if land != owned or sum(len(region.cells) for region in regions.regions) != len(owned):
        raise WorldInvariantError("WG-REGIONS: every land cell must have exactly one owner")
    neighbor_map = {region.region_id: set(region.neighbors) for region in regions.regions}
    if any(
        region.region_id not in neighbor_map.get(other, set())
        for region in regions.regions
        for other in region.neighbors
    ):
        raise WorldInvariantError("WG-REGIONS: adjacency must be symmetric")
    valid_regions = set(neighbor_map)
    region_cells = {region.region_id: set(region.cells) for region in regions.regions}
    for route in routes.routes:
        if (
            route.start_region not in valid_regions
            or route.end_region not in valid_regions
            or not route.cells
        ):
            raise WorldInvariantError("WG-ROUTE: invalid endpoint or geometry")
        if any(not terrain.land.values[cell] for cell in route.cells):
            raise WorldInvariantError("WG-ROUTE: route crosses non-traversable ocean")
        if any(capacity <= 0 for capacity in route.seasonal_capacity):
            raise WorldInvariantError("WG-ROUTE: non-positive capacity")
        if (
            route.end_region not in neighbor_map[route.start_region]
            or route.cells[0] not in region_cells[route.start_region]
            or route.cells[-1] not in region_cells[route.end_region]
        ):
            raise WorldInvariantError("WG-ROUTE: disconnected pair or endpoint containment")
        rule = ROUTE_CLASS_RULES.get(route.route_kind)
        expected_sources = tuple(sorted((route.start_region, route.end_region)))
        if (
            rule is None
            or route.cost_unit != COST_UNIT
            or route.source_ids != expected_sources
            or route.annual_maintenance < 0
        ):
            raise WorldInvariantError("WG-ROUTE: invalid class rule or provenance")
        maintenance_rate = rule["maintenance_per_km"]
        if not isinstance(maintenance_rate, int):
            raise WorldInvariantError("WG-ROUTE: invalid maintenance rule")
        expected_maintenance = div_round_half_up(
            route.distance_m * maintenance_rate,
            1_000,
        )
        if route.annual_maintenance != expected_maintenance:
            raise WorldInvariantError("WG-ROUTE: invalid maintenance")
        if len(route.seasonal_cells) != 4 or len(route.traversable_seasons) != 4:
            raise WorldInvariantError("WG-ROUTE: incomplete seasonal geometry")
        for season_index, path in enumerate(route.seasonal_cells):
            if (
                not path
                or path[0] != route.cells[0]
                or path[-1] != route.cells[-1]
                or route.traversable_seasons[season_index]
                != (
                    route.seasonal_capacity[season_index] > 0
                    and route.seasonal_risk_ppm[season_index] < 950_000
                )
                or any(
                    bool(terrain.land.values[cell]) != (rule["surface"] == "land") for cell in path
                )
                or any(
                    target not in terrain.grid.neighbors4(source)
                    for source, target in zip(path, path[1:])
                )
            ):
                raise WorldInvariantError("WG-ROUTE: invalid seasonal path")
