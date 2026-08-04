"""Terrain generation — elevation + temperature maps from seed.

Produces a 2D grid of elevation and temperature values using
deterministic noise functions. Conceptually inspired by Dwarf
Fortress-style layered world generation.
"""

from __future__ import annotations

from .models import GridCell, WorldRNG


def generate_terrain(
    width: int,
    height: int,
    seed: int,
    land_fraction: float = 0.45,
) -> list[list[GridCell]]:
    """Generate a terrain grid with elevation and temperature.

    Elevation is produced by layered noise at multiple octaves.
    Temperature varies with latitude (north=cold, south=warm) plus
    elevation-based cooling.

    Args:
        width: Grid width in cells.
        height: Grid height in cells.
        seed: Deterministic seed.
        land_fraction: Fraction of cells that should be above water (~0.45).

    Returns:
        2D list of GridCell objects with elevation and temperature set.
    """
    rng = WorldRNG(seed)

    # Generate raw elevation with layered noise
    raw: list[list[float]] = []
    for y in range(height):
        row: list[float] = []
        for x in range(width):
            # Three octaves of smooth noise
            n1 = rng.noise_2d_smooth(x, y, scale=8.0)
            n2 = rng.noise_2d_smooth(x, y, scale=16.0) * 0.5
            n3 = rng.noise_2d_smooth(x, y, scale=32.0) * 0.25
            n4 = rng.noise_2d_smooth(x, y, scale=4.0) * 0.15
            row.append(n1 + n2 + n3 + n4)
        raw.append(row)

    # Find the sea-level threshold so ~land_fraction is above water
    all_values = sorted(v for row in raw for v in row)
    sea_level_idx = int(len(all_values) * (1.0 - land_fraction))
    sea_level = all_values[max(0, min(sea_level_idx, len(all_values) - 1))]

    # Normalize and classify
    grid: list[list[GridCell]] = []
    for y in range(height):
        cell_row: list[GridCell] = []
        for x in range(width):
            # Normalize: -1 (deep) to 1 (peak)
            e = raw[y][x]
            normalized = (e - sea_level) / max(0.5, 1.0 - sea_level)
            normalized = max(-1.0, min(1.0, normalized))

            # Temperature: latitude gradient + elevation cooling
            lat_factor = 1.0 - 2.0 * (y / max(1, height - 1))  # 1 at north, -1 at south
            temp = lat_factor * 0.8 - normalized * 0.3  # Higher=colder
            temp = max(-1.0, min(1.0, temp))  # Clamp

            cell_row.append(GridCell(elevation=normalized, temperature=temp))
        grid.append(cell_row)

    return grid
