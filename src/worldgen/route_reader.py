"""Verified typed reader for the sparse persisted route graph."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .region_reader import VerifiedRegionReader
from .physical_models import Route, RouteKind, RouteLayer


@dataclass(frozen=True)
class PersistedRoutes:
    route_artifact_id: ArtifactId
    routes: RouteLayer
    attributes: FrozenMap


class VerifiedRouteReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-ROUTE-READ: {label} must be an integer")
        return value

    @classmethod
    def _integers(cls, value: object, label: str, *, length: int | None = None) -> tuple[int, ...]:
        if not isinstance(value, Iterable):
            raise ValueError(f"WG-ROUTE-READ: {label} must be iterable")
        result = tuple(cls._integer(item, label) for item in value)
        if length is not None and len(result) != length:
            raise ValueError(f"WG-ROUTE-READ: {label} requires {length} values")
        return result

    @classmethod
    def _four(cls, value: object, label: str) -> tuple[int, int, int, int]:
        result = cls._integers(value, label, length=4)
        return result[0], result[1], result[2], result[3]

    @staticmethod
    def _bool_four(value: object, label: str) -> tuple[bool, bool, bool, bool]:
        if not isinstance(value, Iterable):
            raise ValueError(f"WG-ROUTE-READ: {label} must be iterable")
        result = tuple(value)
        if len(result) != 4 or any(not isinstance(item, bool) for item in result):
            raise ValueError(f"WG-ROUTE-READ: {label} requires four booleans")
        return result[0], result[1], result[2], result[3]

    @classmethod
    def _seasonal_cells(cls, value: object) -> tuple[tuple[int, ...], tuple[int, ...],
                                                       tuple[int, ...], tuple[int, ...]]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-ROUTE-READ: seasonal cells must be iterable")
        paths = tuple(cls._integers(path, "seasonal route cell") for path in value)
        if len(paths) != 4:
            raise ValueError("WG-ROUTE-READ: seasonal cells require four paths")
        return paths[0], paths[1], paths[2], paths[3]

    def load(self) -> PersistedRoutes:
        regions = VerifiedRegionReader(self.root).load()
        artifact = self.artifacts.load_verified("routes")
        if not isinstance(artifact.payload, FrozenMap):
            raise ValueError("WG-ROUTE-READ: payload is not canonical")
        if regions.region_artifact_id not in artifact.depends_on:
            raise ValueError("WG-ROUTE-READ: region dependency mismatch")
        if regions.grid_catalog_id not in artifact.depends_on:
            raise ValueError("WG-ROUTE-READ: region catalog dependency mismatch")
        raw_routes = artifact.payload["routes"]
        if not isinstance(raw_routes, Iterable):
            raise ValueError("WG-ROUTE-READ: routes must be iterable")
        valid_regions = {item.region_id for item in regions.regions.regions}
        routes: list[Route] = []
        for raw in raw_routes:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-ROUTE-READ: invalid route")
            start, end = str(raw["start_region"]), str(raw["end_region"])
            cells = self._integers(raw["cells"], "route cell")
            if start not in valid_regions or end not in valid_regions or not cells:
                raise ValueError("WG-ROUTE-READ: invalid endpoint or geometry")
            if any(cell < 0 or cell >= regions.regions.cell_region.spec.cell_count for cell in cells):
                raise ValueError("WG-ROUTE-READ: route cell outside world")
            routes.append(Route(
                str(raw["route_id"]), start, end, cells,
                self._integer(raw["distance_m"], "distance"),
                self._integer(raw["terrain_cost"], "terrain cost"),
                self._integer(raw["river_crossings"], "river crossings"),
                self._four(raw["seasonal_risk_ppm"], "seasonal risk"),
                self._four(raw["seasonal_capacity"], "seasonal capacity"),
                RouteKind(self._integer(raw["route_kind"], "route kind")),
                self._seasonal_cells(raw["seasonal_cells"]),
                self._bool_four(raw["traversable_seasons"], "traversable seasons"),
                str(raw["cost_unit"]),
                self._integer(raw["annual_maintenance"], "annual maintenance"),
                tuple(str(item) for item in raw["source_ids"]),
            ))
        model = RouteLayer(
            self._integer(artifact.payload["algorithm_version"], "algorithm version"),
            tuple(routes),
        )
        return PersistedRoutes(artifact.artifact_id, model, artifact.payload)
