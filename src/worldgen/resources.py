"""Deterministic geology, deposits, and renewable yields."""
from __future__ import annotations

from .grid import IntGrid
from .numeric import rng_for, stable_id
from .physical_models import BiomeLayer, Deposit, ResourceLayer, Terrain

ALGORITHM_VERSION = 1
RESOURCES = ("iron", "copper", "tin", "coal", "flux_stone", "gems")


def generate_resources(terrain: Terrain, biomes: BiomeLayer, seed: int) -> ResourceLayer:
    grid = terrain.grid
    geology = tuple(0 if not terrain.land.values[i] else 1 + terrain.plate_id.values[i] % 5 for i in grid.indices())
    fault = tuple(1 if terrain.land.values[i] and any(terrain.plate_id.values[n] != terrain.plate_id.values[i]
                  for n in grid.neighbors4(i)) else 0 for i in grid.indices())
    volcano = tuple(1 if fault[i] and terrain.elevation_mm.values[i] > 4_000 and i % 17 == 0 else 0 for i in grid.indices())
    renewable = tuple(biomes.net_productivity_kg_km2.values[i] * grid.metres_per_world_cell ** 2 // 1_000_000
                      for i in grid.indices())
    rng = rng_for(seed, "physical.resources")
    deposits: list[Deposit] = []
    for i in grid.indices():
        if not terrain.land.values[i] or (rng.next_u64() % 97) != 0:
            continue
        resource = RESOURCES[(geology[i] + i) % len(RESOURCES)]
        cells = (i,) + tuple(n for n in grid.neighbors4(i) if geology[n] == geology[i])[:2]
        grade = 50_000 + rng.below(450_001)
        quantity = len(cells) * grid.metres_per_world_cell ** 2 * max(1, grade) // 100
        deposits.append(Deposit(stable_id("deposit", seed, i), resource, cells,
                                10_000 + rng.below(990_001), grade, quantity))
    strata = tuple(0 if not terrain.land.values[i] else 1 + (geology[i] * 3 + terrain.plate_id.values[i]) % 11
                   for i in grid.indices())
    parent = tuple(0 if not terrain.land.values[i] else 1 + (strata[i] + (1 if fault[i] else 0)) % 7
                   for i in grid.indices())
    return ResourceLayer(ALGORITHM_VERSION, IntGrid(grid, geology), IntGrid(grid, strata),
                         IntGrid(grid, parent), IntGrid(grid, fault), IntGrid(grid, volcano),
                         IntGrid(grid, renewable), tuple(deposits))
