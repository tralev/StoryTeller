"""Stable A* route geometry and seasonal route characteristics."""
from __future__ import annotations

import heapq

from .numeric import div_floor_exact, div_round_half_up
from .physical_models import (ClimateLayer, Hydrology, RegionLayer, ResourceLayer, Route,
                              RouteKind, RouteLayer, Terrain)

ALGORITHM_VERSION = 2
COST_UNIT = "fixed_travel_cost"
ROUTE_CLASS_RULES: dict[RouteKind, dict[str, int | str]] = {
    RouteKind.ROAD: {"surface": "land", "base_cost": 700, "slope_ppm": 800_000,
                     "river_cost": 3_000, "capacity": 150_000, "maintenance_per_km": 25},
    RouteKind.TRAIL: {"surface": "land", "base_cost": 1_000, "slope_ppm": 1_000_000,
                      "river_cost": 2_000, "capacity": 80_000, "maintenance_per_km": 5},
    RouteKind.NAVIGABLE_RIVER: {"surface": "land", "base_cost": 900, "slope_ppm": 600_000,
                                "river_cost": -500, "capacity": 120_000, "maintenance_per_km": 8},
    RouteKind.SEA_LANE: {"surface": "ocean", "base_cost": 600, "slope_ppm": 0,
                         "river_cost": 0, "capacity": 200_000, "maintenance_per_km": 10},
    RouteKind.MOUNTAIN_PASS: {"surface": "land", "base_cost": 1_300, "slope_ppm": 700_000,
                              "river_cost": 2_500, "capacity": 50_000, "maintenance_per_km": 20},
    RouteKind.SETTLEMENT_LINK: {"surface": "land", "base_cost": 800, "slope_ppm": 900_000,
                                "river_cost": 2_000, "capacity": 100_000, "maintenance_per_km": 15},
}


def _rule_integer(kind: RouteKind, field: str) -> int:
    value = ROUTE_CLASS_RULES[kind][field]
    if not isinstance(value, int):
        raise ValueError(f"WG-ROUTE-RULE: {kind.name}.{field}")
    return value


def _path(terrain: Terrain, hydrology: Hydrology, climate: ClimateLayer,
          start: int, goal: int, season: int, kind: RouteKind) -> tuple[int, ...]:
    grid = terrain.grid
    frontier: list[tuple[int, int, int]] = [(0, 0, start)]
    cost = {start: 0}
    parent: dict[int, int] = {}
    while frontier:
        _, current_cost, current = heapq.heappop(frontier)
        if current == goal:
            break
        if current_cost != cost[current]:
            continue
        for neighbor in grid.neighbors4(current):
            surface = ROUTE_CLASS_RULES[kind]["surface"]
            if ((surface == "land" and not terrain.land.values[neighbor])
                    or (surface == "ocean" and terrain.land.values[neighbor])):
                continue
            step = (_rule_integer(kind, "base_cost")
                    + div_round_half_up(terrain.slope_ppm.values[neighbor]
                                        * _rule_integer(kind, "slope_ppm"), 1_000_000)
                    + (_rule_integer(kind, "river_cost")
                       if hydrology.accumulation.values[neighbor] > 8 else 0)
                    + div_round_half_up(climate.seasons[season].hazard_ppm.values[neighbor], 1_000))
            step = max(1, step)
            candidate = current_cost + step
            if candidate < cost.get(neighbor, 1 << 62):
                cost[neighbor], parent[neighbor] = candidate, current
                a, b = grid.coordinate(neighbor), grid.coordinate(goal)
                heuristic = (abs(a.x - b.x) + abs(a.y - b.y)) * 1_000
                heapq.heappush(frontier, (candidate + heuristic, candidate, neighbor))
    if goal not in cost:
        return ()
    result = [goal]
    while result[-1] != start:
        result.append(parent[result[-1]])
    return tuple(reversed(result))


def generate_routes(terrain: Terrain, hydrology: Hydrology, climate: ClimateLayer,
                    resources: ResourceLayer, regions: RegionLayer) -> RouteLayer:
    by_id = {region.region_id: region for region in regions.regions}
    routes: list[Route] = []
    seen: set[tuple[str, str]] = set()
    for region in regions.regions:
        for neighbor_id in region.neighbors:
            pair = (min(region.region_id, neighbor_id), max(region.region_id, neighbor_id))
            if pair in seen:
                continue
            seen.add(pair)
            start_region, end_region = by_id[pair[0]], by_id[pair[1]]
            preliminary = _path(terrain, hydrology, climate, start_region.center, end_region.center,
                                0, RouteKind.TRAIL)
            if not preliminary:
                continue
            preliminary_crossings = sum(
                1 for cell in preliminary if hydrology.accumulation.values[cell] > 8
            )
            preliminary_resource = sum(resources.renewable_yield.values[cell]
                                       for cell in preliminary)
            maximum_slope = max(terrain.slope_ppm.values[cell] for cell in preliminary)
            route_kind = (RouteKind.NAVIGABLE_RIVER
                          if preliminary_crossings * 2 >= len(preliminary) else
                          RouteKind.MOUNTAIN_PASS if maximum_slope >= 5_000 else
                          RouteKind.ROAD if preliminary_resource else RouteKind.TRAIL)
            seasonal_paths = tuple(
                _path(terrain, hydrology, climate, start_region.center, end_region.center, season,
                      route_kind)
                for season in range(4)
            )
            if any(not path for path in seasonal_paths):
                continue
            cells = min(seasonal_paths, key=lambda path: (len(path), path))
            crossings = sum(1 for i in cells if hydrology.accumulation.values[i] > 8)
            terrain_cost = sum(1_000 + terrain.slope_ppm.values[i] for i in cells)
            risks = tuple(
                div_round_half_up(
                    sum(season.hazard_ppm.values[i] for i in cells), len(cells),
                )
                for season in climate.seasons
            )
            resource_bonus = div_round_half_up(
                sum(resources.renewable_yield.values[i] for i in cells),
                max(1, len(cells)),
            )
            capacities = tuple(
                max(
                    1,
                    div_round_half_up(
                        _rule_integer(route_kind, "capacity"),
                        max(1, div_floor_exact(risk, 10_000) + 1),
                    )
                    + div_round_half_up(resource_bonus, 1_000_000),
                )
                for risk in risks
            )
            risk4 = (risks[0], risks[1], risks[2], risks[3])
            capacity4 = (capacities[0], capacities[1], capacities[2], capacities[3])
            seasonal4 = (seasonal_paths[0], seasonal_paths[1], seasonal_paths[2], seasonal_paths[3])
            traversable = tuple(capacity > 0 and risk < 950_000
                                for capacity, risk in zip(capacity4, risk4))
            traversable4 = (traversable[0], traversable[1], traversable[2], traversable[3])
            distance_m = (len(cells) - 1) * terrain.grid.metres_per_world_cell
            maintenance = div_round_half_up(
                distance_m * _rule_integer(route_kind, "maintenance_per_km"), 1_000,
            )
            routes.append(Route(f"route_{len(routes) + 1:05d}", pair[0], pair[1], cells,
                                distance_m,
                                terrain_cost, crossings, risk4, capacity4, route_kind,
                                seasonal4, traversable4, COST_UNIT, maintenance, pair))
    return RouteLayer(ALGORITHM_VERSION, tuple(routes))
