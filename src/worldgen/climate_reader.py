"""Verified typed reader for chunked persisted climate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactId, FrozenMap, WorldArtifactRepository
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .hydrology_reader import VerifiedHydrologyReader
from .physical_models import ClimateLayer, ClimateWaterLedger, SeasonProfile


def climate_layer_names(season_count: int) -> dict[str, str]:
    result = {
        "annual_temperature_millic": "climate_annual_temperature_millic",
        "annual_precipitation_mm": "climate_annual_precipitation_mm",
        "weather_regime": "climate_weather_regime",
    }
    for index in range(season_count):
        prefix = f"climate_season_{index:02d}"
        for field in (
            "temperature_millic",
            "precipitation_mm",
            "evaporation_mm",
            "snowpack_mm",
            "ice",
            "storm_ppm",
            "wind_x_mmps",
            "wind_y_mmps",
            "hazard_ppm",
        ):
            result[f"season_{index:02d}_{field}"] = f"{prefix}_{field}"
    return result


@dataclass(frozen=True)
class PersistedClimate:
    climate_artifact_id: ArtifactId
    grid_catalog_id: ArtifactId
    climate: ClimateLayer
    attributes: FrozenMap


class VerifiedClimateReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.artifacts = WorldArtifactRepository(self.root / "artifacts")

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"WG-CLIMATE-READ: {label} must be an integer")
        return value

    @classmethod
    def _water_ledger(cls, value: object) -> tuple[ClimateWaterLedger, ...]:
        if not isinstance(value, Iterable):
            raise ValueError("WG-CLIMATE-READ: water ledger must be iterable")
        result: list[ClimateWaterLedger] = []
        for raw in value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-CLIMATE-READ: invalid water ledger")
            result.append(
                ClimateWaterLedger(
                    *(
                        cls._integer(raw[field], field)
                        for field in (
                            "season",
                            "precipitation_total_mm",
                            "evaporation_total_mm",
                            "snowpack_total_mm",
                            "ice_cell_count",
                            "final_atmospheric_moisture_mm",
                        )
                    )
                )
            )
        return tuple(result)

    def load(self) -> PersistedClimate:
        hydrology = VerifiedHydrologyReader(self.root).load().hydrology
        climate_artifact = self.artifacts.load_verified("climate")
        catalog_artifact = self.artifacts.load_verified("climate_grid_catalog")
        if not isinstance(climate_artifact.payload, FrozenMap):
            raise ValueError("WG-CLIMATE-READ: payload is not canonical")
        season_count = self._integer(climate_artifact.payload["season_count"], "season count")
        if not 1 <= season_count <= 12:
            raise ValueError("WG-CLIMATE-READ: season count outside 1..12")
        if catalog_artifact.depends_on != (climate_artifact.artifact_id,):
            raise ValueError("WG-CLIMATE-READ: catalog dependency mismatch")
        if not isinstance(catalog_artifact.payload, Mapping):
            raise ValueError("WG-CLIMATE-READ: catalog is not a mapping")
        catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
        if catalog.grid != hydrology.flow_to.spec:
            raise ValueError("WG-CLIMATE-READ: catalog grid mismatch")
        names = climate_layer_names(season_count)
        if {item.layer for item in catalog.manifests} != set(names.values()):
            raise ValueError("WG-CLIMATE-READ: catalog layer set mismatch")
        chunks = DenseGridRepository(self.root / "chunks")
        dense: dict[str, IntGrid[int]] = {
            field: chunks.load(catalog.manifest(layer)) for field, layer in names.items()
        }
        seasons = tuple(
            SeasonProfile(
                dense[f"season_{index:02d}_temperature_millic"],
                dense[f"season_{index:02d}_precipitation_mm"],
                dense[f"season_{index:02d}_evaporation_mm"],
                dense[f"season_{index:02d}_snowpack_mm"],
                dense[f"season_{index:02d}_ice"],
                dense[f"season_{index:02d}_storm_ppm"],
                dense[f"season_{index:02d}_wind_x_mmps"],
                dense[f"season_{index:02d}_wind_y_mmps"],
                dense[f"season_{index:02d}_hazard_ppm"],
            )
            for index in range(season_count)
        )
        model = ClimateLayer(
            self._integer(climate_artifact.payload["algorithm_version"], "algorithm version"),
            seasons,
            self._water_ledger(climate_artifact.payload["water_ledger"]),
            dense["annual_temperature_millic"],
            dense["annual_precipitation_mm"],
            dense["weather_regime"],
        )
        return PersistedClimate(
            climate_artifact.artifact_id,
            catalog_artifact.artifact_id,
            model,
            climate_artifact.payload,
        )
