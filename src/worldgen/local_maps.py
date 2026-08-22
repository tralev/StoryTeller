"""Deterministic sparse 3D site maps derived from macro facts."""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..world.views import WorldView
from .local_boundaries import LocalBoundaryConditions, derive_local_boundaries
from .local_chunks import LocalVoxelChunk, generate_material_chunks, validate_material_chunks
from .local_conditionals import plan_local_conditionals, synthesize_conditional_features
from .local_construction import (
    ConstructedOccupancyChunk,
    generate_construction_chunks,
    validate_construction_chunks,
)
from .local_navigation import (
    LocalMovementGraph,
    build_movement_graph,
    validate_movement_graph,
)
from .local_occupancy import (
    LocalOccupancyChunk,
    generate_occupancy_chunks,
    validate_occupancy_chunks,
)
from .local_physics import (
    HeatSimulation,
    MagmaSimulation,
    StructuralSimulation,
    WaterSimulation,
    derive_site_heat_simulation,
    derive_site_magma_simulation,
    derive_site_structural_simulation,
    derive_site_water_simulation,
    validate_fluid_exclusion,
    validate_heat_simulation,
    validate_magma_simulation,
    validate_structural_simulation,
    validate_water_simulation,
)
from .local_reconciliation import macro_edge_anchor
from .local_society import (
    CulturalLocalLayout,
    PersistentLocalEntity,
    derive_cultural_layout,
    generate_persistent_local_entities,
    validate_local_society,
)
from .local_summary import (
    LocalMacroSummary,
    derive_local_macro_summary,
    validate_local_macro_summary,
)
from .numeric import div_floor_exact, identity, rng_for_decision, stable_id


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
    boundary: LocalBoundaryConditions | None = None
    chunks: tuple[LocalVoxelChunk, ...] = ()
    occupancy_chunks: tuple[LocalOccupancyChunk, ...] = ()
    construction_chunks: tuple[ConstructedOccupancyChunk, ...] = ()
    layout: CulturalLocalLayout | None = None
    entities: tuple[PersistentLocalEntity, ...] = ()
    movement_graph: LocalMovementGraph | None = None
    water_simulation: WaterSimulation | None = None
    magma_simulation: MagmaSimulation | None = None
    heat_simulation: HeatSimulation | None = None
    structural_simulation: StructuralSimulation | None = None
    macro_summary: LocalMacroSummary | None = None


