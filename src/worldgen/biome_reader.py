"""Verified typed reader for chunked biome and soil fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .climate_reader import VerifiedClimateReader
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .physical_models import BiomeLayer
from .soil_reader import VerifiedSoilReader

BIOME_GRID_LAYERS = {
    "biome_id": "biome_id",
    "net_productivity_kg_km2": "biome_net_productivity_kg_km2",
    "carrying_capacity": "biome_carrying_capacity",
}


@dataclass(frozen=True)
class PersistedBiomes:
    biome_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    soil_artifact_id: ArtifactId
    biomes: BiomeLayer
    attributes: FrozenMap


class VerifiedBiomeReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-BIOME-READ: {label} must be an integer")
        return value

    def load(self) -> PersistedBiomes:
        climate = VerifiedClimateReader(self.root).load().climate
        biome_artifact = self.artifacts.load_verified("biomes")
        catalog_artifact = self.artifacts.load_verified("biome_grid_catalog")
        soil = VerifiedSoilReader(self.root).load()
        if not isinstance(biome_artifact.payload, FrozenMap):
            raise ValueError("WG-BIOME-READ: payload is not canonical")
        if any(field in biome_artifact.payload for field in BIOME_GRID_LAYERS):
            raise ValueError("WG-BIOME-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (biome_artifact.artifact_id,):
            raise ValueError("WG-BIOME-READ: catalog dependency mismatch")
        if soil.grid_catalog_id not in biome_artifact.depends_on:
            raise ValueError("WG-BIOME-READ: soil catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-BIOME-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != climate.weather_regime.spec:
            raise ValueError("WG-BIOME-READ: catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(BIOME_GRID_LAYERS.values()):
            raise ValueError("WG-BIOME-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer))
            for field, layer in BIOME_GRID_LAYERS.items()
        }
        model = BiomeLayer(
            self._integer(biome_artifact.payload["algorithm_version"], "algorithm version"),
            dense["biome_id"],
            dense["net_productivity_kg_km2"],
            dense["carrying_capacity"],
        )
        return PersistedBiomes(
            biome_artifact.artifact_id,
            catalog_artifact.artifact_id,
            soil.soil_artifact_id,
            model,
            biome_artifact.payload,
        )
