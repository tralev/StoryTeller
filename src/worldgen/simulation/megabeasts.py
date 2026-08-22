"""Rare persistent megabeasts and their bounded event-sourced histories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..numeric import div_floor_exact, identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import SimulationState

MEGABEAST_EVENT_KINDS = {
    EventKind.MEGABEAST_ORIGIN: "origin",
    EventKind.MEGABEAST_MOVEMENT: "movement",
    EventKind.MEGABEAST_ENCOUNTER: "encounter",
    EventKind.MEGABEAST_HUNT: "hunt",
    EventKind.MEGABEAST_DEATH: "death",
}


@dataclass(frozen=True)
class Megabeast:
    megabeast_id: str
    origin_species_id: str
    capabilities: tuple[str, ...]
    habitat_biome_ids: tuple[int, ...]
    lair_site_id: str
    origin_region_id: str
    territory_region_ids: tuple[str, ...]
    movement_limit_regions: int
    initial_condition: str
    carrying_cost: int


@dataclass(frozen=True)
class MegabeastHistoryEntry:
    entry_id: str
    megabeast_id: str
    transition: str
    prior_region_id: str
    new_region_id: str
    prior_condition: str
    new_condition: str
    prior_event_id: str
    event_id: str
    year: int


def generate_megabeasts(
    seed: int, physical: dict[str, Any], state: SimulationState,
) -> tuple[Megabeast, ...]:
    """Create a rare bounded set from living apex species and viable regions."""
    species = sorted(
        (item for item in physical["ecology"]["species"]
         if item["trophic_level"] == 3 and not item["extinct"]),
        key=lambda item: item["species_id"],
    )
    regions = {item["region_id"]: item for item in physical["regions"]["regions"]}
    sites = sorted(state.sites, key=lambda item: item.site_id)
    count = min(2, len(species), max(1, div_floor_exact(len(sites), 2)))
    result: list[Megabeast] = []
    biome_values = physical["biomes"]["biome_id"]["values"]
    for item in species:
        compatible = [
            site for site in sites
            if regions[site.region_id]["neighbors"]
            and any(biome_values[cell] in item["habitat_biomes"]
                    for cell in regions[site.region_id]["cells"])
        ]
        if not compatible:
            continue
        index = len(result)
        lair = compatible[index % len(compatible)]
        region = regions[lair.region_id]
        territory = tuple(sorted({lair.region_id, *region["neighbors"]}))
        result.append(Megabeast(
            stable_id("megabeast", seed, identity("species_id", item["species_id"]),
                      identity("ordinal", index)),
            item["species_id"], ("siege_strength", "territorial_memory"),
            tuple(item["habitat_biomes"]), lair.site_id, lair.region_id, territory,
            1, "healthy", 1,
        ))
        if len(result) == count:
            break
    if (len(result) > max(2, div_floor_exact(len(sites), 2))
            or sum(item.carrying_cost for item in result) > 2):
        raise ValueError("WG-MEGABEAST-RARITY: carrying budget exceeded")
    return tuple(result)


def project_megabeast_history(
    seed: int, events: tuple[HistoryEvent, ...], megabeasts: tuple[Megabeast, ...],
) -> tuple[MegabeastHistoryEntry, ...]:
    """Validate movement, encounters, hunts, death, and post-death retention."""
    by_id = {item.megabeast_id: item for item in megabeasts}
    current = {
        item.megabeast_id: (item.origin_region_id, item.initial_condition, "")
        for item in megabeasts
    }
    originated: set[str] = set()
    entries: list[MegabeastHistoryEntry] = []
    for event in events:
        if event.kind not in MEGABEAST_EVENT_KINDS:
            continue
        consequences = [item for item in event.consequences
                        if item.kind is ConsequenceKind.MEGABEAST_TRANSITION]
        if len(consequences) != 1:
            raise ValueError("WG-MEGABEAST-HISTORY: event lacks one transition")
        consequence = consequences[0]
        beast = by_id.get(consequence.subject)
        prior = current.get(consequence.subject)
        details = dict(consequence.details)
        transition = MEGABEAST_EVENT_KINDS[event.kind]
        new_region = consequence.target
        new_condition = consequence.value
        is_origin = transition == "origin"
        if (beast is None or prior is None or prior[1] == "dead"
                or details.get("transition") != transition
                or details.get("prior_region_id") != prior[0]
                or details.get("prior_condition") != prior[1]
                or details.get("prior_event_id", "") != prior[2]
                or (is_origin and (beast.megabeast_id in originated or prior[2]
                                   or new_region != beast.origin_region_id
                                   or details.get("lair_site_id") != beast.lair_site_id))
                or (not is_origin and not prior[2])
                or (prior[2] and prior[2] not in event.causes)
                or new_region not in beast.territory_region_ids
                or (transition == "movement" and new_region == prior[0])
                or (transition not in {"origin", "movement"} and new_region != prior[0])
                or (transition == "death" and new_condition != "dead")
                or (transition in {"encounter", "hunt"} and new_condition != "wounded")
                or (transition in {"origin", "movement"} and new_condition != prior[1])):
            raise ValueError("WG-MEGABEAST-HISTORY: invalid causal transition")
        originated.add(beast.megabeast_id)
        current[beast.megabeast_id] = (new_region, new_condition, event.event_id)
        entries.append(MegabeastHistoryEntry(
            stable_id("megabeast_history_entry", seed, identity("event_id", event.event_id)),
            beast.megabeast_id, transition, prior[0], new_region, prior[1], new_condition,
            prior[2], event.event_id, event.year,
        ))
    return tuple(entries)
