"""Cost-aware deterministic multi-source physical-region partitioning."""

from __future__ import annotations

import heapq

from .grid import IntGrid
from .numeric import div_floor_exact, div_round_half_up, identity, stable_id
from .physical_models import (
    BiomeLayer,
    ClimateLayer,
    Hydrology,
    PhysicalRegion,
    RegionLayer,
    Terrain,
)

ALGORITHM_VERSION = 3
TARGET_REGION_CELLS = 128
MIN_REGION_CELLS = 16
MAX_REGION_CELLS = 256
REGION_COST_MODEL = {
    "base": 1_000,
    "biome_transition": 4_000,
    "watershed_transition": 2_500,
    "elevation_divisor_mm": 10,
    "temperature_divisor_millic": 100,
    "precipitation_divisor_mm": 10,
}


def region_step_cost(
    source: int,
    target: int,
    terrain: Terrain,
    hydrology: Hydrology,
    climate: ClimateLayer,
    biomes: BiomeLayer,
) -> int:
    return (
        REGION_COST_MODEL["base"]
        + (
            REGION_COST_MODEL["biome_transition"]
            if biomes.biome_id.values[source] != biomes.biome_id.values[target]
            else 0
        )
        + (
            REGION_COST_MODEL["watershed_transition"]
            if hydrology.watershed_id.values[source] != hydrology.watershed_id.values[target]
            else 0
        )
        + div_round_half_up(
            abs(terrain.elevation_mm.values[source] - terrain.elevation_mm.values[target]),
            REGION_COST_MODEL["elevation_divisor_mm"],
        )
        + div_round_half_up(
            abs(
                climate.annual_temperature_millic.values[source]
                - climate.annual_temperature_millic.values[target]
            ),
            REGION_COST_MODEL["temperature_divisor_millic"],
        )
        + div_round_half_up(
            abs(
                climate.annual_precipitation_mm.values[source]
                - climate.annual_precipitation_mm.values[target]
            ),
            REGION_COST_MODEL["precipitation_divisor_mm"],
        )
    )


def physical_region_id(terrain: Terrain, cells: tuple[int, ...]) -> str:
    """Derive the frozen 128-bit region ID from immutable physical identity."""
    grid = terrain.grid
    return stable_id(
        "region",
        ALGORITHM_VERSION,
        identity("grid", f"{grid.width}x{grid.height}x{grid.metres_per_world_cell}"),
        identity("cells", ",".join(str(cell) for cell in cells)),
    )


def _region_seeds(terrain: Terrain) -> tuple[int, ...]:
    land = tuple(index for index in terrain.grid.indices() if terrain.land.values[index])
    seeds = set(land[::TARGET_REGION_CELLS])
    for continent in sorted(set(terrain.continent_id.values) - {0}):
        seeds.add(next(index for index in land if terrain.continent_id.values[index] == continent))
    return tuple(sorted(seeds))


def _distances(cells: set[int], start: int, terrain: Terrain) -> dict[int, int]:
    result, frontier = {start: 0}, [start]
    for cell in frontier:
        for neighbor in terrain.grid.neighbors4(cell):
            if neighbor in cells and neighbor not in result:
                result[neighbor] = result[cell] + 1
                frontier.append(neighbor)
    return result


def _split_oversized(cells: set[int], terrain: Terrain) -> list[set[int]]:
    if len(cells) <= MAX_REGION_CELLS:
        return [cells]
    first = min(cells)
    first_distance = _distances(cells, first, terrain)
    second = max(cells, key=lambda cell: (first_distance[cell], -cell))
    second_distance = _distances(cells, second, terrain)
    left = {
        cell for cell in cells if (first_distance[cell], first) <= (second_distance[cell], second)
    }
    right = cells - left
    if not left or not right:
        ordered = sorted(cells)
        midpoint = div_floor_exact(len(ordered), 2)
        left, right = set(ordered[:midpoint]), set(ordered[midpoint:])
    return _split_oversized(left, terrain) + _split_oversized(right, terrain)


