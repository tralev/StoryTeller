"""Deterministic species, food-web, migration, and extinction model."""
from __future__ import annotations

from .numeric import stable_id
from .physical_models import BiomeLayer, EcologyLayer, FoodWebEdge, RegionLayer, Species

ALGORITHM_VERSION = 1


def generate_ecology(biomes: BiomeLayer, regions: RegionLayer, seed: int) -> EcologyLayer:
    present = sorted(set(biomes.biome_id.values) - {0})
    species: list[Species] = []
    for biome in present:
        base_energy = sum(biomes.net_productivity_kg_km2.values[i]
                          for i, value in enumerate(biomes.biome_id.values) if value == biome)
        for level, divisor in ((1, 1), (2, 10), (3, 100)):
            energy = base_energy // divisor
            species.append(Species(stable_id("species", seed, biome, level), level, (biome,),
                                   energy, energy == 0))
    by = {(item.habitat_biomes[0], item.trophic_level): item for item in species}
    food_web: list[FoodWebEdge] = []
    for biome in present:
        for level in (2, 3):
            predator, prey = by[(biome, level)], by[(biome, level - 1)]
            transfer = min(predator.annual_energy_kj, prey.annual_energy_kj // 10)
            food_web.append(FoodWebEdge(predator.species_id, prey.species_id, transfer))
    corridors = tuple(tuple(sorted(region.cells)) for region in regions.regions
                      if len(region.cells) > 1 and region.neighbors)
    return EcologyLayer(ALGORITHM_VERSION, tuple(species), tuple(food_web), corridors)
