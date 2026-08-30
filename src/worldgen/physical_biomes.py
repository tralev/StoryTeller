"""Total ordered biome, soil, and ecological-capacity classification."""

from __future__ import annotations

from .grid import IntGrid
from .numeric import div_round_half_up
from .physical_models import BiomeLayer, ClimateLayer, Hydrology, SoilLayer, Terrain
from .registries import biome_rule_order, registry_entries

ALGORITHM_VERSION = 1
BIOME_NAMES = tuple(str(entry["name"]) for entry in registry_entries("biomes"))
BIOME_RULE_ORDER = biome_rule_order()


def classify_biome_cell(
    *,
    land: int,
    glacier: int,
    elevation_mm: int,
    temperature_millic: int,
    precipitation_mm: int,
    drainage_ppm: int,
) -> int:
    """Apply the frozen first-match table; the final forest rule is total."""
    if not land:
        return 0
    if glacier:
        return 1
    if elevation_mm > 5_000:
        return 2
    if temperature_millic < 0:
        return 3
    if precipitation_mm < 800:
        return 4
    if drainage_ppm < 250_000 and precipitation_mm >= 3_000:
        return 8
    if precipitation_mm < 2_500:
        return 5
    if temperature_millic > 20_000 and precipitation_mm > 5_000:
        return 7
    return 6


def classify_physical_biomes(
    terrain: Terrain,
    hydrology: Hydrology,
    climate: ClimateLayer,
    soil: SoilLayer,
) -> BiomeLayer:
    grid = terrain.grid
    biomes: list[int] = []
    productivity: list[int] = []
    capacity: list[int] = []
    for i in grid.indices():
        biome = classify_biome_cell(
            land=terrain.land.values[i],
            glacier=hydrology.glacier.values[i],
            elevation_mm=terrain.elevation_mm.values[i],
            temperature_millic=climate.annual_temperature_millic.values[i],
            precipitation_mm=climate.annual_precipitation_mm.values[i],
            drainage_ppm=soil.drainage_ppm.values[i],
        )
        biomes.append(biome)
        npp = div_round_half_up(
            soil.fertility_ppm.values[i]
            * max(0, climate.annual_temperature_millic.values[i] + 20_000),
            40_000_000,
        )
        productivity.append(npp)
        capacity.append(
            div_round_half_up(
                npp * terrain.grid.metres_per_world_cell**2,
                1_000_000_000,
            )
        )
    return BiomeLayer(
        ALGORITHM_VERSION,
        IntGrid(grid, tuple(biomes)),
        IntGrid(grid, tuple(productivity)),
        IntGrid(grid, tuple(capacity)),
    )
