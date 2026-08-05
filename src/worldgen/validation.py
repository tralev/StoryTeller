"""Phase 2 physical-world invariants."""
from __future__ import annotations

from .physical_models import BiomeLayer, ClimateLayer, Hydrology, RegionLayer, ResourceLayer, RouteLayer, Terrain


class WorldInvariantError(ValueError):
    pass


def validate_physical_world(terrain: Terrain, hydrology: Hydrology, climate: ClimateLayer,
                            biomes: BiomeLayer, resources: ResourceLayer,
                            regions: RegionLayer, routes: RouteLayer) -> None:
    count = terrain.grid.cell_count
    grids = (terrain.elevation_mm, terrain.land, terrain.continent_id,
             hydrology.flow_to, hydrology.accumulation, hydrology.watershed_id,
             climate.annual_temperature_millic, climate.annual_precipitation_mm,
             biomes.biome_id, resources.geology_id, regions.cell_region)
    if any(len(layer.values) != count for layer in grids):
        raise WorldInvariantError("WG-COVERAGE: a physical layer does not cover every cell")
    continents = {value for value in terrain.continent_id.values if value}
    if continents != set(range(1, len(continents) + 1)):
        raise WorldInvariantError("WG-CONTINENTS: noncanonical continent labels")
    for river in hydrology.rivers:
        if river.discharge_m3s <= 0 or river.upstream == river.downstream:
            raise WorldInvariantError("WG-RIVER: invalid river edge")
        if hydrology.flow_to.values[river.upstream] != river.downstream:
            raise WorldInvariantError("WG-RIVER: discontinuous river")
    land = {i for i, value in enumerate(terrain.land.values) if value}
    owned = {cell for region in regions.regions for cell in region.cells}
    if land != owned or sum(len(region.cells) for region in regions.regions) != len(owned):
        raise WorldInvariantError("WG-REGIONS: every land cell must have exactly one owner")
    neighbor_map = {region.region_id: set(region.neighbors) for region in regions.regions}
    if any(region.region_id not in neighbor_map.get(other, set())
           for region in regions.regions for other in region.neighbors):
        raise WorldInvariantError("WG-REGIONS: adjacency must be symmetric")
    valid_regions = set(neighbor_map)
    for route in routes.routes:
        if route.start_region not in valid_regions or route.end_region not in valid_regions or not route.cells:
            raise WorldInvariantError("WG-ROUTE: invalid endpoint or geometry")
        if any(not terrain.land.values[cell] for cell in route.cells):
            raise WorldInvariantError("WG-ROUTE: route crosses non-traversable ocean")
        if any(capacity <= 0 for capacity in route.seasonal_capacity):
            raise WorldInvariantError("WG-ROUTE: non-positive capacity")
