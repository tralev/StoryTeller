"""Canonical deletion/rebuild tooling for disposable physical indexes."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ..domain.run_spec import WorldSpec
from .artifacts import WorldArtifact, WorldArtifactRepository
from .hydrology_reader import VerifiedHydrologyReader
from .indexes import build_spatial_index, spatial_index_payload
from .physical_models import EcologyLayer, Species
from .physical_pipeline import physical_stage_fingerprint
from .reference_index import ReferenceIndex, reference_index_payload
from .region_reader import VerifiedRegionReader
from .resource_reader import VerifiedResourceReader
from .route_reader import VerifiedRouteReader
from .terrain_reader import VerifiedTerrainReader

INDEX_KINDS = ("spatial_index", "reference_index")


def _species(payload: object) -> tuple[Species, ...]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("species"), Iterable):
        raise ValueError("WG-INDEX-REBUILD: invalid species source")
    result = []
    for raw in payload["species"]:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("habitat_biomes"), Iterable):
            raise ValueError("WG-INDEX-REBUILD: invalid species record")
        result.append(Species(
            str(raw["species_id"]), int(raw["trophic_level"]),
            tuple(int(item) for item in raw["habitat_biomes"]),
            int(raw["annual_energy_kj"]), bool(raw["extinct"]),
        ))
    return tuple(result)


def rebuild_physical_indexes(root: str | Path) -> tuple[str, str]:
    """Replace only derived indexes with byte-identical authoritative rebuilds."""
    world_root = Path(root).resolve()
    repository = WorldArtifactRepository(world_root / "artifacts")

    # Verify and load every source before touching either disposable target.
    world_index = repository.load_verified("world_index")
    if not isinstance(world_index.payload, Mapping):
        raise ValueError("WG-INDEX-REBUILD: invalid world index")
    spec_payload = world_index.payload.get("spec")
    seed = world_index.payload.get("seed")
    if not isinstance(spec_payload, Mapping) or isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("WG-INDEX-REBUILD: invalid generation identity")
    spec = WorldSpec.from_dict({str(key): value for key, value in spec_payload.items()})
    terrain = VerifiedTerrainReader(world_root).load()
    hydrology = VerifiedHydrologyReader(world_root).load()
    regions = VerifiedRegionReader(world_root).load()
    routes = VerifiedRouteReader(world_root).load()
    resources = VerifiedResourceReader(world_root).load()
    source = {kind: repository.load_verified(kind) for kind in (
        "ecology", "hydrology", "region_grid_catalog", "regions", "resources", "routes", "species",
    )}
    species = _species(source["species"].payload)
    ecology = EcologyLayer(1, species, (), (), (), ())

    spatial = build_spatial_index(regions.regions, routes.routes, terrain.terrain.grid)
    spatial_payload = spatial_index_payload(
        spatial, regions.grid_catalog_id, regions.region_artifact_id, routes.route_artifact_id,
    )
    reference = ReferenceIndex.build(
        terrain.terrain, hydrology.hydrology, regions.regions, routes.routes,
        resources.resources, ecology,
    )
    reference_sources = {
        kind: source[kind].artifact_id for kind in
        ("ecology", "hydrology", "regions", "resources", "routes", "species")
    }
    reference_payload = reference_index_payload(reference, reference_sources)
    replacements = (
        WorldArtifact.build(
            "spatial_index", spatial_payload,
            depends_on=tuple(source[kind].artifact_id for kind in
                             ("region_grid_catalog", "regions", "routes")),
            producer_fingerprint=physical_stage_fingerprint(spec, "spatial_index"),
        ),
        WorldArtifact.build(
            "reference_index", reference_payload,
            depends_on=tuple(source[kind].artifact_id for kind in
                             ("ecology", "hydrology", "regions", "resources", "routes", "species")),
            producer_fingerprint=physical_stage_fingerprint(spec, "reference_index"),
        ),
    )
    expected = world_index.payload.get("artifacts")
    if not isinstance(expected, Mapping):
        raise ValueError("WG-INDEX-REBUILD: missing expected identities")
    for artifact in replacements:
        record = expected.get(artifact.kind)
        if (not isinstance(record, Mapping) or record.get("artifact_id") != artifact.artifact_id
                or record.get("sha256") != artifact.sha256):
            raise ValueError(f"WG-INDEX-REBUILD: {artifact.kind} identity mismatch")

    # Targets are exact, narrow, and reproducible; sources have already passed.
    for kind in INDEX_KINDS:
        (repository.root / f"{kind}.json").unlink(missing_ok=True)
    for artifact in replacements:
        repository.put(artifact)
    return replacements[0].artifact_id, replacements[1].artifact_id
