"""Event-sourced technology discoveries and capability unlocks."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, SettlementState


@dataclass(frozen=True)
class TechnologyDiscovery:
    discovery_id: str
    civilization_id: str
    technology_id: str
    prerequisites: tuple[str, ...]
    settlement_id: str
    workshop_id: str
    material_cost: int
    event_id: str
    year: int


def project_technology_discoveries(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    settlements: tuple[SettlementState, ...],
    registry_entries: tuple[Mapping[str, object], ...],
) -> tuple[TechnologyDiscovery, ...]:
    """Validate prerequisite order and retain discovery provenance."""
    technology_by_id = {str(item["id"]): item for item in registry_entries}
    civilization_by_id = {item.civilization_id: item for item in civilizations}
    settlement_by_id = {item.settlement_id: item for item in settlements}
    discoveries: list[TechnologyDiscovery] = []
    for event in events:
        unlocks = [item for item in event.consequences
                   if item.kind is ConsequenceKind.CAPABILITY_ADD]
        if event.kind is not EventKind.TECHNOLOGY:
            if unlocks:
                raise ValueError("WG-TECHNOLOGY-EVENT: capability outside discovery")
            continue
        costs = [item for item in event.consequences
                 if item.kind is ConsequenceKind.MATERIAL_DELTA]
        if len(unlocks) != 1 or len(costs) != 1:
            raise ValueError("WG-TECHNOLOGY-SHAPE: discovery must unlock once and pay once")
        unlock, cost = unlocks[0], costs[0]
        details = dict(unlock.details)
        prerequisites = tuple(filter(None, details.get("prerequisites", "").split(",")))
        discoveries.append(TechnologyDiscovery(
            stable_id("technology_discovery", seed, identity("event_id", event.event_id)),
            unlock.subject, unlock.target, prerequisites,
            details.get("settlement_id", ""), unlock.value, -cost.amount,
            event.event_id, event.year,
        ))
    discovered_by_civ: dict[str, set[str]] = {}
    final_discoveries = {(item.civilization_id, item.technology_id) for item in discoveries}
    for civilization in civilizations:
        discovered_by_civ[civilization.civilization_id] = {
            capability for capability in civilization.capabilities
            if (civilization.civilization_id, capability) not in final_discoveries
        }
    event_by_id = {item.event_id: item for item in events}
    for discovery in sorted(discoveries, key=lambda item: (
            event_by_id[item.event_id].year, event_by_id[item.event_id].month,
            event_by_id[item.event_id].sequence, item.discovery_id)):
        technology = technology_by_id.get(discovery.technology_id)
        source_civilization = civilization_by_id.get(discovery.civilization_id)
        settlement = settlement_by_id.get(discovery.settlement_id)
        workshop_ids = set() if settlement is None else {
            item.workshop_id for item in settlement.workshops
        }
        raw_required = () if technology is None else technology.get("requires")
        if not isinstance(raw_required, tuple):
            raise ValueError("WG-TECHNOLOGY: malformed technology prerequisites")
        required = tuple(str(item) for item in raw_required)
        known = discovered_by_civ.get(discovery.civilization_id, set())
        event = event_by_id[discovery.event_id]
        if (technology is None or source_civilization is None or settlement is None
                or settlement.civilization_id != discovery.civilization_id
                or discovery.workshop_id not in workshop_ids
                or discovery.prerequisites != required or not set(required) <= known
                or discovery.technology_id in known or discovery.material_cost <= 0
                or discovery.civilization_id not in event.participants
                or settlement.site_id not in event.locations):
            raise ValueError("WG-TECHNOLOGY: invalid discovery or prerequisites")
        known.add(discovery.technology_id)
    if len(final_discoveries) != len(discoveries):
        raise ValueError("WG-TECHNOLOGY: duplicate capability unlock")
    return tuple(discoveries)
