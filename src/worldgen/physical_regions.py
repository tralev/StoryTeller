"""Barrier-aware deterministic physical-region partitioning."""
from __future__ import annotations

from collections import deque

from .grid import IntGrid
from .physical_models import BiomeLayer, Hydrology, PhysicalRegion, RegionLayer, Terrain

ALGORITHM_VERSION = 1


def generate_regions(terrain: Terrain, hydrology: Hydrology, biomes: BiomeLayer) -> RegionLayer:
    grid = terrain.grid
    owner = [0] * grid.cell_count
    regions_raw: list[tuple[int, ...]] = []
    for start in grid.indices():
        if not terrain.land.values[start] or owner[start]:
            continue
        number = len(regions_raw) + 1
        queue = deque([start])
        owner[start] = number
        collected: list[int] = []
        while queue:
            index = queue.popleft()
            collected.append(index)
            for neighbor in grid.neighbors4(index):
                if owner[neighbor] or not terrain.land.values[neighbor]:
                    continue
                # Watershed and biome boundaries are authoritative barriers.
                if biomes.biome_id.values[neighbor] != biomes.biome_id.values[index]:
                    continue
                if hydrology.watershed_id.values[neighbor] != hydrology.watershed_id.values[index]:
                    continue
                owner[neighbor] = number
                queue.append(neighbor)
        region_cells = tuple(sorted(collected))
        regions_raw.append(region_cells)
    adjacency: list[set[int]] = [set() for _ in regions_raw]
    for index in grid.indices():
        if not owner[index]:
            continue
        for neighbor in grid.neighbors4(index):
            if owner[neighbor] and owner[neighbor] != owner[index]:
                adjacency[owner[index] - 1].add(owner[neighbor])
    area = grid.metres_per_world_cell ** 2
    regions: list[PhysicalRegion] = []
    for number, cells in enumerate(regions_raw, 1):
        mean_x = sum(grid.coordinate(i).x for i in cells) // len(cells)
        mean_y = sum(grid.coordinate(i).y for i in cells) // len(cells)
        center = min(cells, key=lambda i: (abs(grid.coordinate(i).x - mean_x)
                                            + abs(grid.coordinate(i).y - mean_y), i))
        boundary = tuple(i for i in cells if any(owner[n] != number for n in grid.neighbors4(i)))
        regions.append(PhysicalRegion(f"region_{number:05d}", cells, center, len(cells) * area,
                                      boundary, tuple(f"region_{n:05d}" for n in sorted(adjacency[number - 1]))))
    return RegionLayer(ALGORITHM_VERSION, IntGrid(grid, tuple(owner)), tuple(regions))