def _normalize_region_cells(raw: list[set[int]], terrain: Terrain) -> list[set[int]]:
    regions = [part for cells in raw for part in _split_oversized(cells, terrain)]
    while len(regions) > 1:
        small_index = next(
            (index for index, cells in enumerate(regions) if len(cells) < MIN_REGION_CELLS), None
        )
        if small_index is None:
            break
        small = regions[small_index]
        contacts: list[tuple[int, int, int, int]] = []
        for target_index, target in enumerate(regions):
            if target_index == small_index:
                continue
            contact = sum(
                neighbor in target for cell in small for neighbor in terrain.grid.neighbors4(cell)
            )
            if contact:
                fits = int(len(small) + len(target) <= MAX_REGION_CELLS)
                contacts.append((-fits, -contact, min(target), target_index))
        if not contacts:
            break
        target_index = min(contacts)[3]
        merged = small | regions[target_index]
        regions = [
            cells for index, cells in enumerate(regions) if index not in (small_index, target_index)
        ]
        regions.extend(_split_oversized(merged, terrain))
        regions.sort(key=min)
    return sorted(regions, key=min)


def generate_regions(
    terrain: Terrain,
    hydrology: Hydrology,
    climate: ClimateLayer,
    biomes: BiomeLayer,
) -> RegionLayer:
    grid = terrain.grid
    seeds = _region_seeds(terrain)
    owner = [0] * grid.cell_count
    distance: list[int | None] = [None] * grid.cell_count
    frontier: list[tuple[int, int, int]] = []
    for number, seed in enumerate(seeds, 1):
        distance[seed] = 0
        owner[seed] = number
        heapq.heappush(frontier, (0, number, seed))
    while frontier:
        cost, number, index = heapq.heappop(frontier)
        if distance[index] != cost or owner[index] != number:
            continue
        for neighbor in grid.neighbors4(index):
            if not terrain.land.values[neighbor]:
                continue
            candidate = cost + region_step_cost(
                index,
                neighbor,
                terrain,
                hydrology,
                climate,
                biomes,
            )
            current = distance[neighbor]
            if current is None or (candidate, number) < (current, owner[neighbor]):
                distance[neighbor] = candidate
                owner[neighbor] = number
                heapq.heappush(frontier, (candidate, number, neighbor))
    if any(terrain.land.values[index] and not owner[index] for index in grid.indices()):
        raise ValueError("WG-REGION-DIJKSTRA: incomplete land ownership")
    initial = [
        set(index for index, value in enumerate(owner) if value == number)
        for number in range(1, len(seeds) + 1)
    ]
    normalized = _normalize_region_cells(initial, terrain)
    owner = [0] * grid.cell_count
    for number, cells in enumerate(normalized, 1):
        for cell in cells:
            owner[cell] = number
    regions_raw = [tuple(sorted(cells)) for cells in normalized]
    adjacency: list[set[int]] = [set() for _ in regions_raw]
    for index in grid.indices():
        if not owner[index]:
            continue
        for neighbor in grid.neighbors4(index):
            if owner[neighbor] and owner[neighbor] != owner[index]:
                adjacency[owner[index] - 1].add(owner[neighbor])
    area = grid.metres_per_world_cell**2
    region_ids = tuple(physical_region_id(terrain, cells) for cells in regions_raw)
    regions: list[PhysicalRegion] = []
    for number, region_cells in enumerate(regions_raw, 1):
        mean_x = div_round_half_up(
            sum(grid.coordinate(i).x for i in region_cells), len(region_cells)
        )
        mean_y = div_round_half_up(
            sum(grid.coordinate(i).y for i in region_cells), len(region_cells)
        )
        center = min(
            region_cells,
            key=lambda i: (
                abs(grid.coordinate(i).x - mean_x) + abs(grid.coordinate(i).y - mean_y),
                i,
            ),
        )
        boundary = tuple(
            i for i in region_cells if any(owner[n] != number for n in grid.neighbors4(i))
        )
        regions.append(
            PhysicalRegion(
                region_ids[number - 1],
                region_cells,
                center,
                len(region_cells) * area,
                boundary,
                tuple(region_ids[n - 1] for n in sorted(adjacency[number - 1])),
            )
        )
    return RegionLayer(ALGORITHM_VERSION, IntGrid(grid, tuple(owner)), tuple(regions))
