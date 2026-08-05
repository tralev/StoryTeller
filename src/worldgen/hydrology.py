"""Priority-flood hydrology and retained water-domain artifacts."""
from __future__ import annotations

import heapq

from .grid import IntGrid
from .physical_models import Hydrology, Lake, RiverEdge, Terrain

ALGORITHM_VERSION = 1


def generate_hydrology(terrain: Terrain) -> Hydrology:
    grid = terrain.grid
    filled = list(terrain.elevation_mm.values)
    visited = [False] * grid.cell_count
    heap: list[tuple[int, int]] = []
    for index in grid.indices():
        point = grid.coordinate(index)
        if point.x in (0, grid.width - 1) or point.y in (0, grid.height - 1) or not terrain.land.values[index]:
            visited[index] = True
            heapq.heappush(heap, (filled[index], index))
    while heap:
        height, index = heapq.heappop(heap)
        for neighbor in grid.neighbors4(index):
            if visited[neighbor]:
                continue
            visited[neighbor] = True
            filled[neighbor] = max(filled[neighbor], height)
            heapq.heappush(heap, (filled[neighbor], neighbor))

    flow: list[int] = []
    for index in grid.indices():
        if not terrain.land.values[index]:
            flow.append(-1)
            continue
        candidates = grid.neighbors4(index)
        target = min(candidates, key=lambda n: (filled[n], terrain.elevation_mm.values[n], n))
        flow.append(target if (filled[target], target) < (filled[index], index) else -1)
    accumulation = [1 if terrain.land.values[i] else 0 for i in grid.indices()]
    order = sorted(grid.indices(), key=lambda i: (filled[i], i), reverse=True)
    for index in order:
        if flow[index] >= 0:
            accumulation[flow[index]] += accumulation[index]

    outlets: dict[int, int] = {}
    watersheds = [0] * grid.cell_count
    for index in grid.indices():
        if not terrain.land.values[index]:
            continue
        cursor, seen = index, set()
        while flow[cursor] >= 0 and cursor not in seen:
            seen.add(cursor)
            cursor = flow[cursor]
        outlet = cursor
        if outlet not in outlets:
            outlets[outlet] = len(outlets) + 1
        watersheds[index] = outlets[outlet]
    coast = tuple(1 if terrain.land.values[i] and any(not terrain.land.values[n] for n in grid.neighbors4(i)) else 0 for i in grid.indices())
    lake_cells = [i for i in grid.indices() if terrain.land.values[i] and filled[i] > terrain.elevation_mm.values[i]]
    lakes = tuple(Lake(f"lake_{n + 1:04d}", (cell,), flow[cell] if flow[cell] >= 0 else None, filled[cell])
                  for n, cell in enumerate(lake_cells))
    threshold = max(4, grid.cell_count // 200)
    rivers = tuple(RiverEdge(i, flow[i], accumulation[i],
                             (max(1, accumulation[i] * 70 // 100),
                              max(1, accumulation[i] * 120 // 100),
                              max(1, accumulation[i] * 90 // 100),
                              max(1, accumulation[i] * 55 // 100)))
                   for i in grid.indices() if flow[i] >= 0 and accumulation[i] >= threshold)
    aquifer = tuple(max(0, 2_000 - terrain.slope_ppm.values[i]) if terrain.land.values[i] else 0 for i in grid.indices())
    salinity = tuple(35_000 if not terrain.land.values[i] else (2_000 if coast[i] else 200) for i in grid.indices())
    snow = tuple(max(0, (grid.height // 4 - min(grid.coordinate(i).y, grid.height - 1 - grid.coordinate(i).y)) * 100)
                 if terrain.land.values[i] else 0 for i in grid.indices())
    glacier = tuple(1 if snow[i] > 500 and terrain.elevation_mm.values[i] > 2_000 else 0 for i in grid.indices())
    return Hydrology(ALGORITHM_VERSION, IntGrid(grid, tuple(filled)), IntGrid(grid, tuple(flow)),
                     IntGrid(grid, tuple(accumulation)), IntGrid(grid, tuple(watersheds)),
                     IntGrid(grid, coast), IntGrid(grid, aquifer), IntGrid(grid, salinity),
                     IntGrid(grid, snow), IntGrid(grid, glacier), lakes, rivers)
