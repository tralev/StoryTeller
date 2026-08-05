"""Standalone Phase 2 physical-world generation and artifact publication."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..domain.run_spec import WorldSpec
from .artifacts import WorldArtifact, WorldArtifactRepository, canonical_json
from .grid import GridSpec
from .hydrology import generate_hydrology
from .ecology import generate_ecology
from .maps import render_maps
from .physical_biomes import classify_physical_biomes
from .physical_regions import generate_regions
from .physical_terrain import generate_physical_terrain
from .resources import generate_resources
from .routes import generate_routes
from .validation import validate_physical_world
from .weather import generate_weather


def _commit(repository: WorldArtifactRepository, kind: str, payload: object,
            dependencies: tuple[WorldArtifact[Any], ...], fingerprint: str) -> WorldArtifact[Any]:
    artifact = WorldArtifact.build(kind, payload,
                                   depends_on=tuple(item.artifact_id for item in dependencies),
                                   producer_fingerprint=fingerprint)
    repository.put(artifact)
    return artifact


def generate_physical_world(spec: WorldSpec, seed: int, output: str | Path) -> dict[str, Any]:
    root = Path(output)
    repository = WorldArtifactRepository(root / "artifacts")
    grid = GridSpec(spec.width, spec.height, spec.metres_per_world_cell)
    fingerprint = hashlib.sha256(canonical_json({"algorithm": "physical-world-v1", "spec": spec})).hexdigest()
    terrain = generate_physical_terrain(grid, seed, continent_count=spec.continent_count,
                                        plate_count=spec.plate_count, erosion_passes=spec.erosion_passes,
                                        minimum_continent_cells=spec.minimum_continent_cells)
    plates_ref = _commit(repository, "plates", terrain.plates, (), fingerprint)
    terrain_ref = _commit(repository, "terrain", terrain, (plates_ref,), fingerprint)
    geology_payload = {"plate_id": terrain.plate_id, "elevation_mm": terrain.elevation_mm}
    geology_ref = _commit(repository, "geology", geology_payload, (terrain_ref,), fingerprint)
    hydrology = generate_hydrology(terrain)
    hydrology_ref = _commit(repository, "hydrology", hydrology, (terrain_ref, geology_ref), fingerprint)
    climate = generate_weather(terrain, hydrology, axial_tilt_millidegrees=spec.axial_tilt_millidegrees,
                               relaxation_passes=spec.climate_relaxation_passes)
    climate_ref = _commit(repository, "climate", climate, (terrain_ref, hydrology_ref), fingerprint)
    biomes = classify_physical_biomes(terrain, hydrology, climate)
    soil_ref = _commit(repository, "soil", {"fertility_ppm": biomes.soil_fertility_ppm},
                       (geology_ref, climate_ref), fingerprint)
    biome_ref = _commit(repository, "biomes", biomes, (soil_ref, climate_ref), fingerprint)
    resources = generate_resources(terrain, biomes, seed)
    resource_ref = _commit(repository, "resources", resources, (geology_ref, biome_ref), fingerprint)
    regions = generate_regions(terrain, hydrology, biomes)
    ecology = generate_ecology(biomes, regions, seed)
    species_ref = _commit(repository, "species", {"algorithm_version": 1, "species": ecology.species},
                         (biome_ref,), fingerprint)
    ecology_ref = _commit(repository, "ecology", ecology, (biome_ref, species_ref), fingerprint)
    region_ref = _commit(repository, "regions", regions, (hydrology_ref, biome_ref), fingerprint)
    routes = generate_routes(terrain, hydrology, climate, resources, regions)
    route_ref = _commit(repository, "routes", routes, (region_ref, resource_ref, climate_ref), fingerprint)
    validate_physical_world(terrain, hydrology, climate, biomes, resources, regions, routes)
    map_paths = render_maps(root / "maps", terrain, biomes, regions, routes)
    map_payload = {name: {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for name, path in sorted(map_paths.items())}
    map_ref = _commit(repository, "maps", map_payload, (region_ref, route_ref), fingerprint)
    refs = (plates_ref, terrain_ref, geology_ref, hydrology_ref, climate_ref, soil_ref, biome_ref,
            resource_ref, species_ref, ecology_ref, region_ref, route_ref, map_ref)
    index_payload = {
        "algorithm_version": 1, "seed": seed, "spec": spec.to_dict(),
        "artifacts": {item.kind: {"artifact_id": item.artifact_id, "sha256": item.sha256}
                      for item in refs},
        "map_count": len(map_paths),
    }
    index_ref = _commit(repository, "world_index", index_payload, refs, fingerprint)
    return {"world_index": index_ref.artifact_id, "artifacts": len(refs) + 1,
            "regions": len(regions.regions), "routes": len(routes.routes), "maps": len(map_paths)}
