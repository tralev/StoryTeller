"""Priority-flood hydrology and retained water-domain artifacts."""
from __future__ import annotations

import heapq

from .grid import GridSpec, IntGrid
from .numeric import div_floor_exact, div_round_half_up
from .physical_models import (DrainageTerminal, DrainageTerminalKind, Hydrology,
                              Lake, RiverEdge, Terrain)

ALGORITHM_VERSION = 4

# Public algorithm contract: equal D8 choices are considered clockwise from
# north. Changing this order changes canonical worlds and requires a version
# bump plus regenerated golden vectors.
D8_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, -1), (1, -1), (1, 0), (1, 1),
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
)


def d8_neighbors(grid: GridSpec, index: int) -> tuple[int, ...]:
    point = grid.coordinate(index)
    return tuple(
        grid.index(point.x + dx, point.y + dy)
        for dx, dy in D8_OFFSETS
        if 0 <= point.x + dx < grid.width and 0 <= point.y + dy < grid.height
    )


def priority_flood(
    grid: GridSpec, elevations: tuple[int, ...], outlets: tuple[bool, ...],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Fill depressions and return deterministic parent and discovery ranks."""
    if len(elevations) != grid.cell_count or len(outlets) != grid.cell_count:
        raise ValueError("WG-HYDROLOGY-FLOOD: input coverage mismatch")
    filled = list(elevations)
    parent = [-1] * grid.cell_count
    rank = [-1] * grid.cell_count
    visited = [False] * grid.cell_count
    heap: list[tuple[int, int]] = []
    next_rank = 0
    for index in grid.indices():
        point = grid.coordinate(index)
        if (point.x in (0, grid.width - 1) or point.y in (0, grid.height - 1)
                or outlets[index]):
            visited[index] = True
            rank[index] = next_rank
            next_rank += 1
            heapq.heappush(heap, (filled[index], index))
    while heap:
        height, index = heapq.heappop(heap)
        for neighbor in d8_neighbors(grid, index):
            if visited[neighbor]:
                continue
            visited[neighbor] = True
            parent[neighbor] = index
            rank[neighbor] = next_rank
            next_rank += 1
            filled[neighbor] = max(filled[neighbor], height)
            heapq.heappush(heap, (filled[neighbor], neighbor))
    if any(value < 0 for value in rank):
        raise ValueError("WG-HYDROLOGY-FLOOD: unreachable cell")
    return tuple(filled), tuple(parent), tuple(rank)


def route_d8(
    grid: GridSpec, elevations: tuple[int, ...], filled: tuple[int, ...],
    parent: tuple[int, ...], rank: tuple[int, ...], land: tuple[int, ...],
) -> tuple[int, ...]:
    """Route each land cell downhill, using flood ancestry across filled flats."""
    flow: list[int] = []
    for index in grid.indices():
        if not land[index]:
            flow.append(-1)
            continue
        neighbors = d8_neighbors(grid, index)
        lower = [neighbor for neighbor in neighbors if filled[neighbor] < filled[index]]
        if lower:
            direction = {neighbor: order for order, neighbor in enumerate(neighbors)}
            flow.append(min(lower, key=lambda neighbor: (
                filled[neighbor], elevations[neighbor], direction[neighbor], neighbor,
            )))
        else:
            target = parent[index]
            flow.append(target if target >= 0 and rank[target] < rank[index] else -1)
    return tuple(flow)


def connected_lakes(
    grid: GridSpec, elevations: tuple[int, ...], filled: tuple[int, ...],
    flow: tuple[int, ...], land: tuple[int, ...],
) -> tuple[Lake, ...]:
    """Group equal-surface depressed cells and select one canonical spillway."""
    remaining = {
        index for index in grid.indices()
        if land[index] and filled[index] > elevations[index]
    }
    bodies: list[tuple[int, ...]] = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        stack = [start]
        body: set[int] = set()
        while stack:
            cell = stack.pop()
            body.add(cell)
            for neighbor in d8_neighbors(grid, cell):
                if neighbor in remaining and filled[neighbor] == filled[start]:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        bodies.append(tuple(sorted(body)))
    lakes: list[Lake] = []
    for number, cells in enumerate(sorted(bodies, key=lambda body: body[0]), 1):
        body = set(cells)
        exits = [
            (cell, flow[cell]) for cell in cells
            if flow[cell] >= 0 and flow[cell] not in body
        ]
        spillway, outlet = (None, None)
        if exits:
            spillway, outlet = min(exits, key=lambda edge: (
                filled[edge[1]], elevations[edge[1]], edge[0], edge[1],
            ))
        lakes.append(Lake(
            f"lake_{number:04d}", cells, spillway, outlet, filled[cells[0]],
        ))
    return tuple(lakes)


def generate_hydrology(terrain: Terrain) -> Hydrology:
    grid = terrain.grid
    ocean_outlets = tuple(not value for value in terrain.land.values)
    filled, parent, flood_rank = priority_flood(
        grid, terrain.elevation_mm.values, ocean_outlets,
    )
    flow = route_d8(
        grid, terrain.elevation_mm.values, filled, parent, flood_rank,
        terrain.land.values,
    )
    accumulation = [1 if terrain.land.values[i] else 0 for i in grid.indices()]
    order = sorted(grid.indices(), key=lambda i: (filled[i], flood_rank[i]), reverse=True)
    for index in order:
        if flow[index] >= 0:
            accumulation[flow[index]] += accumulation[index]

    terminals = [-1] * grid.cell_count
    for index in grid.indices():
        if not terrain.land.values[index]:
            continue
        cursor, seen = index, set()
        while flow[cursor] >= 0 and cursor not in seen:
            seen.add(cursor)
            cursor = flow[cursor]
        terminals[index] = cursor
    outlet_ids = {
        outlet: number for number, outlet in enumerate(
            sorted({terminals[index] for index in grid.indices() if terrain.land.values[index]}), 1,
        )
    }
    watersheds = [
        outlet_ids[terminals[index]] if terrain.land.values[index] else 0
        for index in grid.indices()
    ]
    terminal_records = tuple(
        DrainageTerminal(
            f"terminal_{watershed_id:04d}", outlet,
            (DrainageTerminalKind.OCEAN if not terrain.land.values[outlet]
             else DrainageTerminalKind.CLOSED_BASIN),
            watershed_id,
        )
        for outlet, watershed_id in sorted(outlet_ids.items(), key=lambda item: item[1])
    )
    coast = tuple(1 if terrain.land.values[i] and any(not terrain.land.values[n] for n in grid.neighbors4(i)) else 0 for i in grid.indices())
    lakes = connected_lakes(
        grid, terrain.elevation_mm.values, filled, flow, terrain.land.values,
    )
    threshold = max(4, div_floor_exact(grid.cell_count, 200))
    rivers = tuple(RiverEdge(i, flow[i], accumulation[i],
                             (max(1, div_round_half_up(accumulation[i] * 70, 100)),
                              max(1, div_round_half_up(accumulation[i] * 120, 100)),
                              max(1, div_round_half_up(accumulation[i] * 90, 100)),
                              max(1, div_round_half_up(accumulation[i] * 55, 100))))
                   for i in grid.indices() if flow[i] >= 0 and accumulation[i] >= threshold)
    delta = tuple(
        1 if (coast[i] and flow[i] >= 0 and not terrain.land.values[flow[i]]
              and accumulation[i] >= threshold) else 0
        for i in grid.indices()
    )
    aquifer = tuple(max(0, 2_000 - terrain.slope_ppm.values[i]) if terrain.land.values[i] else 0 for i in grid.indices())
    salinity = tuple(35_000 if not terrain.land.values[i] else (2_000 if coast[i] else 200) for i in grid.indices())
    snow_line = div_floor_exact(grid.height, 4)
    snow = tuple(max(0, (snow_line - min(grid.coordinate(i).y, grid.height - 1 - grid.coordinate(i).y)) * 100)
                 if terrain.land.values[i] else 0 for i in grid.indices())
    glacier = tuple(1 if snow[i] > 500 and terrain.elevation_mm.values[i] > 2_000 else 0 for i in grid.indices())
    return Hydrology(ALGORITHM_VERSION, IntGrid(grid, filled), IntGrid(grid, flow),
                     IntGrid(grid, tuple(accumulation)), IntGrid(grid, tuple(watersheds)),
                     IntGrid(grid, coast), IntGrid(grid, aquifer), IntGrid(grid, salinity),
                     IntGrid(grid, snow), IntGrid(grid, glacier), IntGrid(grid, delta),
                     terminal_records, lakes, rivers)
