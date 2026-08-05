"""Immutable contracts for the authoritative Phase 2 physical world."""
from __future__ import annotations

from dataclasses import dataclass

from .grid import GridSpec, IntGrid


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
    plate_boundary: IntGrid[int]  # 0 interior, 1 convergent, 2 divergent, 3 transform
    elevation_mm: IntGrid[int]
    slope_ppm: IntGrid[int]
    land: IntGrid[int]
    continent_id: IntGrid[int]
    adjustment_ledger_mm: tuple[int, ...]


@dataclass(frozen=True)
class Lake:
    lake_id: str
    cells: tuple[int, ...]
    outlet: int | None
    surface_elevation_mm: int


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
    lakes: tuple[Lake, ...]
    rivers: tuple[RiverEdge, ...]


@dataclass(frozen=True)
class SeasonProfile:
    temperature_millic: IntGrid[int]
    precipitation_mm: IntGrid[int]
    wind_x_mmps: IntGrid[int]
    wind_y_mmps: IntGrid[int]
    hazard_ppm: IntGrid[int]


@dataclass(frozen=True)
class ClimateLayer:
    algorithm_version: int
    seasons: tuple[SeasonProfile, ...]
    annual_temperature_millic: IntGrid[int]
    annual_precipitation_mm: IntGrid[int]
    weather_regime: IntGrid[int]


@dataclass(frozen=True)
class BiomeLayer:
    algorithm_version: int
    biome_id: IntGrid[int]
    soil_fertility_ppm: IntGrid[int]
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
class EcologyLayer:
    algorithm_version: int
    species: tuple[Species, ...]
    food_web: tuple[FoodWebEdge, ...]
    migration_corridors: tuple[tuple[int, ...], ...]


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


@dataclass(frozen=True)
class RouteLayer:
    algorithm_version: int
    routes: tuple[Route, ...]
