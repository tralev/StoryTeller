"""Typed projection and validation for diplomacy, war, and peace transitions."""

from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, DiplomaticRelation

_TRANSITIONS = {
    "neutral": ("rivalry", EventKind.DIPLOMACY),
    "rivalry": ("alliance", EventKind.DIPLOMACY),
    "alliance": ("war", EventKind.WAR),
    "war": ("peace", EventKind.PEACE),
    "peace": ("alliance", EventKind.DIPLOMACY),
}
_INFLUENCE = {"war": 100_000, "alliance": 700_000}


@dataclass(frozen=True)
class DiplomaticTransition:
    transition_id: str
    left_civilization_id: str
    right_civilization_id: str
    prior_status: str
    new_status: str
    influence_ppm: int
    left_material_cost: int
    right_material_cost: int
    event_id: str
    year: int


def project_diplomatic_transitions(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    genesis_relations: tuple[DiplomaticRelation, ...],
    final_relations: tuple[DiplomaticRelation, ...],
) -> tuple[DiplomaticTransition, ...]:
    """Replay and verify every relation transition against its causal envelope."""
    civilization_by_id = {item.civilization_id: item for item in civilizations}
    current = {(item.left, item.right): item for item in genesis_relations}
    projected: list[DiplomaticTransition] = []
    for event in events:
        relation_changes = [
            item for item in event.consequences if item.kind is ConsequenceKind.RELATION_SET
        ]
        if not relation_changes:
            continue
        if len(relation_changes) != 1:
            raise ValueError("WG-DIPLOMACY: event must contain one relation transition")
        change = relation_changes[0]
        left_id, right_id = sorted((change.subject, change.target))
        pair = (left_id, right_id)
        prior = current.get(pair)
        expected = _TRANSITIONS.get(prior.status if prior else "")
        details = dict(change.details)
        left = civilization_by_id.get(pair[0])
        right = civilization_by_id.get(pair[1])
        costs = {
            item.subject: -item.amount
            for item in event.consequences
            if item.kind is ConsequenceKind.MATERIAL_DELTA
        }
        expected_influence = _INFLUENCE.get(change.value, 500_000)
        conflict_keys = tuple(details.get("conflict_keys", "").split(","))
        expected_relation_key = f"annual-relation:{pair[0]}:{pair[1]}:{event.year:04d}"
        proposal_details_valid = (
            set(details)
            == {
                "prior_status",
                "new_status",
                "proposal_id",
                "conflict_keys",
                "snapshot",
            }
            and details["proposal_id"].startswith("history_proposal_")
            and conflict_keys == tuple(sorted(set(conflict_keys)))
            and expected_relation_key in conflict_keys
            and details["snapshot"] == f"{event.year:04d}:12"
            and all(dict(item.details) == details for item in event.consequences)
        )
        if (
            prior is None
            or expected != (change.value, event.kind)
            or event.kind not in {EventKind.DIPLOMACY, EventKind.WAR, EventKind.PEACE}
            or left is None
            or right is None
            or event.participants != pair
            or event.locations != (left.capital_site_id, right.capital_site_id)
            or details.get("prior_status") != prior.status
            or details.get("new_status") != change.value
            or not proposal_details_valid
            or change.amount != expected_influence
            or any(item not in pair for item in costs)
            or (event.kind is not EventKind.WAR and costs)
            or (event.kind is EventKind.WAR and set(costs) != set(pair))
            or any(not 0 <= amount <= 100 for amount in costs.values())
        ):
            raise ValueError("WG-DIPLOMACY: invalid typed transition")
        current[pair] = DiplomaticRelation(pair[0], pair[1], change.value, change.amount)
        projected.append(
            DiplomaticTransition(
                stable_id("diplomatic_transition", seed, identity("event_id", event.event_id)),
                pair[0],
                pair[1],
                prior.status,
                change.value,
                change.amount,
                costs.get(pair[0], 0),
                costs.get(pair[1], 0),
                event.event_id,
                event.year,
            )
        )
    if tuple(current[key] for key in sorted(current)) != tuple(
        sorted(final_relations, key=lambda item: (item.left, item.right))
    ):
        raise ValueError("WG-DIPLOMACY: projected relations disagree with final state")
    return tuple(projected)
