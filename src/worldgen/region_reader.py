"""Verified typed reader for chunked region ownership and sparse region records."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .biome_reader import VerifiedBiomeReader
from .climate_reader import VerifiedClimateReader
from .grid import DenseGridCatalog, DenseGridRepository
from .hydrology_reader import VerifiedHydrologyReader
from .physical_models import PhysicalRegion, RegionLayer

REGION_GRID_LAYER = "region_cell_region"


@dataclass(frozen=True)
class PersistedRegions:
    region_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    regions: RegionLayer
    attributes: FrozenMap


class VerifiedRegionReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-REGION-READ: {label} must be an integer")
        return value

    @classmethod
    def _integers(cls, value: object, label: str) -> tuple[int, ...]:
        if not isinstance(value, Iterable):
            raise ValueError(f"WG-REGION-READ: {label} must be iterable")
        return tuple(cls._integer(item, label) for item in value)

    @classmethod
    def _regions(cls, value: object) -> tuple[PhysicalRegion, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-REGION-READ: regions must be iterable")
        result: list[PhysicalRegion] = []
        for raw in value:
            if not isinstance(raw, Mapping) or not isinstance(raw["neighbors"], Iterable):
                raise ValueError("WG-REGION-READ: invalid region")
            result.append(PhysicalRegion(
                str(raw["region_id"]), cls._integers(raw["cells"], "region cell"),
                cls._integer(raw["center"], "region center"),
                cls._integer(raw["area_m2"], "region area"),
                cls._integers(raw["boundary_cells"], "boundary cell"),
                tuple(str(item) for item in raw["neighbors"]),
            ))
        return tuple(result)

    def load(self) -> PersistedRegions:
        hydrology = VerifiedHydrologyReader(self.root).load().hydrology
        VerifiedClimateReader(self.root).load()
        VerifiedBiomeReader(self.root).load()
        region_artifact = self.artifacts.load_verified("regions")
        catalog_artifact = self.artifacts.load_verified("region_grid_catalog")
        if not isinstance(region_artifact.payload, FrozenMap):
            raise ValueError("WG-REGION-READ: payload is not canonical")
        if "cell_region" in region_artifact.payload:
            raise ValueError("WG-REGION-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (region_artifact.artifact_id,):
            raise ValueError("WG-REGION-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-REGION-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != hydrology.watershed_id.spec:
            raise ValueError("WG-REGION-READ: catalog grid mismatch")
        if tuple(item.layer for item in catalog.manifests) != (REGION_GRID_LAYER,):
            raise ValueError("WG-REGION-READ: catalog layer set mismatch")
        owner = DenseGridRepository(self.root / "chunks").load(
            catalog.manifest(REGION_GRID_LAYER)
        )
        model = RegionLayer(
            self._integer(region_artifact.payload["algorithm_version"], "algorithm version"),
            owner, self._regions(region_artifact.payload["regions"]),
        )
        return PersistedRegions(
            region_artifact.artifact_id, catalog_artifact.artifact_id, model,
            region_artifact.payload,
        )
