"""Typed, auditable physical-pressure scoring for deterministic site founding."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from ..numeric import div_round_half_up, identity, stable_id
from .state import SettlementState, SiteState


@dataclass(frozen=True)
class SiteSuitability:
    fresh_water_ppm: int
    food_capacity_ppm: int
    defense_ppm: int
    safety_ppm: int
    routes_ppm: int
    resources_ppm: int
    climate_ppm: int
    neighbours_ppm: int
    total_ppm: int

    @property
    def components(self) -> tuple[tuple[str, int], ...]:
        return tuple((field.name, int(getattr(self, field.name))) for field in fields(self)
                     if field.name != "total_ppm")


SITE_SCORE_WEIGHTS = (
    ("fresh_water_ppm", 200_000), ("food_capacity_ppm", 200_000),
    ("defense_ppm", 100_000), ("safety_ppm", 150_000),
    ("routes_ppm", 100_000), ("resources_ppm", 100_000),
    ("climate_ppm", 100_000), ("neighbours_ppm", 50_000),
)


@dataclass(frozen=True)
class CivilizationCapacityDiagnostic:
    code: str
    requested: int
    viable_regions: int
    total_regions: int


class CivilizationCapacityError(ValueError):
    def __init__(self, diagnostic: CivilizationCapacityDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            f"{diagnostic.code}: requested={diagnostic.requested}; "
            f"viable_regions={diagnostic.viable_regions}; total_regions={diagnostic.total_regions}"
        )


def validate_site_lifecycle(seed: int, genesis_sites: tuple[SiteState, ...],
                            current_sites: tuple[SiteState, ...],
                            settlements: tuple[SettlementState, ...]) -> None:
    """Prove sites survive lifecycle changes byte-for-byte under stable identities."""
    if current_sites != genesis_sites:
        raise ValueError("WG-SITE-IMMUTABLE: site records changed after genesis")
    site_ids = {site.site_id for site in current_sites}
    if len(site_ids) != len(current_sites):
        raise ValueError("WG-SITE-ID: duplicate site identity")
    for site in current_sites:
        expected = stable_id(
            "site", seed, identity("region_id", site.region_id), identity("cell", site.cell),
        )
        if site.site_id != expected:
            raise ValueError(f"WG-SITE-ID: noncanonical identity {site.site_id}")
    for settlement in settlements:
        if settlement.site_id not in site_ids:
            raise ValueError(f"WG-SITE-REFERENCE: {settlement.settlement_id}")


def score_site(physical: dict[str, Any], region: dict[str, Any], cell: int) -> SiteSuitability:
    hydrology, biomes = physical["hydrology"], physical["biomes"]
    resources, climate = physical["resources"], physical["climate"]
    water = bool(hydrology["coastline"]["values"][cell]
                 or hydrology["accumulation"]["values"][cell] > 4)
    resource = bool(resources["renewable_yield"]["values"][cell]
                    or any(cell in deposit["cells"] for deposit in resources["deposits"]))
    route_degree = sum(str(region["region_id"]) in (route["start_region"], route["end_region"])
                       for route in physical["routes"]["routes"])
    hazards = tuple(int(season["hazard_ppm"]["values"][cell])
                    for season in climate["seasons"])
    average_hazard = div_round_half_up(sum(hazards), len(hazards))
    temperature = int(climate["annual_temperature_millic"]["values"][cell])
    precipitation = int(climate["annual_precipitation_mm"]["values"][cell])
    temperature_penalty = min(1_000_000, abs(temperature - 15_000) * 25)
    precipitation_penalty = min(1_000_000, abs(precipitation - 800) * 500)
    values = {
        "fresh_water_ppm": 1_000_000 if water else 0,
        "food_capacity_ppm": min(1_000_000, int(biomes["carrying_capacity"]["values"][cell]) * 100),
        "defense_ppm": min(1_000_000, int(physical["terrain_typed"].slope_ppm.values[cell]) * 2),
        "safety_ppm": max(0, 1_000_000 - average_hazard),
        "routes_ppm": min(1_000_000, route_degree * 250_000),
        "resources_ppm": 1_000_000 if resource else 0,
        "climate_ppm": max(0, 1_000_000 - div_round_half_up(
            temperature_penalty + precipitation_penalty, 2)),
        "neighbours_ppm": min(1_000_000, len(region["neighbors"]) * 250_000),
    }
    total = sum(div_round_half_up(values[name] * weight, 1_000_000)
                for name, weight in SITE_SCORE_WEIGHTS)
    return SiteSuitability(**values, total_ppm=min(1_000_000, total))


def found_sites(seed: int, physical: dict[str, Any], count: int) -> tuple[SiteState, ...]:
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("WG-CIV-COUNT: civilization count must be a positive integer")
    scores: list[tuple[int, int, str, SiteSuitability]] = []
    for region in physical["regions"]["regions"]:
        candidates = []
        for raw_cell in region["cells"]:
            cell = int(raw_cell)
            breakdown = score_site(physical, region, cell)
            if (breakdown.food_capacity_ppm > 0
                    and (breakdown.fresh_water_ppm > 0 or breakdown.resources_ppm > 0)):
                candidates.append((breakdown.total_ppm, cell, breakdown))
        if not candidates:
            continue
        score, cell, breakdown = max(candidates, key=lambda item: (item[0], -item[1]))
        scores.append((score, cell, str(region["region_id"]), breakdown))
    if len(scores) < count:
        raise CivilizationCapacityError(CivilizationCapacityDiagnostic(
            "WG-CIV-CAPACITY", count, len(scores), len(physical["regions"]["regions"]),
        ))
    selected = sorted(scores, key=lambda item: (-item[0], item[1], item[2]))[:count]
    return tuple(SiteState(
        stable_id("site", seed, identity("region_id", region), identity("cell", cell)),
        region, cell, score,
        bool(physical["hydrology"]["coastline"]["values"][cell]
             or physical["hydrology"]["accumulation"]["values"][cell] > 4),
        bool(physical["resources"]["renewable_yield"]["values"][cell]
             or any(cell in deposit["cells"] for deposit in physical["resources"]["deposits"])),
        breakdown.components,
    ) for score, cell, region, breakdown in selected)
