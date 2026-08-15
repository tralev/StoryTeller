"""Deterministic species, food-web, migration, and extinction model."""
from __future__ import annotations

from .numeric import div_round_half_up, identity, rng_for_decision, stable_id
from .physical_models import (BiomeLayer, EcologyLayer, EcologyTransition, FoodWebEdge,
                              RegionalSpeciesPopulation, RegionLayer, Species)

ALGORITHM_VERSION = 2
SIMULATED_YEARS = 4


def generate_ecology(biomes: BiomeLayer, regions: RegionLayer, seed: int) -> EcologyLayer:
    present = sorted(set(biomes.biome_id.values) - {0})
    species: list[Species] = []
    for biome in present:
        base_energy = sum(biomes.net_productivity_kg_km2.values[i]
                          for i, value in enumerate(biomes.biome_id.values) if value == biome)
        for level, divisor in ((1, 1), (2, 10), (3, 100)):
            energy = div_round_half_up(base_energy, divisor)
            species.append(Species(stable_id(
                "species", seed, identity("biome_id", biome), identity("trophic_level", level),
            ), level, (biome,),
                                   energy, energy == 0))
    by = {(item.habitat_biomes[0], item.trophic_level): item for item in species}
    food_web: list[FoodWebEdge] = []
    for biome in present:
        for level in (2, 3):
            predator, prey = by[(biome, level)], by[(biome, level - 1)]
            transfer = min(
                predator.annual_energy_kj,
                div_round_half_up(prey.annual_energy_kj, 10),
            )
            food_web.append(FoodWebEdge(predator.species_id, prey.species_id, transfer))
    corridors = tuple(tuple(sorted(region.cells)) for region in regions.regions
                      if len(region.cells) > 1 and region.neighbors)
    region_by_id = {region.region_id: region for region in regions.regions}
    capacities: dict[tuple[str, str], tuple[int, int]] = {}
    populations: dict[tuple[str, str], int] = {}
    for item in species:
        divisor = 10 ** (item.trophic_level - 1)
        habitat = set(item.habitat_biomes)
        for region in regions.regions:
            suitable = tuple(cell for cell in region.cells if biomes.biome_id.values[cell] in habitat)
            suitability = div_round_half_up(len(suitable) * 1_000_000, len(region.cells))
            capacity = div_round_half_up(
                sum(biomes.carrying_capacity.values[cell] for cell in suitable), divisor,
            )
            key = (item.species_id, region.region_id)
            capacities[key] = (suitability, capacity)
            if capacity:
                rng = rng_for_decision(seed, "ecology_population", item.species_id, region.region_id)
                populations[key] = div_round_half_up(capacity * (700_000 + rng.below(500_001)),
                                                     1_000_000)
            else:
                populations[key] = 0

    ledger: list[EcologyTransition] = []
    for year in range(1, SIMULATED_YEARS + 1):
        before = dict(populations)
        births: dict[tuple[str, str], int] = {}
        deaths: dict[tuple[str, str], int] = {}
        immigrants = {key: 0 for key in before}
        emigrants = {key: 0 for key in before}
        for key, value in sorted(before.items()):
            capacity = capacities[key][1]
            births[key] = (div_round_half_up((capacity - value) * 120_000, 1_000_000)
                           if value < capacity else 0)
            deaths[key] = (div_round_half_up((value - capacity) * 400_000, 1_000_000)
                           if value > capacity else 0)
        # Migration is synchronous and conservative. Only population above capacity moves,
        # along one canonical region edge, into habitat with spare capacity.
        for item in species:
            for source_id in sorted(region_by_id):
                source_key = (item.species_id, source_id)
                available = max(0, before[source_key] - capacities[source_key][1] - deaths[source_key])
                if not available:
                    continue
                targets = []
                for target_id in region_by_id[source_id].neighbors:
                    target_key = (item.species_id, target_id)
                    spare = max(0, capacities[target_key][1] - before[target_key] - births[target_key]
                                - immigrants[target_key])
                    if spare:
                        targets.append((target_id, spare))
                if targets:
                    target_id, spare = min(targets)
                    moved = min(available, spare)
                    emigrants[source_key] += moved
                    immigrants[(item.species_id, target_id)] += moved
        for key in sorted(before):
            after = max(0, before[key] + births[key] - deaths[key]
                        + immigrants[key] - emigrants[key])
            populations[key] = after
            ledger.append(EcologyTransition(year, key[0], key[1], before[key], births[key],
                                            deaths[key], immigrants[key], emigrants[key], after))

    regional = tuple(
        RegionalSpeciesPopulation(species_id, region_id, capacities[(species_id, region_id)][0],
                                  capacities[(species_id, region_id)][1], value, value == 0)
        for (species_id, region_id), value in sorted(populations.items())
    )
    living = {item.species_id for item in regional if item.population}
    final_species = tuple(Species(item.species_id, item.trophic_level, item.habitat_biomes,
                                  item.annual_energy_kj, item.species_id not in living)
                          for item in species)
    return EcologyLayer(ALGORITHM_VERSION, final_species, tuple(food_web), corridors,
                        regional, tuple(ledger))
