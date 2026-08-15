"""Deterministic geology, deposits, and renewable yields."""
from __future__ import annotations

from .grid import IntGrid
from .numeric import div_round_half_up, identity, rng_for_decision, stable_id
from .geology import generate_geology
from .physical_models import BiomeLayer, Deposit, GeologyLayer, ResourceLayer, Terrain
from .registries import material_densities

ALGORITHM_VERSION = 2
RESOURCE_DENSITY_KG_M2 = material_densities()
RESOURCES = tuple(RESOURCE_DENSITY_KG_M2)


def _resource_for_cell(geology: GeologyLayer, index: int) -> str:
    if geology.volcano.values[index]:
        return "gems"
    if geology.fault.values[index]:
        return "copper" if geology.rock_class_id.values[index] % 2 == 0 else "tin"
    return {1: "coal", 2: "iron", 3: "flux_stone", 4: "copper", 5: "iron"}[
        geology.rock_class_id.values[index]
    ]


def _deposit_body(
    terrain: Terrain, geology: GeologyLayer, start: int, target_size: int,
    occupied: set[int],
) -> tuple[int, ...]:
    grid = terrain.grid
    rock = geology.rock_class_id.values[start]
    strata = geology.strata_id.values[start]
    body: set[int] = {start}
    frontier = [start]
    while frontier and len(body) < target_size:
        current = frontier.pop(0)
        for neighbor in grid.neighbors4(current):
            if (neighbor in body or neighbor in occupied or not terrain.land.values[neighbor]
                    or geology.rock_class_id.values[neighbor] != rock
                    or geology.strata_id.values[neighbor] != strata):
                continue
            body.add(neighbor)
            frontier.append(neighbor)
            if len(body) == target_size:
                break
    return tuple(sorted(body))


def generate_resources(
    terrain: Terrain, biomes: BiomeLayer, seed: int, geology: GeologyLayer | None = None,
) -> ResourceLayer:
    grid = terrain.grid
    geology_layer = geology or generate_geology(terrain)
    rock = geology_layer.rock_class_id.values
    renewable = tuple(div_round_half_up(
        biomes.net_productivity_kg_km2.values[i] * grid.metres_per_world_cell ** 2,
        1_000_000,
    )
                      for i in grid.indices())
    deposits: list[Deposit] = []
    occupied: set[int] = set()
    for i in grid.indices():
        entity_id = f"cell:{i}"
        if i in occupied or not terrain.land.values[i] or (
            rng_for_decision(
                seed, "physical.resources", entity_id, "deposit_presence",
            ).next_u64() % 97
        ) != 0:
            continue
        body_size = 2 + rng_for_decision(
            seed, "physical.resources", entity_id, "deposit_body_size",
        ).below(5)
        cells = _deposit_body(terrain, geology_layer, i, body_size, occupied)
        if len(cells) < 2:
            continue
        fault_related = any(geology_layer.fault.values[cell] for cell in cells)
        volcanic_related = any(geology_layer.volcano.values[cell] for cell in cells)
        resource = ("gems" if volcanic_related else
                    ("copper" if rock[i] % 2 == 0 else "tin") if fault_related else
                    _resource_for_cell(geology_layer, i))
        grade = 50_000 + rng_for_decision(
            seed, "physical.resources", entity_id, "deposit_grade",
        ).below(450_001)
        quantity = div_round_half_up(
            len(cells) * grid.metres_per_world_cell ** 2
            * RESOURCE_DENSITY_KG_M2[resource] * grade, 1_000_000,
        )
        deposits.append(Deposit(stable_id("deposit", seed, identity("cell", i)), resource, cells,
                                10_000 + rng_for_decision(
                                    seed, "physical.resources", entity_id,
                                    "deposit_depth",
                                ).below(990_001), grade, quantity,
                                rock[i], geology_layer.strata_id.values[i],
                                fault_related, volcanic_related))
        occupied.update(cells)
    return ResourceLayer(ALGORITHM_VERSION, geology_layer.rock_class_id, geology_layer.strata_id,
                         geology_layer.parent_material_id, geology_layer.fault, geology_layer.volcano,
                         IntGrid(grid, renewable), tuple(deposits))
