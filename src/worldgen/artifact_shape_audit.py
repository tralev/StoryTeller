"""Audit physical JSON artifacts for forbidden embedded dense-grid encodings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from .artifacts import WorldArtifactRepository

PHYSICAL_JSON_KINDS = (
    "plates",
    "terrain",
    "geology",
    "hydrology",
    "climate",
    "soil",
    "biomes",
    "resources",
    "species",
    "ecology",
    "regions",
    "routes",
    "spatial_index",
    "reference_index",
    "map_layers",
    "maps",
    "validation_report",
)

FORBIDDEN_DENSE_FIELDS = frozenset(
    {
        "elevation_mm",
        "plate_id",
        "plate_boundary",
        "slope_ppm",
        "land",
        "continent_id",
        "filled_elevation_mm",
        "flow_to",
        "accumulation",
        "watershed_id",
        "coastline",
        "aquifer_capacity_mm",
        "salinity_ppm",
        "snowpack_mm",
        "glacier",
        "annual_temperature_millic",
        "annual_precipitation_mm",
        "weather_regime",
        "temperature_millic",
        "precipitation_mm",
        "evaporation_mm",
        "ice",
        "storm_ppm",
        "wind_x_mmps",
        "wind_y_mmps",
        "hazard_ppm",
        "biome_id",
        "soil_depth_mm",
        "soil_fertility_ppm",
        "soil_drainage_ppm",
        "soil_erosion_class",
        "net_productivity_kg_km2",
        "carrying_capacity",
        "geology_id",
        "rock_class_id",
        "strata_id",
        "parent_material_id",
        "fault",
        "volcano",
        "tectonic_relief_mm",
        "renewable_yield",
        "cell_region",
    }
)


def embedded_dense_grid_paths(payload: object, path: str = "payload") -> tuple[str, ...]:
    """Return canonical paths of migrated grid fields or IntGrid-shaped objects."""
    found: list[str] = []
    if isinstance(payload, Mapping):
        keys = {str(key) for key in payload}
        if {"spec", "values"} <= keys:
            found.append(path)
        for key, value in payload.items():
            child = f"{path}.{key}"
            if str(key) in FORBIDDEN_DENSE_FIELDS and isinstance(value, Mapping):
                found.append(child)
            found.extend(embedded_dense_grid_paths(value, child))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, value in enumerate(payload):
            found.extend(embedded_dense_grid_paths(value, f"{path}[{index}]"))
    return tuple(sorted(set(found)))


def audit_physical_artifacts(root: str | Path) -> None:
    """Reject verified physical artifacts containing migrated dense grids in JSON."""
    repository = WorldArtifactRepository(Path(root).resolve() / "artifacts")
    violations: list[str] = []
    for kind in PHYSICAL_JSON_KINDS:
        artifact = repository.load_verified(kind)
        violations.extend(f"{kind}:{path}" for path in embedded_dense_grid_paths(artifact.payload))
    if violations:
        raise ValueError("WG-DENSE-JSON: " + ", ".join(sorted(violations)))