def generate_local_maps(world: WorldView) -> tuple[LocalSiteMap, ...]:
    spec = world.payload("world_index")["spec"]
    width = int(spec["local_site_width"])
    height = int(spec["local_site_height"])
    z_levels = int(spec["local_z_levels"])
    strata_grid = world.resources().resources.strata_id.values
    boundaries = {item.site_id: item for item in derive_local_boundaries(world)}
    maps: list[LocalSiteMap] = []
    for site in world.sites():
        boundary = boundaries[site.fact_id]
        cell = boundary.macro_cell
        seed = int(world.payload("world_index")["seed"])
        layout = derive_cultural_layout(seed, boundary)
        conditional_plan = plan_local_conditionals(boundary, layout.street_axis)
        strata = tuple(1 + (int(strata_grid[cell]) + z) % 11 for z in range(z_levels))
        surface_midpoint = div_floor_exact(z_levels, 2)
        surface_values = [
            surface_midpoint + rng_for_decision(
                seed, "local_map", f"{site.fact_id}:surface:{cell_index}",
                "height_jitter",
            ).below(3) - 1
            for cell_index in range(width * height)
        ]
        edge_anchors = tuple(
            macro_edge_anchor(width, height, z_levels, edge) for edge in boundary.edges
        )
        for x, y, z in edge_anchors:
            surface_values[y * width + x] = z
        surface = tuple(surface_values)
        center = (
            div_floor_exact(width, 2),
            div_floor_exact(height, 2),
            surface_midpoint,
        )
        road = (
            tuple((x, center[1], center[2]) for x in range(width))
            if layout.street_axis == "east_west"
            else tuple((center[0], y, center[2]) for y in range(height))
        )
        stairs = tuple(
            (center[0], center[1], z)
            for z in range(max(0, center[2] - 4), center[2] + 1)
        )
        cave = tuple((center[0] + dx, center[1], center[2] - 4) for dx in range(-4, 5))
        water = tuple((center[0] + dx, center[1] + 6, center[2] - 5) for dx in range(-3, 4))
        building = ((center[0], center[1], center[2]), (center[0] + 1, center[1], center[2]))
        def feature_id(kind: str) -> str:
            return stable_id(
                "feature", cell, identity("site_id", site.fact_id), identity("kind", kind),
            )
        natural_features: list[LocalFeature] = []
        vegetation_xy = (center[0] + 4, center[1] + 4)
        vegetation_z = min(
            z_levels - 1,
            surface[vegetation_xy[1] * width + vegetation_xy[0]] + 1,
        )
        natural_features.append(LocalFeature(
            feature_id("vegetation"), "vegetation",
            ((vegetation_xy[0], vegetation_xy[1], vegetation_z),),
            (world.artifact_ids["ecology"], world.artifact_ids["climate"]),
        ))
        construction_sources = (
            world.artifact_ids["settlements"], world.artifact_ids["civilizations"],
        )
        wall = (building[0], building[1])
        constructed_features = [
            LocalFeature(feature_id("wall"), "wall", wall, construction_sources),
            LocalFeature(
                feature_id("interior"), "interior", building, construction_sources
            ),
            LocalFeature(
                feature_id("item"), "item", (building[1],), construction_sources
            ),
            LocalFeature(
                feature_id("door"), "door",
                ((center[0] - 1, center[1], center[2]), building[0]),
                construction_sources,
            ),
            LocalFeature(
                feature_id("ramp"), "ramp",
                ((center[0] + 2, center[1], center[2]),
                 (center[0] + 3, center[1], center[2] + 1)),
                construction_sources,
            ),
            LocalFeature(
                feature_id("climbable"), "climbable",
                (building[1], (building[1][0], building[1][1], building[1][2] + 1)),
                construction_sources,
            ),
        ]
        conditional_features = tuple(
            LocalFeature(feature_id(spec.key), spec.kind, spec.cells, spec.source_ids)
            for spec in synthesize_conditional_features(
                boundary, conditional_plan, width, height, z_levels, surface, center,
                cave, building, edge_anchors, world.artifact_ids,
            )
        )
        anchor_feature = LocalFeature(
            feature_id("macro_elevation_anchor"), "macro_elevation_anchor",
            edge_anchors, (world.artifact_ids["terrain"],),
        )
        features = (
            LocalFeature(feature_id("road"), "road", road, site.source_ids),
            LocalFeature(feature_id("stairs"), "vertical_stairs", stairs, site.source_ids),
            LocalFeature(feature_id("cave"), "sealed_cave", cave, site.source_ids),
            LocalFeature(feature_id("aquifer"), "aquifer_water", water, site.source_ids),
            LocalFeature(feature_id("building"), "supported_building", building, site.source_ids),
            LocalFeature(feature_id("workshop"), "workshop", (building[0],), site.source_ids),
            LocalFeature(feature_id("stockpile"), "stockpile", (building[1],), site.source_ids),
            LocalFeature(feature_id("magma"), "sealed_magma", ((center[0], center[1], 1),),
                         (world.artifact_ids["geology"],)),
            LocalFeature(feature_id("heat"), "heat_zone", ((center[0], center[1], 2),),
                         (world.artifact_ids["climate"],)),
            LocalFeature(feature_id("support"), "structural_support", (building[0], building[1]),
                         site.source_ids),
            LocalFeature(feature_id("parcel"), "parcel", tuple(
                (center[0] + dx, center[1] + dy, center[2])
                for dx in range(-layout.parcel_radius, layout.parcel_radius + 1)
                for dy in range(-layout.parcel_radius, layout.parcel_radius + 1)
            ), site.source_ids),
            LocalFeature(feature_id("scar"), "event_scar", ((center[0] - 2, center[1], center[2]),),
                         (world.artifact_ids["history"],)),
            anchor_feature,
        ) + tuple(natural_features) + tuple(constructed_features) + conditional_features
        chunks = generate_material_chunks(width, height, z_levels, surface, strata)
        movement_graph = build_movement_graph(features)
        water_simulation = derive_site_water_simulation(
            width, height, z_levels, features,
        )
        magma_simulation = derive_site_magma_simulation(
            width, height, z_levels, features,
        )
        validate_fluid_exclusion(water_simulation, magma_simulation)
        heat_simulation = derive_site_heat_simulation(
            width, height, z_levels, features, magma_simulation,
        )
        structural_simulation = derive_site_structural_simulation(
            features, heat_simulation,
        )
        local = LocalSiteMap(
            1, site.fact_id, width, height, z_levels, cell, strata, surface, features,
            boundary, chunks,
            generate_occupancy_chunks(width, height, z_levels, features),
            generate_construction_chunks(width, height, z_levels, features, boundary),
            layout, generate_persistent_local_entities(seed, boundary, building),
            movement_graph,
            water_simulation,
            magma_simulation,
            heat_simulation,
            structural_simulation,
        )
        maps.append(replace(local, macro_summary=derive_local_macro_summary(local)))
    return tuple(maps)


