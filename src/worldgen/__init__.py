"""Worldgen — procedural world generation for StoryTeller.

Deterministic algorithms (terrain, climate, biomes, civilization
simulation) using the numeric kernel and stage contracts.
"""

from __future__ import annotations

from .artifact_shape_audit import audit_physical_artifacts, embedded_dense_grid_paths
from .artifacts import (
    ArtifactDependency,
    ArtifactId,
    ChunkCoordinate,
    DependencyGraph,
    FrozenMap,
    FrozenSequence,
    GridChunk,
    ProducerFingerprint,
    WorldArtifact,
    WorldArtifactRepository,
    artifact_identity_digest,
    canonical_json,
    freeze_canonical,
)
from .biome_reader import PersistedBiomes, VerifiedBiomeReader
from .climate_reader import PersistedClimate, VerifiedClimateReader
from .geology import generate_geology
from .geology_reader import PersistedGeology, VerifiedGeologyReader
from .grid import (
    Coordinate,
    DenseGridCatalog,
    DenseGridManifest,
    DenseGridRepository,
    GridChunkDescriptor,
    GridSpec,
    IntGrid,
    LocalCoordinate,
    WorldCoordinate,
    build_grid_manifest,
    iter_grid_chunks,
    reconstruct_grid,
)
from .grid_catalog_audit import GridCatalogByteAudit, verify_catalog_chunk_bytes
from .hydrology_reader import PersistedHydrology, VerifiedHydrologyReader
from .numeric import (
    FIXED_UNIT_TYPES,
    Capacity,
    Distance,
    Elevation,
    Energy,
    Mass,
    Moisture,
    Population,
    Price,
    Probability,
    Rainfall,
    SplitMix64,
    Temperature,
    Time,
    checked_i64,
    div_floor_exact,
    div_round_half_up,
    mul_ppm,
    rng_for,
    rng_for_decision,
    stable_id,
)
from .physical_dag import PHYSICAL_STAGE_DAG, PhysicalStageNode, validate_physical_stage_dag
from .physical_models import (
    ClimateWaterLedger,
    DrainageTerminal,
    DrainageTerminalKind,
    ErosionPassLedger,
    PlateBoundaryClass,
)
from .physical_pipeline import PhysicalWorldResult, generate_physical_world
from .physical_terrain import classify_plate_boundary
from .region_reader import PersistedRegions, VerifiedRegionReader
from .resource_reader import PersistedResources, VerifiedResourceReader
from .route_reader import PersistedRoutes, VerifiedRouteReader
from .soil import generate_soil
from .soil_reader import PersistedSoil, VerifiedSoilReader
from .stages import (
    DiagnosticSeverity,
    StageDependencies,
    StageInputs,
    StageOutput,
    StageRunResult,
    StageValidationResult,
    WorldDiagnostic,
    WorldStage,
    WorldStageRunner,
)
from .terrain_reader import PersistedTerrain, VerifiedTerrainReader

__all__ = [
    "FIXED_UNIT_TYPES",
    "Capacity",
    "Distance",
    "Elevation",
    "Energy",
    "Mass",
    "Moisture",
    "Population",
    "Price",
    "Probability",
    "Rainfall",
    "Temperature",
    "Time",
    "SplitMix64",
    "checked_i64",
    "div_floor_exact",
    "div_round_half_up",
    "mul_ppm",
    "rng_for",
    "rng_for_decision",
    "stable_id",
    "DependencyGraph",
    "GridChunk",
    "ChunkCoordinate",
    "ArtifactId",
    "ArtifactDependency",
    "ProducerFingerprint",
    "WorldArtifact",
    "WorldArtifactRepository",
    "FrozenMap",
    "FrozenSequence",
    "freeze_canonical",
    "canonical_json",
    "artifact_identity_digest",
    "WorldStage",
    "WorldStageRunner",
    "StageInputs",
    "StageDependencies",
    "StageOutput",
    "StageRunResult",
    "StageValidationResult",
    "WorldDiagnostic",
    "DiagnosticSeverity",
    "Coordinate",
    "WorldCoordinate",
    "LocalCoordinate",
    "GridSpec",
    "IntGrid",
    "GridChunkDescriptor",
    "DenseGridManifest",
    "DenseGridCatalog",
    "DenseGridRepository",
    "iter_grid_chunks",
    "build_grid_manifest",
    "reconstruct_grid",
    "PhysicalWorldResult",
    "generate_physical_world",
    "PersistedTerrain",
    "VerifiedTerrainReader",
    "PersistedHydrology",
    "VerifiedHydrologyReader",
    "PersistedClimate",
    "VerifiedClimateReader",
    "PersistedBiomes",
    "VerifiedBiomeReader",
    "PersistedResources",
    "VerifiedResourceReader",
    "PersistedRegions",
    "VerifiedRegionReader",
    "PersistedRoutes",
    "VerifiedRouteReader",
    "audit_physical_artifacts",
    "embedded_dense_grid_paths",
    "GridCatalogByteAudit",
    "verify_catalog_chunk_bytes",
    "PHYSICAL_STAGE_DAG",
    "PhysicalStageNode",
    "validate_physical_stage_dag",
    "PlateBoundaryClass",
    "ErosionPassLedger",
    "DrainageTerminal",
    "DrainageTerminalKind",
    "ClimateWaterLedger",
    "classify_plate_boundary",
    "generate_geology",
    "PersistedGeology",
    "VerifiedGeologyReader",
    "generate_soil",
    "PersistedSoil",
    "VerifiedSoilReader",
]
