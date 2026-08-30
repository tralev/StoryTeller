"""Verified typed reader for the independent soil grid catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .climate_reader import VerifiedClimateReader
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .physical_models import SoilLayer

SOIL_GRID_LAYERS = {
    "depth_mm": "soil_depth_mm",
    "fertility_ppm": "soil_fertility_ppm",
    "drainage_ppm": "soil_drainage_ppm",
    "erosion_class": "soil_erosion_class",
}


@dataclass(frozen=True)
class PersistedSoil:
    soil_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    soil: SoilLayer
    attributes: FrozenMap


class VerifiedSoilReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-SOIL-READ: {label} must be an integer")
        return value

    def load(self) -> PersistedSoil:
        climate = VerifiedClimateReader(self.root).load().climate
        artifact = self.artifacts.load_verified("soil")
        catalog_artifact = self.artifacts.load_verified("soil_grid_catalog")
        if not isinstance(artifact.payload, FrozenMap):
            raise ValueError("WG-SOIL-READ: payload is not canonical")
        if any(field in artifact.payload for field in SOIL_GRID_LAYERS):
            raise ValueError("WG-SOIL-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (artifact.artifact_id,):
            raise ValueError("WG-SOIL-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-SOIL-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != climate.weather_regime.spec:
            raise ValueError("WG-SOIL-READ: catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(SOIL_GRID_LAYERS.values()):
            raise ValueError("WG-SOIL-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer)) for field, layer in SOIL_GRID_LAYERS.items()
        }
        model = SoilLayer(
            self._integer(artifact.payload["algorithm_version"], "algorithm version"),
            dense["depth_mm"],
            dense["fertility_ppm"],
            dense["drainage_ppm"],
            dense["erosion_class"],
        )
        return PersistedSoil(
            artifact.artifact_id, catalog_artifact.artifact_id, model, artifact.payload
        )
