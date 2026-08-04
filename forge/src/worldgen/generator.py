"""WorldGenerator — orchestrates the full procedural world pipeline.

Tie together terrain → climate → biomes → regions → civilizations
into a single deterministic WorldSnapshot.
"""

from __future__ import annotations

from .biomes import classify_biomes
from .civilizations import generate_civilizations
from .climate import generate_climate
from .models import WorldSnapshot
from .regions import segment_regions
from .terrain import generate_terrain


def generate_world(
    seed: int,
    width: int = 64,
    height: int = 64,
    max_civs: int = 4,
    history_years: int = 200,
    land_fraction: float = 0.45,
) -> WorldSnapshot:
    """Generate a complete procedural world from a single seed.

    Pipeline:
      1. Terrain: elevation + temperature from layered noise
      2. Climate: precipitation + drainage + rivers
      3. Biomes: classify each cell
      4. Regions: flood-fill into contiguous named regions
      5. Civilizations: placement + population simulation + history

    Args:
        seed: Deterministic seed — same seed = same world.
        width: Grid width (16-512).
        height: Grid height (16-512).
        max_civs: Maximum civilizations to generate.
        history_years: Years of simulated history.
        land_fraction: Target fraction of land cells (0.0-1.0).

    Returns:
        Complete WorldSnapshot with regions, sites, civilizations, history.
    """
    # 1. Terrain
    grid = generate_terrain(width, height, seed, land_fraction)

    # 2. Climate
    generate_climate(grid, seed)

    # 3. Biomes
    classify_biomes(grid)

    # 4. Regions
    regions = segment_regions(grid, seed)

    # 5. Civilizations
    civs, sites, history = generate_civilizations(regions, seed, max_civs, history_years)

    return WorldSnapshot(
        schema_version=1,
        seed=seed,
        dimensions={"width": width, "height": height},
        regions=regions,
        sites=sites,
        civilizations=civs,
        history=history,
    )
