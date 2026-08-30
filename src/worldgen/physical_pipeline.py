"""Standalone Phase 2 physical-world generation and artifact publication."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Union

from ..domain.run_spec import WorldSpec
from .artifacts import (
    ProducerFingerprint,
    WorldArtifact,
    WorldArtifactRepository,
    canonical_json,
    freeze_canonical,
)
from .ecology import generate_ecology
from .geology import generate_geology
from .grid import (
    DenseGridCatalog,
    DenseGridManifest,
    DenseGridRepository,
    GridSpec,
    IntGrid,
    build_grid_manifest,
    iter_grid_chunks,
)
from .hydrology import generate_hydrology
from .indexes import build_spatial_index, spatial_index_payload, validate_spatial_index_payload
from .maps import build_map_layers, build_map_manifest, render_maps, validate_map_manifest
from .numeric import deterministic_map
from .physical_biomes import classify_physical_biomes
from .physical_dag import PHYSICAL_STAGE_DEPENDENCIES, validate_physical_stage_dag
from .physical_regions import REGION_COST_MODEL, generate_regions
from .physical_terrain import generate_physical_terrain
from .physical_validation_report import (
    build_physical_validation_report,
    measure_physical_invariants,
)
from .reference_index import (
    ReferenceIndex,
    reference_index_payload,
    validate_reference_index_payload,
)
from .registries import validate_and_hash_physical_registries
from .resources import generate_resources
from .routes import generate_routes
from .soil import generate_soil
from .validation import (
    validate_ecology,
    validate_physical_world,
    validate_regions,
    validate_terrain_contract,
)
from .weather import generate_weather


@dataclass(frozen=True)
class PhysicalStageCommit:
    kind: str
    payload: object
    dependencies: tuple[WorldArtifact[Any], ...]
    producer_fingerprint: ProducerFingerprint

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_canonical(self.payload))
        ordered = tuple(sorted(self.dependencies, key=lambda item: item.artifact_id))
        if len({item.artifact_id for item in ordered}) != len(ordered):
            raise ValueError("WG-DEPENDENCY: duplicate physical-stage dependency")
        object.__setattr__(self, "dependencies", ordered)
        object.__setattr__(
            self, "producer_fingerprint", ProducerFingerprint(self.producer_fingerprint)
        )


def _commit(repository: WorldArtifactRepository, stage: PhysicalStageCommit) -> WorldArtifact[Any]:
    artifact = WorldArtifact.build(
        stage.kind,
        stage.payload,
        depends_on=tuple(item.artifact_id for item in stage.dependencies),
        producer_fingerprint=stage.producer_fingerprint,
    )
    repository.put(artifact)
    return artifact


def _publish_grid_catalog(
    repository: DenseGridRepository,
    grid: GridSpec,
    layers: tuple[tuple[str, IntGrid[int]], ...],
    worker_count: int,
) -> DenseGridCatalog:
    if isinstance(worker_count, bool) or not isinstance(worker_count, int) or worker_count < 1:
        raise ValueError("WG-WORKERS: worker_count must be a positive integer")
    by_layer = dict(layers)
    if len(by_layer) != len(layers):
        raise ValueError("WG-GRID-CATALOG: duplicate layer")

    def publish(layer: str) -> DenseGridManifest:
        dense_grid = by_layer[layer]
        manifest = build_grid_manifest(layer, dense_grid)
        repository.put(manifest, iter_grid_chunks(layer, dense_grid))
        return manifest

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        published = deterministic_map(executor, publish, by_layer)
    return DenseGridCatalog(
        "storyteller.dense-grid-catalog.v1",
        grid,
        tuple(manifest for _, manifest in published),
    )


@dataclass(frozen=True)
class PhysicalWorldResult(Mapping[str, Union[int, str]]):
    world_index: str
    artifacts: int
    regions: int
    routes: int
    maps: int

    def __getitem__(self, key: str) -> Union[int, str]:
        values: dict[str, int | str] = {
            "world_index": self.world_index,
            "artifacts": self.artifacts,
            "regions": self.regions,
            "routes": self.routes,
            "maps": self.maps,
        }
        try:
            return values[key]
        except KeyError:
            raise KeyError(key) from None

    def __iter__(self) -> Iterator[str]:
        return iter(("world_index", "artifacts", "regions", "routes", "maps"))

    def __len__(self) -> int:
        return 5

    def to_dict(self) -> dict[str, int | str]:
        return {key: self[key] for key in self}


_STAGE_REGISTRIES: dict[str, tuple[str, ...]] = {
    "biomes": ("biomes",),
    "resources": ("materials",),
    "species": ("species",),
    # Recipe rules are first consumed by history, but the physical root records
    # their exact generation contract for package-wide provenance.
    "world_index": ("recipes",),
}


def physical_stage_fingerprint(
    spec: WorldSpec,
    kind: str,
    registry_hashes: Mapping[str, str] | None = None,
) -> ProducerFingerprint:
    hashes = dict(registry_hashes or validate_and_hash_physical_registries())
    selected = {name: hashes[name] for name in _STAGE_REGISTRIES.get(kind, ())}
    return ProducerFingerprint(
        hashlib.sha256(
            canonical_json(
                {
                    "algorithm": "physical-world-v1",
                    "spec": spec,
                    "registries": selected,
                }
            )
        ).hexdigest()
    )


def generate_physical_world(
    spec: WorldSpec,
    seed: int,
    output: str | Path,
    *,
    worker_count: int = 1,
) -> PhysicalWorldResult:
    validate_physical_stage_dag()
    root = Path(output)
    repository = WorldArtifactRepository(root / "artifacts")
    grid = GridSpec(spec.width, spec.height, spec.metres_per_world_cell)
    registry_hashes = validate_and_hash_physical_registries()

    def commit(
        kind: str, payload: object, dependencies: tuple[WorldArtifact[Any], ...] = ()
    ) -> WorldArtifact[Any]:
        expected = PHYSICAL_STAGE_DEPENDENCIES[kind]
        actual = tuple(sorted(item.kind for item in dependencies))
        if actual != expected:
            raise ValueError(f"WG-PHYSICAL-DAG: {kind} dependencies {actual} != {expected}")
        return _commit(
            repository,
            PhysicalStageCommit(
                kind,
                payload,
                dependencies,
                physical_stage_fingerprint(spec, kind, registry_hashes),
            ),
        )

    terrain = generate_physical_terrain(
        grid,
        seed,
        continent_count=spec.continent_count,
        plate_count=spec.plate_count,
        erosion_passes=spec.erosion_passes,
        minimum_continent_cells=spec.minimum_continent_cells,
        sea_level_ppm=spec.sea_level_ppm,
    )
    validate_terrain_contract(terrain, spec)
    plates_ref = commit("plates", terrain.plates)
    terrain_grid_fields = {
        "elevation_mm",
        "plate_id",
        "plate_boundary",
        "slope_ppm",
        "land",
        "continent_id",
    }
    terrain_payload = {
        item.name: getattr(terrain, item.name)
        for item in fields(terrain)
        if item.name not in terrain_grid_fields
    }
    terrain_ref = commit("terrain", terrain_payload, (plates_ref,))
    grid_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("terrain_elevation_mm", terrain.elevation_mm),
        ("terrain_plate_id", terrain.plate_id),
        ("terrain_plate_boundary", terrain.plate_boundary),
        ("terrain_slope_ppm", terrain.slope_ppm),
        ("terrain_land", terrain.land),
        ("terrain_continent_id", terrain.continent_id),
    )
    chunk_repository = DenseGridRepository(root / "chunks")
    terrain_catalog = _publish_grid_catalog(chunk_repository, grid, grid_layers, worker_count)
    catalog_ref = commit("terrain_grid_catalog", terrain_catalog, (terrain_ref,))
    geology = generate_geology(terrain)
    geology_payload = {
        "algorithm_version": geology.algorithm_version,
        "terrain_grid_catalog": catalog_ref.artifact_id,
    }
    geology_ref = commit("geology", geology_payload, (terrain_ref, catalog_ref))
    geology_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("geology_rock_class_id", geology.rock_class_id),
        ("geology_strata_id", geology.strata_id),
        ("geology_parent_material_id", geology.parent_material_id),
        ("geology_fault", geology.fault),
        ("geology_volcano", geology.volcano),
        ("geology_tectonic_relief_mm", geology.tectonic_relief_mm),
    )
    geology_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        geology_layers,
        worker_count,
    )
    geology_catalog_ref = commit("geology_grid_catalog", geology_catalog, (geology_ref,))
    hydrology = generate_hydrology(terrain)
    hydrology_grid_fields = {
        "filled_elevation_mm",
        "flow_to",
        "accumulation",
        "watershed_id",
        "coastline",
        "aquifer_capacity_mm",
        "salinity_ppm",
        "snowpack_mm",
        "glacier",
        "delta",
    }
    hydrology_payload = {
        item.name: getattr(hydrology, item.name)
        for item in fields(hydrology)
        if item.name not in hydrology_grid_fields
    }
    hydrology_ref = commit("hydrology", hydrology_payload, (terrain_ref, geology_ref))
    hydrology_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("hydrology_filled_elevation_mm", hydrology.filled_elevation_mm),
        ("hydrology_flow_to", hydrology.flow_to),
        ("hydrology_accumulation", hydrology.accumulation),
        ("hydrology_watershed_id", hydrology.watershed_id),
        ("hydrology_coastline", hydrology.coastline),
        ("hydrology_aquifer_capacity_mm", hydrology.aquifer_capacity_mm),
        ("hydrology_salinity_ppm", hydrology.salinity_ppm),
        ("hydrology_snowpack_mm", hydrology.snowpack_mm),
        ("hydrology_glacier", hydrology.glacier),
        ("hydrology_delta", hydrology.delta),
    )
    hydrology_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        hydrology_layers,
        worker_count,
    )
    hydrology_catalog_ref = commit(
        "hydrology_grid_catalog",
        hydrology_catalog,
        (hydrology_ref,),
    )
    climate = generate_weather(
        terrain,
        hydrology,
        axial_tilt_millidegrees=spec.axial_tilt_millidegrees,
        relaxation_passes=spec.climate_relaxation_passes,
    )
    climate_payload = {
        "algorithm_version": climate.algorithm_version,
        "season_count": len(climate.seasons),
        "water_ledger": climate.water_ledger,
    }
    climate_ref = commit(
        "climate", climate_payload, (terrain_ref, hydrology_ref, hydrology_catalog_ref)
    )
    climate_layers: list[tuple[str, IntGrid[int]]] = [
        ("climate_annual_temperature_millic", climate.annual_temperature_millic),
        ("climate_annual_precipitation_mm", climate.annual_precipitation_mm),
        ("climate_weather_regime", climate.weather_regime),
    ]
    for season_index, season in enumerate(climate.seasons):
        prefix = f"climate_season_{season_index:02d}"
        climate_layers.extend(
            (
                (f"{prefix}_temperature_millic", season.temperature_millic),
                (f"{prefix}_precipitation_mm", season.precipitation_mm),
                (f"{prefix}_evaporation_mm", season.evaporation_mm),
                (f"{prefix}_snowpack_mm", season.snowpack_mm),
                (f"{prefix}_ice", season.ice),
                (f"{prefix}_storm_ppm", season.storm_ppm),
                (f"{prefix}_wind_x_mmps", season.wind_x_mmps),
                (f"{prefix}_wind_y_mmps", season.wind_y_mmps),
                (f"{prefix}_hazard_ppm", season.hazard_ppm),
            )
        )
    climate_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        tuple(climate_layers),
        worker_count,
    )
    climate_catalog_ref = commit("climate_grid_catalog", climate_catalog, (climate_ref,))
    soil = generate_soil(terrain, geology, hydrology, climate)
    soil_ref = commit(
        "soil",
        {"algorithm_version": soil.algorithm_version},
        (
            terrain_ref,
            geology_ref,
            geology_catalog_ref,
            hydrology_ref,
            hydrology_catalog_ref,
            climate_ref,
            climate_catalog_ref,
        ),
    )
    soil_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("soil_depth_mm", soil.depth_mm),
        ("soil_fertility_ppm", soil.fertility_ppm),
        ("soil_drainage_ppm", soil.drainage_ppm),
        ("soil_erosion_class", soil.erosion_class),
    )
    soil_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        soil_layers,
        worker_count,
    )
    soil_catalog_ref = commit("soil_grid_catalog", soil_catalog, (soil_ref,))
    biomes = classify_physical_biomes(terrain, hydrology, climate, soil)
    biome_ref = commit(
        "biomes",
        {"algorithm_version": biomes.algorithm_version},
        (climate_ref, climate_catalog_ref, soil_ref, soil_catalog_ref),
    )
    biome_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("biome_id", biomes.biome_id),
        ("biome_net_productivity_kg_km2", biomes.net_productivity_kg_km2),
        ("biome_carrying_capacity", biomes.carrying_capacity),
    )
    biome_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        biome_layers,
        worker_count,
    )
    biome_catalog_ref = commit("biome_grid_catalog", biome_catalog, (biome_ref,))
    resources = generate_resources(terrain, biomes, seed, geology)
    resource_ref = commit(
        "resources",
        {
            "algorithm_version": resources.algorithm_version,
            "deposits": resources.deposits,
        },
        (
            geology_ref,
            geology_catalog_ref,
            soil_ref,
            soil_catalog_ref,
            biome_ref,
            biome_catalog_ref,
        ),
    )
    resource_layers: tuple[tuple[str, IntGrid[int]], ...] = (
        ("resource_renewable_yield", resources.renewable_yield),
    )
    resource_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        resource_layers,
        worker_count,
    )
    resource_catalog_ref = commit("resource_grid_catalog", resource_catalog, (resource_ref,))
    regions = generate_regions(terrain, hydrology, climate, biomes)
    validate_regions(terrain, regions)
    ecology = generate_ecology(biomes, regions, seed)
    validate_ecology(ecology, regions)
    species_ref = commit(
        "species",
        {"algorithm_version": ecology.algorithm_version, "species": ecology.species},
        (biome_ref, biome_catalog_ref),
    )
    ecology_ref = commit("ecology", ecology, (biome_ref, biome_catalog_ref, species_ref))
    region_ref = commit(
        "regions",
        {
            "algorithm_version": regions.algorithm_version,
            "cost_model": REGION_COST_MODEL,
            "regions": regions.regions,
        },
        (
            hydrology_ref,
            hydrology_catalog_ref,
            climate_ref,
            climate_catalog_ref,
            biome_ref,
            biome_catalog_ref,
        ),
    )
    region_catalog = _publish_grid_catalog(
        chunk_repository,
        grid,
        (("region_cell_region", regions.cell_region),),
        worker_count,
    )
    region_catalog_ref = commit("region_grid_catalog", region_catalog, (region_ref,))
    routes = generate_routes(terrain, hydrology, climate, resources, regions)
    route_ref = commit(
        "routes",
        routes,
        (
            region_ref,
            region_catalog_ref,
            resource_ref,
            resource_catalog_ref,
            climate_ref,
            climate_catalog_ref,
        ),
    )
    spatial_index = build_spatial_index(regions, routes, grid)
    spatial_payload = spatial_index_payload(
        spatial_index,
        region_catalog_ref.artifact_id,
        region_ref.artifact_id,
        route_ref.artifact_id,
    )
    spatial_ref = commit(
        "spatial_index", spatial_payload, (region_catalog_ref, region_ref, route_ref)
    )
    validate_spatial_index_payload(spatial_ref.payload, spatial_payload, spatial_ref.depends_on)
    reference_index = ReferenceIndex.build(
        terrain,
        hydrology,
        regions,
        routes,
        resources,
        ecology,
    )
    reference_sources = {
        "ecology": ecology_ref.artifact_id,
        "hydrology": hydrology_ref.artifact_id,
        "regions": region_ref.artifact_id,
        "resources": resource_ref.artifact_id,
        "routes": route_ref.artifact_id,
        "species": species_ref.artifact_id,
    }
    reference_payload = reference_index_payload(reference_index, reference_sources)
    reference_ref = commit(
        "reference_index",
        reference_payload,
        (ecology_ref, hydrology_ref, region_ref, resource_ref, route_ref, species_ref),
    )
    validate_reference_index_payload(
        reference_ref.payload, reference_payload, reference_ref.depends_on
    )
    validate_physical_world(terrain, hydrology, climate, soil, biomes, resources, regions, routes)
    scalar_sources = {
        "biome": ("biome_grid_catalog", biome_catalog_ref.artifact_id, "biome_id"),
        "climate": (
            "climate_grid_catalog",
            climate_catalog_ref.artifact_id,
            "climate_annual_temperature_millic",
        ),
        "hazard": (
            "climate_grid_catalog",
            climate_catalog_ref.artifact_id,
            "climate_season_00_hazard_ppm",
        ),
        "hydrology": (
            "hydrology_grid_catalog",
            hydrology_catalog_ref.artifact_id,
            "hydrology_accumulation",
        ),
        "political": ("region_grid_catalog", region_catalog_ref.artifact_id, "region_cell_region"),
        "resource": (
            "resource_grid_catalog",
            resource_catalog_ref.artifact_id,
            "resource_renewable_yield",
        ),
        "soil": ("soil_grid_catalog", soil_catalog_ref.artifact_id, "soil_drainage_ppm"),
        "terrain": ("terrain_grid_catalog", catalog_ref.artifact_id, "terrain_elevation_mm"),
    }
    map_layers = build_map_layers(
        grid, scalar_sources, region_ref.artifact_id, route_ref.artifact_id, regions, routes
    )
    map_layers_ref = commit(
        "map_layers",
        map_layers,
        (
            biome_catalog_ref,
            climate_catalog_ref,
            hydrology_catalog_ref,
            region_catalog_ref,
            region_ref,
            resource_catalog_ref,
            route_ref,
            soil_catalog_ref,
            catalog_ref,
        ),
    )
    scalar_values = {
        "biome": biomes.biome_id.values,
        "climate": climate.annual_temperature_millic.values,
        "hazard": climate.seasons[0].hazard_ppm.values,
        "hydrology": hydrology.accumulation.values,
        "political": regions.cell_region.values,
        "resource": resources.renewable_yield.values,
        "soil": soil.drainage_ppm.values,
        "terrain": terrain.elevation_mm.values,
    }
    map_paths = render_maps(
        root / "maps", terrain, biomes, regions, routes, map_layers, scalar_values
    )
    map_payload = build_map_manifest(root, map_paths, map_layers, regions)
    validate_map_manifest(root, map_payload, map_layers)
    map_ref = commit(
        "maps",
        map_payload,
        (
            biome_catalog_ref,
            biome_ref,
            climate_catalog_ref,
            hydrology_catalog_ref,
            map_layers_ref,
            region_catalog_ref,
            region_ref,
            resource_catalog_ref,
            route_ref,
            soil_catalog_ref,
            catalog_ref,
        ),
    )
    refs = (
        plates_ref,
        terrain_ref,
        catalog_ref,
        geology_ref,
        geology_catalog_ref,
        hydrology_ref,
        hydrology_catalog_ref,
        climate_ref,
        climate_catalog_ref,
        soil_ref,
        soil_catalog_ref,
        biome_ref,
        biome_catalog_ref,
        resource_ref,
        resource_catalog_ref,
        species_ref,
        ecology_ref,
        region_ref,
        region_catalog_ref,
        route_ref,
        spatial_ref,
        reference_ref,
        map_layers_ref,
        map_ref,
    )
    invariant_evidence = measure_physical_invariants(terrain, hydrology, climate)
    validation_report = build_physical_validation_report(refs, invariant_evidence)
    validation_ref = commit("validation_report", validation_report, refs)
    indexed_refs = refs + (validation_ref,)
    index_payload = {
        "algorithm_version": 1,
        "seed": seed,
        "spec": spec.to_dict(),
        "artifacts": {
            item.kind: {"artifact_id": item.artifact_id, "sha256": item.sha256}
            for item in indexed_refs
        },
        "map_count": len(map_paths),
    }
    index_ref = commit("world_index", index_payload, indexed_refs)
    return PhysicalWorldResult(
        index_ref.artifact_id,
        len(refs) + 2,
        len(regions.regions),
        len(routes.routes),
        len(map_paths),
    )
