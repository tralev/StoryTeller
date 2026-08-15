"""Verified typed reader for chunked geology and renewable-resource fields."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .biome_reader import VerifiedBiomeReader
from .geology_reader import VerifiedGeologyReader
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .physical_models import Deposit, ResourceLayer
from .terrain_reader import VerifiedTerrainReader

RESOURCE_GRID_LAYERS = {
    "renewable_yield": "resource_renewable_yield",
}


@dataclass(frozen=True)
class PersistedResources:
    resource_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    resources: ResourceLayer
    attributes: FrozenMap


class VerifiedResourceReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-RESOURCE-READ: {label} must be an integer")
        return value

    @staticmethod
    def _boolean(value: object, label: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"WG-RESOURCE-READ: {label} must be a boolean")
        return value

    @classmethod
    def _deposits(cls, value: object) -> tuple[Deposit, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-RESOURCE-READ: deposits must be iterable")
        deposits: list[Deposit] = []
        for raw in value:
            if not isinstance(raw, Mapping) or not isinstance(raw["cells"], Iterable):
                raise ValueError("WG-RESOURCE-READ: invalid deposit")
            deposits.append(Deposit(
                str(raw["deposit_id"]), str(raw["resource"]),
                tuple(cls._integer(item, "deposit cell") for item in raw["cells"]),
                cls._integer(raw["depth_mm"], "deposit depth"),
                cls._integer(raw["grade_ppm"], "deposit grade"),
                cls._integer(raw["quantity_kg"], "deposit quantity"),
                cls._integer(raw["rock_class_id"], "deposit rock class"),
                cls._integer(raw["strata_id"], "deposit strata"),
                cls._boolean(raw["fault_related"], "fault provenance"),
                cls._boolean(raw["volcanic_related"], "volcanic provenance"),
            ))
        return tuple(deposits)

    def load(self) -> PersistedResources:
        terrain = VerifiedTerrainReader(self.root).load().terrain
        geology = VerifiedGeologyReader(self.root).load().geology
        VerifiedBiomeReader(self.root).load()
        resource_artifact = self.artifacts.load_verified("resources")
        catalog_artifact = self.artifacts.load_verified("resource_grid_catalog")
        if not isinstance(resource_artifact.payload, FrozenMap):
            raise ValueError("WG-RESOURCE-READ: payload is not canonical")
        if any(field in resource_artifact.payload for field in RESOURCE_GRID_LAYERS):
            raise ValueError("WG-RESOURCE-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (resource_artifact.artifact_id,):
            raise ValueError("WG-RESOURCE-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-RESOURCE-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != terrain.grid:
            raise ValueError("WG-RESOURCE-READ: catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(RESOURCE_GRID_LAYERS.values()):
            raise ValueError("WG-RESOURCE-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer))
            for field, layer in RESOURCE_GRID_LAYERS.items()
        }
        model = ResourceLayer(
            self._integer(resource_artifact.payload["algorithm_version"], "algorithm version"),
            geology.rock_class_id, geology.strata_id, geology.parent_material_id,
            geology.fault, geology.volcano, dense["renewable_yield"],
            self._deposits(resource_artifact.payload["deposits"]),
        )
        return PersistedResources(
            resource_artifact.artifact_id, catalog_artifact.artifact_id, model,
            resource_artifact.payload,
        )
