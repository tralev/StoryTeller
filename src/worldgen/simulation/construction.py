"""Need-driven construction records projected from accepted events."""

from __future__ import annotations

from dataclasses import dataclass

from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, SettlementState


@dataclass(frozen=True)
class ConstructionProject:
    project_id: str
    civilization_id: str
    settlement_id: str
    addressed_need: str
    building: str
    workshop_id: str
    material_cost: int
    event_id: str
    year: int


def project_construction(
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    settlements: tuple[SettlementState, ...],
) -> tuple[ConstructionProject, ...]:
    """Retain construction provenance and verify mirrored material accounting."""
    civilization_by_id = {item.civilization_id: item for item in civilizations}
    settlement_by_id = {item.settlement_id: item for item in settlements}
    projects: list[ConstructionProject] = []
    for event in events:
        if event.kind is not EventKind.CONSTRUCTION:
            continue
        buildings = [
            item
            for item in event.consequences
            if item.kind is ConsequenceKind.SETTLEMENT_BUILDING_ADD
        ]
        workshops = [
            item
            for item in event.consequences
            if item.kind is ConsequenceKind.SETTLEMENT_WORKSHOP_ADD
        ]
        civilization_costs = [
            item for item in event.consequences if item.kind is ConsequenceKind.MATERIAL_DELTA
        ]
        inventory_costs = [
            item
            for item in event.consequences
            if item.kind is ConsequenceKind.SETTLEMENT_INVENTORY_DELTA
            and item.target == "materials"
        ]
        if not (
            len(buildings) == len(workshops) == len(civilization_costs) == len(inventory_costs) == 1
        ):
            raise ValueError("WG-CONSTRUCTION-SHAPE: construction must have exact effects")
        building, workshop = buildings[0], workshops[0]
        civilization_cost, inventory_cost = civilization_costs[0], inventory_costs[0]
        details = dict(building.details)
        workshop_parts = workshop.value.split("|")
        civilization = civilization_by_id.get(civilization_cost.subject)
        settlement = settlement_by_id.get(building.subject)
        cost = -civilization_cost.amount
        if (
            civilization is None
            or settlement is None
            or settlement.civilization_id != civilization.civilization_id
            or inventory_cost.subject != settlement.settlement_id
            or workshop.subject != settlement.settlement_id
            or civilization_cost.amount != inventory_cost.amount
            or cost <= 0
            or details.get("material_cost") != str(cost)
            or details.get("addressed_need") not in civilization.needs
            or not details.get("project_id")
            or len(workshop_parts) != 6
            or details.get("workshop_id") != workshop_parts[0]
            or civilization.civilization_id not in event.participants
            or civilization.capital_site_id not in event.locations
        ):
            raise ValueError("WG-CONSTRUCTION-PROVENANCE: invalid project or accounting")
        projects.append(
            ConstructionProject(
                details["project_id"],
                civilization.civilization_id,
                settlement.settlement_id,
                details["addressed_need"],
                building.value,
                workshop_parts[0],
                cost,
                event.event_id,
                event.year,
            )
        )
    if len({item.project_id for item in projects}) != len(projects):
        raise ValueError("WG-CONSTRUCTION-PROVENANCE: duplicate project identity")
    return tuple(projects)
