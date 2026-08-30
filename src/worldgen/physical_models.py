"""Immutable contracts for the authoritative Phase 2 physical world."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .grid import GridSpec, IntGrid


class PlateBoundaryClass(IntEnum):
    INTERIOR = 0
    CONVERGENT = 1
    DIVERGENT = 2
    TRANSFORM = 3


@dataclass(frozen=True)
class ErosionPassLedger:
    pass_index: int
    mass_before_mm: int
    thermal_moved_mm: int
    hydraulic_moved_mm: int
    mass_after_mm: int


@dataclass(frozen=True)
class Plate:
    plate_id: str
    center: int
    motion_x_ppm: int
    motion_y_ppm: int


@dataclass(frozen=True)
class Terrain:
    algorithm_version: int
    grid: GridSpec
    plates: tuple[Plate, ...]
    plate_id: IntGrid[int]
    plate_boundary: IntGrid[int]  # PlateBoundaryClass values
    elevation_mm: IntGrid[int]
    slope_ppm: IntGrid[int]
    land: IntGrid[int]
    continent_id: IntGrid[int]
    erosion_ledger: tuple[ErosionPassLedger, ...]


@dataclass(frozen=True)
class GeologyLayer:
    algorithm_version: int
    rock_class_id: IntGrid[int]
    strata_id: IntGrid[int]
    parent_material_id: IntGrid[int]
    fault: IntGrid[int]
    volcano: IntGrid[int]
    tectonic_relief_mm: IntGrid[int]


@dataclass(frozen=True)
class Lake:
    lake_id: str
    cells: tuple[int, ...]
    spillway_cell: int | None
    outlet: int | None
    surface_elevation_mm: int


class DrainageTerminalKind(IntEnum):
    OCEAN = 1
    CLOSED_BASIN = 2


@dataclass(frozen=True)
class DrainageTerminal:
    terminal_id: str
    cell: int
    kind: DrainageTerminalKind
    watershed_id: int


@dataclass(frozen=True)
class RiverEdge:
    upstream: int
    downstream: int
    discharge_m3s: int
    seasonal_discharge_m3s: tuple[int, int, int, int]


@dataclass(frozen=True)
class Hydrology:
    algorithm_version: int
    filled_elevation_mm: IntGrid[int]
    flow_to: IntGrid[int]
    accumulation: IntGrid[int]
    watershed_id: IntGrid[int]
    coastline: IntGrid[int]
    aquifer_capacity_mm: IntGrid[int]
    salinity_ppm: IntGrid[int]
    snowpack_mm: IntGrid[int]
    glacier: IntGrid[int]
    delta: IntGrid[int]
    terminals: tuple[DrainageTerminal, ...]
    lakes: tuple[Lake, ...]
    rivers: tuple[RiverEdge, ...]


@dataclass(frozen=True)
class SeasonProfile:
    temperature_millic: IntGrid[int]
    precipitation_mm: IntGrid[int]
    evaporation_mm: IntGrid[int]
    snowpack_mm: IntGrid[int]
    ice: IntGrid[int]
    storm_ppm: IntGrid[int]
    wind_x_mmps: IntGrid[int]
    wind_y_mmps: IntGrid[int]
    hazard_ppm: IntGrid[int]


@dataclass(frozen=True)
class ClimateWaterLedger:
    season: int
    precipitation_total_mm: int
    evaporation_total_mm: int
    snowpack_total_mm: int
    ice_cell_count: int
    final_atmospheric_moisture_mm: int


@dataclass(frozen=True)
class ClimateLayer:
    algorithm_version: int
    seasons: tuple[SeasonProfile, ...]
    water_ledger: tuple[ClimateWaterLedger, ...]
    annual_temperature_millic: IntGrid[int]
    annual_precipitation_mm: IntGrid[int]
    weather_regime: IntGrid[int]


@dataclass(frozen=True)
class SoilLayer:
    algorithm_version: int
    depth_mm: IntGrid[int]
    fertility_ppm: IntGrid[int]
    drainage_ppm: IntGrid[int]
    erosion_class: IntGrid[int]


@dataclass(frozen=True)
class BiomeLayer:
    algorithm_version: int
    biome_id: IntGrid[int]
    net_productivity_kg_km2: IntGrid[int]
    carrying_capacity: IntGrid[int]


@dataclass(frozen=True)
class Deposit:
    deposit_id: str
    resource: str
    cells: tuple[int, ...]
    depth_mm: int
    grade_ppm: int
    quantity_kg: int
    rock_class_id: int
    strata_id: int
    fault_related: bool
    volcanic_related: bool


@dataclass(frozen=True)
class ResourceLayer:
    algorithm_version: int
    geology_id: IntGrid[int]
    strata_id: IntGrid[int]
    parent_material_id: IntGrid[int]
    fault: IntGrid[int]
    volcano: IntGrid[int]
    renewable_yield: IntGrid[int]
    deposits: tuple[Deposit, ...]


@dataclass(frozen=True)
class Species:
    species_id: str
    trophic_level: int
    habitat_biomes: tuple[int, ...]
    annual_energy_kj: int
    extinct: bool


@dataclass(frozen=True)
class FoodWebEdge:
    predator: str
    prey: str
    transferred_energy_kj: int


@dataclass(frozen=True)
class RegionalSpeciesPopulation:
    species_id: str
    region_id: str
    habitat_suitability_ppm: int
    carrying_capacity: int
    population: int
    extinct: bool


@dataclass(frozen=True)
class EcologyTransition:
    year: int
    species_id: str
    region_id: str
    population_before: int
    births: int
    deaths: int
    immigrants: int
    emigrants: int
    population_after: int


@dataclass(frozen=True)
class EcologyLayer:
    algorithm_version: int
    species: tuple[Species, ...]
    food_web: tuple[FoodWebEdge, ...]
    migration_corridors: tuple[tuple[int, ...], ...]
    regional_populations: tuple[RegionalSpeciesPopulation, ...]
    transition_ledger: tuple[EcologyTransition, ...]


@dataclass(frozen=True)
class PhysicalRegion:
    region_id: str
    cells: tuple[int, ...]
    center: int
    area_m2: int
    boundary_cells: tuple[int, ...]
    neighbors: tuple[str, ...]


@dataclass(frozen=True)
class RegionLayer:
    algorithm_version: int
    cell_region: IntGrid[int]
    regions: tuple[PhysicalRegion, ...]


class RouteKind(IntEnum):
    ROAD = 1
    TRAIL = 2
    NAVIGABLE_RIVER = 3
    SEA_LANE = 4
    MOUNTAIN_PASS = 5
    SETTLEMENT_LINK = 6


@dataclass(frozen=True)
class Route:
    route_id: str
    start_region: str
    end_region: str
    cells: tuple[int, ...]
    distance_m: int
    terrain_cost: int
    river_crossings: int
    seasonal_risk_ppm: tuple[int, int, int, int]
    seasonal_capacity: tuple[int, int, int, int]
    route_kind: RouteKind
    seasonal_cells: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]
    traversable_seasons: tuple[bool, bool, bool, bool]
    cost_unit: str
    annual_maintenance: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class RouteLayer:
    algorithm_version: int
    routes: tuple[Route, ...]
