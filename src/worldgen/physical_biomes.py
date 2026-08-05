"""Total ordered biome, soil, and ecological-capacity classification."""
from __future__ import annotations

from .grid import IntGrid
from .physical_models import BiomeLayer, ClimateLayer, Hydrology, Terrain

ALGORITHM_VERSION = 1
BIOME_NAMES = ("ocean", "ice", "mountain", "tundra", "desert", "grassland", "forest", "rainforest", "wetland")


def classify_physical_biomes(terrain: Terrain, hydrology: Hydrology, climate: ClimateLayer) -> BiomeLayer:
    grid = terrain.grid
    biomes: list[int] = []
    fertility: list[int] = []
    productivity: list[int] = []
    capacity: list[int] = []
    for i in grid.indices():
        if not terrain.land.values[i]: biome = 0
        elif hydrology.glacier.values[i]: biome = 1
        elif terrain.elevation_mm.values[i] > 5_000: biome = 2
        elif climate.annual_temperature_millic.values[i] < 0: biome = 3
        elif climate.annual_precipitation_mm.values[i] < 800: biome = 4
        elif hydrology.accumulation.values[i] > max(8, grid.cell_count // 100): biome = 8
        elif climate.annual_precipitation_mm.values[i] < 2_500: biome = 5
        elif climate.annual_temperature_millic.values[i] > 20_000 and climate.annual_precipitation_mm.values[i] > 5_000: biome = 7
        else: biome = 6
        biomes.append(biome)
        soil = 0 if biome == 0 else max(20_000, min(1_000_000, 650_000 - terrain.slope_ppm.values[i] * 500
                                                   + hydrology.aquifer_capacity_mm.values[i] * 100))
        fertility.append(soil)
        npp = soil * max(0, climate.annual_temperature_millic.values[i] + 20_000) // 40_000_000
        productivity.append(npp)
        capacity.append(npp * terrain.grid.metres_per_world_cell ** 2 // 1_000_000_000)
    return BiomeLayer(ALGORITHM_VERSION, IntGrid(grid, tuple(biomes)), IntGrid(grid, tuple(fertility)),
                      IntGrid(grid, tuple(productivity)), IntGrid(grid, tuple(capacity)))
