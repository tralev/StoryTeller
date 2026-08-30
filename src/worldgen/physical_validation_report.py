"""Immutable evidence that the published physical artifact contract was checked."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .artifact_shape_audit import embedded_dense_grid_paths
from .artifacts import WorldArtifact
from .grid import DenseGridCatalog
from .physical_dag import PHYSICAL_STAGE_DEPENDENCIES
from .physical_models import ClimateLayer, Hydrology, Terrain


@dataclass(frozen=True)
class ValidatedArtifactRecord:
    kind: str
    artifact_id: str
    sha256: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class ErosionEvidence:
    pass_count: int
    initial_mass_mm: int
    final_mass_mm: int
    thermal_moved_mm: int
    hydraulic_moved_mm: int


@dataclass(frozen=True)
class HydrologyEvidence:
    land_cell_count: int
    terminal_count: int
    lake_count: int
    river_edge_count: int
    monotonic_river_edge_count: int
    total_river_discharge_m3s: int


@dataclass(frozen=True)
class ClimateEvidence:
    season_count: int
    precipitation_total_mm: int
    evaporation_total_mm: int
    snowpack_total_mm: int
    ice_cell_seasons: int
    minimum_temperature_millic: int
    maximum_temperature_millic: int


@dataclass(frozen=True)
class PhysicalInvariantEvidence:
    erosion: ErosionEvidence
    hydrology: HydrologyEvidence
    climate: ClimateEvidence


@dataclass(frozen=True)
class PhysicalValidationReport:
    algorithm_version: int
    artifacts: tuple[ValidatedArtifactRecord, ...]
    catalog_count: int
    dense_layer_count: int
    invariants: PhysicalInvariantEvidence
    checks: tuple[str, ...]


def measure_physical_invariants(
    terrain: Terrain,
    hydrology: Hydrology,
    climate: ClimateLayer,
) -> PhysicalInvariantEvidence:
    erosion = terrain.erosion_ledger
    if any(entry.mass_before_mm != entry.mass_after_mm for entry in erosion):
        raise ValueError("WG-EROSION: nonconserving evidence")
    if any(left.mass_after_mm != right.mass_before_mm for left, right in zip(erosion, erosion[1:])):
        raise ValueError("WG-EROSION: discontinuous evidence")
    final_mass = sum(terrain.elevation_mm.values)
    if erosion and erosion[-1].mass_after_mm != final_mass:
        raise ValueError("WG-EROSION: final evidence mismatch")
    monotonic = sum(
        hydrology.flow_to.values[edge.upstream] == edge.downstream
        and hydrology.filled_elevation_mm.values[edge.downstream]
        <= hydrology.filled_elevation_mm.values[edge.upstream]
        for edge in hydrology.rivers
    )
    if monotonic != len(hydrology.rivers):
        raise ValueError("WG-RIVER: nonmonotonic evidence")
    if len(climate.seasons) != 4 or len(climate.water_ledger) != 4:
        raise ValueError("WG-CLIMATE-WATER: incomplete seasonal evidence")
    for season, ledger in zip(climate.seasons, climate.water_ledger):
        if (
            ledger.precipitation_total_mm != sum(season.precipitation_mm.values)
            or ledger.evaporation_total_mm != sum(season.evaporation_mm.values)
            or ledger.snowpack_total_mm != sum(season.snowpack_mm.values)
            or ledger.ice_cell_count != sum(season.ice.values)
        ):
            raise ValueError("WG-CLIMATE-WATER: ledger evidence mismatch")
    temperatures = tuple(
        value for season in climate.seasons for value in season.temperature_millic.values
    )
    return PhysicalInvariantEvidence(
        ErosionEvidence(
            len(erosion),
            erosion[0].mass_before_mm if erosion else final_mass,
            final_mass,
            sum(entry.thermal_moved_mm for entry in erosion),
            sum(entry.hydraulic_moved_mm for entry in erosion),
        ),
        HydrologyEvidence(
            sum(terrain.land.values),
            len(hydrology.terminals),
            len(hydrology.lakes),
            len(hydrology.rivers),
            monotonic,
            sum(edge.discharge_m3s for edge in hydrology.rivers),
        ),
        ClimateEvidence(
            len(climate.seasons),
            sum(entry.precipitation_total_mm for entry in climate.water_ledger),
            sum(entry.evaporation_total_mm for entry in climate.water_ledger),
            sum(entry.snowpack_total_mm for entry in climate.water_ledger),
            sum(entry.ice_cell_count for entry in climate.water_ledger),
            min(temperatures),
            max(temperatures),
        ),
    )


def build_physical_validation_report(
    artifacts: Sequence[WorldArtifact[object]],
    invariants: PhysicalInvariantEvidence,
) -> PhysicalValidationReport:
    by_kind = {artifact.kind: artifact for artifact in artifacts}
    if len(by_kind) != len(artifacts):
        raise ValueError("WG-ARTIFACT-CONTRACT: duplicate physical artifact kind")
    expected_kinds = set(PHYSICAL_STAGE_DEPENDENCIES) - {"validation_report", "world_index"}
    if set(by_kind) != expected_kinds:
        raise ValueError("WG-ARTIFACT-CONTRACT: physical artifact set mismatch")
    for kind, artifact in by_kind.items():
        expected_dependencies = PHYSICAL_STAGE_DEPENDENCIES[kind]
        actual_dependencies = tuple(
            sorted(by_kind[parent].artifact_id for parent in expected_dependencies)
        )
        if artifact.depends_on != actual_dependencies:
            raise ValueError(f"WG-ARTIFACT-CONTRACT: dependency mismatch for {kind}")
        violations = embedded_dense_grid_paths(artifact.payload)
        if violations:
            raise ValueError(f"WG-DENSE-JSON: {kind}:{violations[0]}")
    catalogs = [artifact for artifact in artifacts if artifact.kind.endswith("_grid_catalog")]
    layer_count = 0
    for artifact in catalogs:
        if not isinstance(artifact.payload, Mapping):
            raise ValueError(f"WG-GRID-CATALOG: invalid payload for {artifact.kind}")
        layer_count += len(DenseGridCatalog.from_mapping(artifact.payload).manifests)
    records = tuple(
        ValidatedArtifactRecord(
            artifact.kind,
            artifact.artifact_id,
            artifact.sha256,
            artifact.depends_on,
        )
        for artifact in sorted(artifacts, key=lambda item: item.kind)
    )
    return PhysicalValidationReport(
        1,
        records,
        len(catalogs),
        layer_count,
        invariants,
        (
            "WG-ARTIFACT-SET",
            "WG-DEPENDENCY-DAG",
            "WG-DENSE-JSON",
            "WG-GRID-CATALOG",
            "WG-TERRAIN-SPEC",
            "WG-PHYSICAL-INVARIANTS",
            "WG-ECOLOGY",
        ),
    )
