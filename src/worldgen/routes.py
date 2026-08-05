"""Stable A* route geometry and seasonal route characteristics."""
from __future__ import annotations

import heapq

from .physical_models import ClimateLayer, Hydrology, RegionLayer, ResourceLayer, Route, RouteLayer, Terrain

ALGORITHM_VERSION = 1


def _path(terrain: Terrain, hydrology: Hydrology, start: int, goal: int) -> tuple[int, ...]:
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
            if not terrain.land.values[neighbor]:
                continue
            step = 1_000 + terrain.slope_ppm.values[neighbor] + (2_000 if hydrology.accumulation.values[neighbor] > 8 else 0)
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
            neighbor = by_id[neighbor_id]
            cells = _path(terrain, hydrology, region.center, neighbor.center)
            if not cells:
                continue
            crossings = sum(1 for i in cells if hydrology.accumulation.values[i] > 8)
            terrain_cost = sum(1_000 + terrain.slope_ppm.values[i] for i in cells)
            risks = tuple(sum(season.hazard_ppm.values[i] for i in cells) // len(cells) for season in climate.seasons)
            resource_bonus = sum(resources.renewable_yield.values[i] for i in cells) // max(1, len(cells))
            capacities = tuple(max(1, 1_000_000 // max(1, risk // 10_000 + 1) + resource_bonus // 1_000_000)
                               for risk in risks)
            risk4 = (risks[0], risks[1], risks[2], risks[3])
            capacity4 = (capacities[0], capacities[1], capacities[2], capacities[3])
            routes.append(Route(f"route_{len(routes) + 1:05d}", pair[0], pair[1], cells,
                                (len(cells) - 1) * terrain.grid.metres_per_world_cell,
                                terrain_cost, crossings, risk4, capacity4))
    return RouteLayer(ALGORITHM_VERSION, tuple(routes))
