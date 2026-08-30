"""Verified typed reader for fully chunked persisted terrain."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .grid import DenseGridCatalog, DenseGridRepository, GridSpec, IntGrid
from .physical_models import ErosionPassLedger, Plate, Terrain

TERRAIN_GRID_LAYERS = {
    "elevation_mm": "terrain_elevation_mm",
    "plate_id": "terrain_plate_id",
    "plate_boundary": "terrain_plate_boundary",
    "slope_ppm": "terrain_slope_ppm",
    "land": "terrain_land",
    "continent_id": "terrain_continent_id",
}


@dataclass(frozen=True)
class PersistedTerrain:
    terrain_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    terrain: Terrain
    attributes: FrozenMap

    @property
    def grid(self) -> GridSpec:
        return self.terrain.grid

    @property
    def elevation_mm(self) -> IntGrid[int]:
        return self.terrain.elevation_mm


class VerifiedTerrainReader:
    """Reconstruct the complete authoritative Terrain from verified chunks."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-TERRAIN-READ: {label} must be an integer")
        return value

    @classmethod
    def _grid(cls, value: object) -> GridSpec:
        if not isinstance(value, Mapping):
            raise ValueError("WG-TERRAIN-READ: terrain grid is not a mapping")
        return GridSpec(
            cls._integer(value.get("width"), "width"),
            cls._integer(value.get("height"), "height"),
            cls._integer(value.get("metres_per_world_cell"), "metres_per_world_cell"),
        )

    @classmethod
    def _plates(cls, value: object) -> tuple[Plate, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-TERRAIN-READ: plates must be iterable")
        plates: list[Plate] = []
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-TERRAIN-READ: invalid plate")
            plates.append(
                Plate(
                    str(raw["plate_id"]),
                    cls._integer(raw["center"], "plate center"),
                    cls._integer(raw["motion_x_ppm"], "plate motion x"),
                    cls._integer(raw["motion_y_ppm"], "plate motion y"),
                )
            )
        return tuple(plates)

    @classmethod
    def _erosion_ledger(cls, value: object) -> tuple[ErosionPassLedger, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-TERRAIN-READ: invalid erosion ledger")
        result: list[ErosionPassLedger] = []
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-TERRAIN-READ: invalid erosion pass")
            result.append(
                ErosionPassLedger(
                    cls._integer(raw["pass_index"], "erosion pass index"),
                    cls._integer(raw["mass_before_mm"], "mass before"),
                    cls._integer(raw["thermal_moved_mm"], "thermal moved"),
                    cls._integer(raw["hydraulic_moved_mm"], "hydraulic moved"),
                    cls._integer(raw["mass_after_mm"], "mass after"),
                )
            )
        return tuple(result)

    def load(self) -> PersistedTerrain:
        terrain_artifact = self.artifacts.load_verified("terrain")
        catalog_artifact = self.artifacts.load_verified("terrain_grid_catalog")
        geology = self.artifacts.load_verified("geology")
        if not isinstance(terrain_artifact.payload, FrozenMap):
            raise ValueError("WG-TERRAIN-READ: terrain payload is not canonical")
        if any(field in terrain_artifact.payload for field in TERRAIN_GRID_LAYERS):
            raise ValueError("WG-TERRAIN-READ: duplicate embedded terrain grid is forbidden")
        if "plate_id" in geology.payload or "elevation_mm" in geology.payload:
            raise ValueError("WG-TERRAIN-READ: duplicate embedded geology grid is forbidden")
        if catalog_artifact.depends_on != (terrain_artifact.artifact_id,):
            raise ValueError("WG-TERRAIN-READ: terrain catalog dependency mismatch")
        if catalog_artifact.artifact_id not in geology.depends_on:
            raise ValueError("WG-TERRAIN-READ: geology catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-TERRAIN-READ: terrain catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        grid = self._grid(terrain_artifact.payload["grid"])
        if catalog.grid != grid:
            raise ValueError("WG-TERRAIN-READ: terrain catalog grid mismatch")
        if {item.layer for item in catalog.manifests} != set(TERRAIN_GRID_LAYERS.values()):
            raise ValueError("WG-TERRAIN-READ: terrain catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense = {
            field: chunks.load(catalog.manifest(layer))
            for field, layer in TERRAIN_GRID_LAYERS.items()
        }
        terrain = Terrain(
            self._integer(terrain_artifact.payload["algorithm_version"], "algorithm version"),
            grid,
            self._plates(terrain_artifact.payload["plates"]),
            dense["plate_id"],
            dense["plate_boundary"],
            dense["elevation_mm"],
            dense["slope_ppm"],
            dense["land"],
            dense["continent_id"],
            self._erosion_ledger(terrain_artifact.payload["erosion_ledger"]),
        )
        return PersistedTerrain(
            terrain_artifact.artifact_id,
            catalog_artifact.artifact_id,
            terrain,
            terrain_artifact.payload,
        )
