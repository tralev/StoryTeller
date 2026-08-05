"""Deterministic sparse 3D site maps derived from macro facts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..world.views import WorldView
from .numeric import rng_for, stable_id


@dataclass(frozen=True)
class LocalFeature:
    feature_id: str
    kind: str
    cells: tuple[tuple[int, int, int], ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocalSiteMap:
    algorithm_version: int
    site_id: str
    width: int
    height: int
    z_levels: int
    macro_cell: int
    strata: tuple[int, ...]
    surface_height: tuple[int, ...]
    features: tuple[LocalFeature, ...]


def generate_local_maps(world: WorldView) -> tuple[LocalSiteMap, ...]:
    spec = world.payload("world_index")["spec"]
    width, height, z_levels = int(spec["local_site_width"]), int(spec["local_site_height"]), int(spec["local_z_levels"])
    geology = world.payload("resources")
    maps: list[LocalSiteMap] = []
    for site in world.sites():
        cell = int(site.value["cell"])
        rng = rng_for(int(world.payload("world_index")["seed"]), "local_map", site.fact_id)
        strata = tuple(1 + (int(geology["strata_id"]["values"][cell]) + z) % 11 for z in range(z_levels))
        surface = tuple(z_levels // 2 + rng.below(3) - 1 for _ in range(width * height))
        center = (width // 2, height // 2, z_levels // 2)
        road = tuple((x, center[1], center[2]) for x in range(width))
        stairs = tuple((center[0], center[1], z) for z in range(max(0, center[2] - 4), center[2] + 1))
        cave = tuple((center[0] + dx, center[1] + (dx % 2), center[2] - 4) for dx in range(-4, 5))
        water = tuple((center[0] + dx, center[1] + 6, center[2] - 5) for dx in range(-3, 4))
        building = ((center[0], center[1], center[2]), (center[0] + 1, center[1], center[2]))
        features = (
            LocalFeature(stable_id("feature", cell, "road"), "road", road, site.source_ids),
            LocalFeature(stable_id("feature", cell, "stairs"), "vertical_stairs", stairs, site.source_ids),
            LocalFeature(stable_id("feature", cell, "cave"), "sealed_cave", cave, site.source_ids),
            LocalFeature(stable_id("feature", cell, "aquifer"), "aquifer_water", water, site.source_ids),
            LocalFeature(stable_id("feature", cell, "building"), "supported_building", building, site.source_ids),
            LocalFeature(stable_id("feature", cell, "workshop"), "workshop", (building[0],), site.source_ids),
            LocalFeature(stable_id("feature", cell, "stockpile"), "stockpile", (building[1],), site.source_ids),
            LocalFeature(stable_id("feature", cell, "deposit"), "mineral_deposit", (cave[0], cave[-1]),
                         (world.artifact_ids["resources"],)),
            LocalFeature(stable_id("feature", cell, "magma"), "sealed_magma", ((center[0], center[1], 1),),
                         (world.artifact_ids["geology"],)),
            LocalFeature(stable_id("feature", cell, "heat"), "heat_zone", ((center[0], center[1], 2),),
                         (world.artifact_ids["climate"],)),
            LocalFeature(stable_id("feature", cell, "support"), "structural_support", (building[0], building[1]),
                         site.source_ids),
            LocalFeature(stable_id("feature", cell, "parcel"), "parcel", tuple(
                (center[0] + dx, center[1] + dy, center[2]) for dx in range(-2, 3) for dy in range(-2, 3)
            ), site.source_ids),
            LocalFeature(stable_id("feature", cell, "scar"), "event_scar", ((center[0] - 2, center[1], center[2]),),
                         (world.artifact_ids["history"],)),
        )
        maps.append(LocalSiteMap(1, site.fact_id, width, height, z_levels, cell, strata, surface, features))
    return tuple(maps)


def validate_local_map(local: LocalSiteMap) -> None:
    if len(local.surface_height) != local.width * local.height or len(local.strata) != local.z_levels:
        raise ValueError("LOCAL-COVERAGE: incomplete local geometry")
    for feature in local.features:
        for x, y, z in feature.cells:
            if not (0 <= x < local.width and 0 <= y < local.height and 0 <= z < local.z_levels):
                raise ValueError("LOCAL-BOUNDS: feature outside local map")
    kinds = {feature.kind for feature in local.features}
    required = {"road", "vertical_stairs", "sealed_cave", "aquifer_water", "supported_building",
                "workshop", "stockpile", "mineral_deposit", "sealed_magma", "heat_zone",
                "structural_support", "parcel", "event_scar"}
    if not required <= kinds:
        raise ValueError("LOCAL-FEATURES: required systems missing")
    stairs = next(feature for feature in local.features if feature.kind == "vertical_stairs")
    if any(abs(a[2] - b[2]) != 1 for a, b in zip(stairs.cells, stairs.cells[1:])):
        raise ValueError("LOCAL-VERTICAL: illegal vertical movement")
    cave = next(feature for feature in local.features if feature.kind == "sealed_cave")
    if any(sum(abs(a[i] - b[i]) for i in range(3)) > 2 for a, b in zip(cave.cells, cave.cells[1:])):
        raise ValueError("LOCAL-CAVE: cave path is disconnected")
    magma = set(next(feature for feature in local.features if feature.kind == "sealed_magma").cells)
    water = set(next(feature for feature in local.features if feature.kind == "aquifer_water").cells)
    if magma & water:
        raise ValueError("LOCAL-FLUID: magma and water overlap")
    if any(x in (0, local.width - 1) or y in (0, local.height - 1) for x, y, _ in magma | water):
        raise ValueError("LOCAL-FLUID: sealed fluids touch map boundary")
    heat = set(next(feature for feature in local.features if feature.kind == "heat_zone").cells)
    if any(not any(abs(x - mx) + abs(y - my) + abs(z - mz) == 1 for mx, my, mz in magma)
           for x, y, z in heat):
        raise ValueError("LOCAL-HEAT: heat is not conserved next to magma")
    building = set(next(feature for feature in local.features if feature.kind == "supported_building").cells)
    supports = set(next(feature for feature in local.features if feature.kind == "structural_support").cells)
    if not building <= supports:
        raise ValueError("LOCAL-SUPPORT: unsupported building cell")
    road = next(feature for feature in local.features if feature.kind == "road")
    if any(sum(abs(a[i] - b[i]) for i in range(3)) != 1 for a, b in zip(road.cells, road.cells[1:])):
        raise ValueError("LOCAL-PATH: disconnected road")
