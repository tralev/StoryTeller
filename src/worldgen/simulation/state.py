"""Immutable simulation state contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class SiteState:
    site_id: str
    region_id: str
    cell: int
    suitability_ppm: int
    water_access: bool
    resource_access: bool
    score_components: tuple[tuple[str, int], ...]


class SettlementStatus(str, Enum):
    INHABITED = "inhabited"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class InventoryStack:
    material_id: str
    quantity: int


@dataclass(frozen=True)
class WorkshopState:
    workshop_id: str
    workshop_kind: str
    recipe_id: str
    input_material: str
    output_material: str
    ratio_ppm: int


@dataclass(frozen=True)
class SettlementState:
    settlement_id: str
    site_id: str
    civilization_id: str
    name: str
    founded_year: int
    carrying_capacity: int
    population: int
    status: SettlementStatus
    abandoned_year: int | None
    land_use: tuple[str, ...]
    buildings: tuple[str, ...]
    workshops: tuple[WorkshopState, ...]
    inventory: tuple[InventoryStack, ...]


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
class ResourceStock:
    stock_id: str
    resource: str
    region_id: str
    renewable: bool
    capacity_kg: int
    quantity_kg: int
    regeneration_kg: int


@dataclass(frozen=True)
class EconomyLedgerEntry:
    event_id: str
    year: int
    month: int
    kind: str
    subject_id: str
    amount: int
    material_id: str
    route_ids: tuple[str, ...]
    transport_capacity: int


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
    resource_stocks: tuple[ResourceStock, ...]
    economy_ledger: tuple[EconomyLedgerEntry, ...] = ()
    applied_events: tuple[str, ...] = ()
