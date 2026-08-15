"""Verified typed reader for authoritative chunked geology."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .physical_models import GeologyLayer
from .terrain_reader import VerifiedTerrainReader

GEOLOGY_GRID_LAYERS = {
    "rock_class_id": "geology_rock_class_id",
    "strata_id": "geology_strata_id",
    "parent_material_id": "geology_parent_material_id",
    "fault": "geology_fault",
    "volcano": "geology_volcano",
    "tectonic_relief_mm": "geology_tectonic_relief_mm",
}


@dataclass(frozen=True)
class PersistedGeology:
    geology_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    geology: GeologyLayer
    attributes: FrozenMap


class VerifiedGeologyReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    def load(self) -> PersistedGeology:
        terrain = VerifiedTerrainReader(self.root).load().terrain
        artifact = self.artifacts.load_verified("geology")
        catalog_artifact = self.artifacts.load_verified("geology_grid_catalog")
        if not isinstance(artifact.payload, FrozenMap):
            raise ValueError("WG-GEOLOGY-READ: payload is not canonical")
        if any(field in artifact.payload for field in GEOLOGY_GRID_LAYERS):
            raise ValueError("WG-GEOLOGY-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (artifact.artifact_id,):
            raise ValueError("WG-GEOLOGY-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-GEOLOGY-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != terrain.grid:
            raise ValueError("WG-GEOLOGY-READ: catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(GEOLOGY_GRID_LAYERS.values()):
            raise ValueError("WG-GEOLOGY-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer))
            for field, layer in GEOLOGY_GRID_LAYERS.items()
        }
        version = artifact.payload["algorithm_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("WG-GEOLOGY-READ: algorithm version must be an integer")
        geology = GeologyLayer(
            version, dense["rock_class_id"], dense["strata_id"],
            dense["parent_material_id"], dense["fault"], dense["volcano"],
            dense["tectonic_relief_mm"],
        )
        return PersistedGeology(
            artifact.artifact_id, catalog_artifact.artifact_id, geology, artifact.payload,
        )
