"""Immutable soil fields derived before biome classification."""
from __future__ import annotations

from .grid import IntGrid
from .numeric import div_round_half_up
from .physical_models import ClimateLayer, GeologyLayer, Hydrology, SoilLayer, Terrain

ALGORITHM_VERSION = 1


def generate_soil(
    terrain: Terrain, geology: GeologyLayer, hydrology: Hydrology,
    climate: ClimateLayer,
) -> SoilLayer:
    grid = terrain.grid
    depth: list[int] = []
    fertility: list[int] = []
    drainage: list[int] = []
    erosion: list[int] = []
    for index in grid.indices():
        if not terrain.land.values[index]:
            depth.append(0); fertility.append(0); drainage.append(0); erosion.append(0)
            continue
        slope = terrain.slope_ppm.values[index]
        rain = climate.annual_precipitation_mm.values[index]
        aquifer = hydrology.aquifer_capacity_mm.values[index]
        soil_depth = max(100, min(5_000, 3_500 - div_round_half_up(slope, 4)))
        soil_drainage = max(0, min(1_000_000,
            slope * 400 + max(0, 2_000 - aquifer) * 250,
        ))
        parent_bonus = geology.parent_material_id.values[index] * 25_000
        soil_fertility = max(20_000, min(1_000_000,
            500_000 + parent_bonus + min(250_000, rain * 40)
            - div_round_half_up(soil_drainage, 3),
        ))
        pressure = slope * 300 + rain * 50
        erosion_class = 3 if pressure >= 750_000 else 2 if pressure >= 300_000 else 1
        depth.append(soil_depth)
        fertility.append(soil_fertility)
        drainage.append(soil_drainage)
        erosion.append(erosion_class)
    return SoilLayer(
        ALGORITHM_VERSION, IntGrid(grid, tuple(depth)), IntGrid(grid, tuple(fertility)),
        IntGrid(grid, tuple(drainage)), IntGrid(grid, tuple(erosion)),
    )