def validate_local_map(local: LocalSiteMap) -> None:
    if local.boundary is not None and (
            local.boundary.site_id != local.site_id
            or local.boundary.macro_cell != local.macro_cell
            or not local.boundary.source_artifact_ids):
        raise ValueError("LOCAL-BOUNDARY: local map contradicts its macro boundary")
    if local.boundary is not None:
        validate_material_chunks(
            local.width, local.height, local.z_levels, local.surface_height,
            local.strata, local.chunks,
        )
        validate_occupancy_chunks(
            local.width, local.height, local.z_levels, local.features,
            local.occupancy_chunks,
        )
        validate_construction_chunks(
            local.width, local.height, local.z_levels, local.features,
            local.boundary, local.construction_chunks,
        )
        if local.layout is None:
            raise ValueError("WG-LOCAL-LAYOUT: generated local map lacks cultural layout")
        building_cells = next(
            feature.cells for feature in local.features
            if feature.kind == "supported_building"
        )
        validate_local_society(
            local.boundary, local.layout, local.entities, building_cells,
        )
        if local.movement_graph is None:
            raise ValueError("WG-LOCAL-NAV: generated local map lacks movement graph")
        validate_movement_graph(local.features, local.movement_graph)
        if local.water_simulation is None:
            raise ValueError("WG-LOCAL-WATER: generated local map lacks water simulation")
        validate_water_simulation(local.water_simulation)
        if local.water_simulation != derive_site_water_simulation(
            local.width, local.height, local.z_levels, local.features,
        ):
            raise ValueError("WG-LOCAL-WATER: simulation contradicts water occupants")
        if local.magma_simulation is None:
            raise ValueError("WG-LOCAL-MAGMA: generated local map lacks magma simulation")
        validate_magma_simulation(local.magma_simulation)
        if local.magma_simulation != derive_site_magma_simulation(
            local.width, local.height, local.z_levels, local.features,
        ):
            raise ValueError("WG-LOCAL-MAGMA: simulation contradicts magma occupants")
        validate_fluid_exclusion(local.water_simulation, local.magma_simulation)
        if local.heat_simulation is None:
            raise ValueError("WG-LOCAL-HEAT: generated local map lacks heat simulation")
        validate_heat_simulation(local.heat_simulation)
        if local.heat_simulation != derive_site_heat_simulation(
            local.width, local.height, local.z_levels, local.features,
            local.magma_simulation,
        ):
            raise ValueError("WG-LOCAL-HEAT: simulation contradicts retained sources")
        if local.structural_simulation is None:
            raise ValueError("WG-LOCAL-STRUCTURE: generated local map lacks structural simulation")
        validate_structural_simulation(
            local.structural_simulation, local.heat_simulation.final,
        )
        if local.structural_simulation != derive_site_structural_simulation(
            local.features, local.heat_simulation,
        ):
            raise ValueError("WG-LOCAL-STRUCTURE: simulation contradicts construction")
        if local.macro_summary is None:
            raise ValueError("WG-LOCAL-SUMMARY: generated local map lacks macro summary")
        validate_local_macro_summary(local, local.macro_summary)
    if (len(local.surface_height) != local.width * local.height
            or len(local.strata) != local.z_levels):
        raise ValueError("LOCAL-COVERAGE: incomplete local geometry")
    for feature in local.features:
        for x, y, z in feature.cells:
            if not (0 <= x < local.width and 0 <= y < local.height and 0 <= z < local.z_levels):
                raise ValueError("LOCAL-BOUNDS: feature outside local map")
    kinds = {feature.kind for feature in local.features}
    required = {"road", "vertical_stairs", "sealed_cave", "aquifer_water", "supported_building",
                "workshop", "stockpile", "sealed_magma", "heat_zone",
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
    water = set(next(
        feature for feature in local.features if feature.kind == "aquifer_water"
    ).cells)
    if magma & water:
        raise ValueError("LOCAL-FLUID: magma and water overlap")
    if any(x in (0, local.width - 1) or y in (0, local.height - 1) for x, y, _ in magma | water):
        raise ValueError("LOCAL-FLUID: sealed fluids touch map boundary")
    heat = set(next(feature for feature in local.features if feature.kind == "heat_zone").cells)
    if any(not any(abs(x - mx) + abs(y - my) + abs(z - mz) == 1 for mx, my, mz in magma)
           for x, y, z in heat):
        raise ValueError("LOCAL-HEAT: heat is not conserved next to magma")
    building = set(next(
        feature for feature in local.features if feature.kind == "supported_building"
    ).cells)
    supports = set(next(
        feature for feature in local.features if feature.kind == "structural_support"
    ).cells)
    if not building <= supports:
        raise ValueError("LOCAL-SUPPORT: unsupported building cell")
    road = next(feature for feature in local.features if feature.kind == "road")
    if any(
        sum(abs(a[i] - b[i]) for i in range(3)) != 1
        for a, b in zip(road.cells, road.cells[1:])
    ):
        raise ValueError("LOCAL-PATH: disconnected road")
