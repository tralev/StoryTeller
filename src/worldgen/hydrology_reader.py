"""Verified typed reader for chunked persisted hydrology."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .physical_models import (DrainageTerminal, DrainageTerminalKind, Hydrology,
                              Lake, RiverEdge)
from .terrain_reader import VerifiedTerrainReader

HYDROLOGY_GRID_LAYERS = {
    "filled_elevation_mm": "hydrology_filled_elevation_mm",
    "flow_to": "hydrology_flow_to",
    "accumulation": "hydrology_accumulation",
    "watershed_id": "hydrology_watershed_id",
    "coastline": "hydrology_coastline",
    "aquifer_capacity_mm": "hydrology_aquifer_capacity_mm",
    "salinity_ppm": "hydrology_salinity_ppm",
    "snowpack_mm": "hydrology_snowpack_mm",
    "glacier": "hydrology_glacier",
    "delta": "hydrology_delta",
}


@dataclass(frozen=True)
class PersistedHydrology:
    hydrology_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    hydrology: Hydrology
    attributes: FrozenMap


class VerifiedHydrologyReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-HYDROLOGY-READ: {label} must be an integer")
        return value

    @classmethod
    def _lakes(cls, value: object) -> tuple[Lake, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-HYDROLOGY-READ: lakes must be iterable")
        result: list[Lake] = []
        for raw in value:
            if not isinstance(raw, Mapping) or not isinstance(raw["cells"], Iterable):
                raise ValueError("WG-HYDROLOGY-READ: invalid lake")
            outlet = raw["outlet"]
            result.append(Lake(
                str(raw["lake_id"]), tuple(cls._integer(item, "lake cell") for item in raw["cells"]),
                None if raw["spillway_cell"] is None else cls._integer(raw["spillway_cell"], "lake spillway"),
                None if outlet is None else cls._integer(outlet, "lake outlet"),
                cls._integer(raw["surface_elevation_mm"], "lake elevation"),
            ))
        return tuple(result)

    @classmethod
    def _rivers(cls, value: object) -> tuple[RiverEdge, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-HYDROLOGY-READ: rivers must be iterable")
        result: list[RiverEdge] = []
        for raw in value:
            if not isinstance(raw, Mapping) or not isinstance(raw["seasonal_discharge_m3s"], Iterable):
                raise ValueError("WG-HYDROLOGY-READ: invalid river")
            seasonal = tuple(cls._integer(item, "seasonal discharge")
                             for item in raw["seasonal_discharge_m3s"])
            if len(seasonal) != 4:
                raise ValueError("WG-HYDROLOGY-READ: river requires four seasons")
            result.append(RiverEdge(
                cls._integer(raw["upstream"], "river upstream"),
                cls._integer(raw["downstream"], "river downstream"),
                cls._integer(raw["discharge_m3s"], "river discharge"), seasonal,
            ))
        return tuple(result)

    @classmethod
    def _terminals(cls, value: object) -> tuple[DrainageTerminal, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-HYDROLOGY-READ: terminals must be iterable")
        result: list[DrainageTerminal] = []
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-HYDROLOGY-READ: invalid drainage terminal")
            try:
                kind = DrainageTerminalKind(cls._integer(raw["kind"], "terminal kind"))
            except ValueError as error:
                raise ValueError("WG-HYDROLOGY-READ: invalid terminal kind") from error
            result.append(DrainageTerminal(
                str(raw["terminal_id"]), cls._integer(raw["cell"], "terminal cell"),
                kind, cls._integer(raw["watershed_id"], "terminal watershed"),
            ))
        return tuple(result)

    def load(self) -> PersistedHydrology:
        terrain = VerifiedTerrainReader(self.root).load().terrain
        hydrology_artifact = self.artifacts.load_verified("hydrology")
        catalog_artifact = self.artifacts.load_verified("hydrology_grid_catalog")
        if not isinstance(hydrology_artifact.payload, FrozenMap):
            raise ValueError("WG-HYDROLOGY-READ: payload is not canonical")
        if any(field in hydrology_artifact.payload for field in HYDROLOGY_GRID_LAYERS):
            raise ValueError("WG-HYDROLOGY-READ: duplicate embedded grid is forbidden")
        if catalog_artifact.depends_on != (hydrology_artifact.artifact_id,):
            raise ValueError("WG-HYDROLOGY-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-HYDROLOGY-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != terrain.grid:
            raise ValueError("WG-HYDROLOGY-READ: catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(HYDROLOGY_GRID_LAYERS.values()):
            raise ValueError("WG-HYDROLOGY-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer))
            for field, layer in HYDROLOGY_GRID_LAYERS.items()
        }
        model = Hydrology(
            self._integer(hydrology_artifact.payload["algorithm_version"], "algorithm version"),
            dense["filled_elevation_mm"], dense["flow_to"], dense["accumulation"],
            dense["watershed_id"], dense["coastline"], dense["aquifer_capacity_mm"],
            dense["salinity_ppm"], dense["snowpack_mm"], dense["glacier"], dense["delta"],
            self._terminals(hydrology_artifact.payload["terminals"]),
            self._lakes(hydrology_artifact.payload["lakes"]),
            self._rivers(hydrology_artifact.payload["rivers"]),
        )
        return PersistedHydrology(
            hydrology_artifact.artifact_id, catalog_artifact.artifact_id, model,
            hydrology_artifact.payload,
        )
