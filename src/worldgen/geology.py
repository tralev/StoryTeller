"""Typed deterministic geology derived from tectonic terrain."""

from __future__ import annotations

from .grid import IntGrid
from .physical_models import GeologyLayer, PlateBoundaryClass, Terrain

ALGORITHM_VERSION = 1


def generate_geology(terrain: Terrain) -> GeologyLayer:
    grid = terrain.grid
    rock = tuple(
        0 if not terrain.land.values[i] else 1 + terrain.plate_id.values[i] % 5
        for i in grid.indices()
    )
    fault = tuple(
        1 if terrain.plate_boundary.values[i] != PlateBoundaryClass.INTERIOR else 0
        for i in grid.indices()
    )
    volcano = tuple(
        1
        if (
            terrain.land.values[i]
            and terrain.plate_boundary.values[i] == PlateBoundaryClass.CONVERGENT
            and terrain.elevation_mm.values[i] > 4_000
            and i % 17 == 0
        )
        else 0
        for i in grid.indices()
    )
    strata = tuple(
        0 if not terrain.land.values[i] else 1 + (rock[i] * 3 + terrain.plate_id.values[i]) % 11
        for i in grid.indices()
    )
    parent = tuple(
        0 if not terrain.land.values[i] else 1 + (strata[i] + fault[i]) % 7 for i in grid.indices()
    )
    relief = tuple(
        1_000
        if value == PlateBoundaryClass.CONVERGENT
        else -300
        if value == PlateBoundaryClass.DIVERGENT
        else 200
        if value == PlateBoundaryClass.TRANSFORM
        else 0
        for value in terrain.plate_boundary.values
    )
    return GeologyLayer(
        ALGORITHM_VERSION,
        IntGrid(grid, rock),
        IntGrid(grid, strata),
        IntGrid(grid, parent),
        IntGrid(grid, fault),
        IntGrid(grid, volcano),
        IntGrid(grid, relief),
    )
