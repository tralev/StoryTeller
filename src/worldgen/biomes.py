"""Biome classification from temperature + precipitation.

Maps each cell to a biome based on its climate attributes.
Also classifies elevation bands.
"""

from __future__ import annotations

from .models import Biome, Climate, Elevation, GridCell


def classify_biomes(grid: list[list[GridCell]]) -> None:
    """Set biome, elevation_class, and climate_class on each cell (mutates grid)."""
    for row in grid:
        for cell in row:
            _classify_cell(cell)


def _classify_cell(cell: GridCell) -> None:
    """Classify a single cell's biome."""
    t = cell.temperature  # -1 (cold) to 1 (hot)
    p = cell.precipitation  # 0 (dry) to 1 (wet)
    e = cell.elevation  # -1 (deep) to 1 (peak)

    # Water cells (below sea level)
    if e <= -0.05:
        cell.biome = ""
        return

    # Mountain override
    if e > 0.65:
        cell.biome = Biome.MOUNTAIN.value
        return
    if e > 0.4:
        cell.biome = Biome.HIGHLAND.value
        return

    # Climate zones by temperature
    if t < -0.5:  # Arctic / cold
        if p > 0.4:
            cell.biome = Biome.TAIGA.value
        else:
            cell.biome = Biome.TUNDRA.value
    elif t < 0.0:  # Cool temperate
        if p > 0.5:
            cell.biome = Biome.TEMPERATE_FOREST.value
        elif p > 0.25:
            cell.biome = Biome.TEMPERATE_GRASSLAND.value
        else:
            cell.biome = Biome.DESERT.value
    elif t < 0.4:  # Warm temperate
        if p > 0.5:
            cell.biome = Biome.TROPICAL_FOREST.value
        elif p > 0.25:
            cell.biome = Biome.SAVANNA.value
        else:
            cell.biome = Biome.DESERT.value
    else:  # Hot / tropical
        if p > 0.5:
            cell.biome = Biome.TROPICAL_FOREST.value
        elif p > 0.15:
            cell.biome = Biome.SAVANNA.value
        else:
            cell.biome = Biome.DESERT.value

    # Wetland override
    if cell.is_river and p > 0.4:
        cell.biome = Biome.WETLAND.value

    # Coastal override
    if cell.is_coastal and cell.biome not in (Biome.MOUNTAIN.value,):
        if p > 0.3:
            cell.biome = Biome.COASTAL.value
