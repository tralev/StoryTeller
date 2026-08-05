"""Physical-constraint-aware deterministic site founding."""
from __future__ import annotations

from typing import Any

from ..numeric import stable_id
from .state import SiteState


def found_sites(seed: int, physical: dict[str, Any], count: int) -> tuple[SiteState, ...]:
    regions = physical["regions"]["regions"]
    hydrology = physical["hydrology"]
    biomes = physical["biomes"]
    resources = physical["resources"]
    route_cells = {cell for route in physical["routes"]["routes"] for cell in route["cells"]}
    scores: list[tuple[int, int, str]] = []
    for region in regions:
        cell = int(region["center"])
        water = bool(hydrology["coastline"]["values"][cell] or hydrology["accumulation"]["values"][cell] > 4)
        resource = bool(resources["renewable_yield"]["values"][cell] or
                        any(cell in deposit["cells"] for deposit in resources["deposits"]))
        capacity = int(biomes["carrying_capacity"]["values"][cell])
        suitability = min(1_000_000, capacity * 100 + (200_000 if water else 0)
                          + (150_000 if resource else 0) + (100_000 if cell in route_cells else 0))
        scores.append((suitability, cell, str(region["region_id"])))
    selected = sorted(scores, key=lambda item: (-item[0], item[1], item[2]))[:min(count, len(scores))]
    return tuple(SiteState(stable_id("site", seed, index), region, cell, score,
                           bool(physical["hydrology"]["coastline"]["values"][cell]
                                or physical["hydrology"]["accumulation"]["values"][cell] > 4),
                           bool(physical["resources"]["renewable_yield"]["values"][cell]))
                 for index, (score, cell, region) in enumerate(selected))
