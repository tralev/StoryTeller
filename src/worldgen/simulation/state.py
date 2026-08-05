"""Immutable simulation state contracts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteState:
    site_id: str
    region_id: str
    cell: int
    suitability_ppm: int
    water_access: bool
    resource_access: bool


@dataclass(frozen=True)
class SettlementState:
    settlement_id: str
    site_id: str
    civilization_id: str
    name: str
    founded_year: int
    carrying_capacity: int
    population: int


@dataclass(frozen=True)
class Cohort:
    cohort_id: str
    civilization_id: str
    site_id: str
    age_band: str
    population: int


@dataclass(frozen=True)
class EconomyState:
    grain: int
    materials: int
    currency: int
    price_grain_ppm: int


@dataclass(frozen=True)
class CivilizationState:
    civilization_id: str
    name: str
    culture: str
    government: str
    language_id: str
    capital_site_id: str
    capabilities: tuple[str, ...]
    needs: tuple[str, ...]
    territory: tuple[str, ...]
    population: int
    economy: EconomyState
    active: bool = True


@dataclass(frozen=True)
class DiplomaticRelation:
    left: str
    right: str
    status: str
    trust_ppm: int


@dataclass(frozen=True)
class SimulationState:
    year: int
    month: int
    sites: tuple[SiteState, ...]
    settlements: tuple[SettlementState, ...]
    civilizations: tuple[CivilizationState, ...]
    cohorts: tuple[Cohort, ...]
    relations: tuple[DiplomaticRelation, ...]
    applied_events: tuple[str, ...] = ()
