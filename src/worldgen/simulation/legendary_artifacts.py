"""Legendary artifacts derived exclusively from successful history events."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .relationships import SocialAnchor
from .state import CivilizationState, SettlementState


@dataclass(frozen=True)
class ArtifactProvenance:
    creation_event_id: str
    creation_year: int
    creation_month: int
    creation_sequence: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LegendaryArtifact:
    artifact_id: str
    name: str
    creator_id: str
    culture_id: str
    material_id: str
    workshop_id: str
    site_id: str
    objective_properties: tuple[tuple[str, str], ...]
    attributed_meaning: str
    meaning_attributed_to: str
    provenance: ArtifactProvenance


def _commission_details(event: HistoryEvent) -> tuple[str, str, str] | None:
    candidates = [consequence for consequence in event.consequences
                  if consequence.kind is ConsequenceKind.SETTLEMENT_INVENTORY_DELTA
                  and consequence.amount < 0]
    if len(candidates) != 1:
        return None
    details = dict(candidates[0].details)
    if details.get("artifact_class") != "legendary":
        return None
    return candidates[0].subject, details.get("material_id", ""), details.get("workshop_id", "")


def validate_legendary_artifacts(artifacts: tuple[LegendaryArtifact, ...],
                                 events: tuple[HistoryEvent, ...],
                                 people: tuple[SocialAnchor, ...],
                                 civilizations: tuple[CivilizationState, ...],
                                 settlements: tuple[SettlementState, ...]) -> None:
    event_by_id = {event.event_id: event for event in events}
    people_by_id = {person.person_id: person for person in people}
    civilization_ids = {civilization.civilization_id for civilization in civilizations}
    settlement_by_id = {settlement.settlement_id: settlement for settlement in settlements}
    ids = {artifact.artifact_id for artifact in artifacts}
    if len(ids) != len(artifacts):
        raise ValueError("WG-LEGENDARY-ID: duplicate legendary artifact")
    creation_events: set[str] = set()
    for artifact in artifacts:
        provenance = artifact.provenance
        event = event_by_id.get(provenance.creation_event_id)
        details = _commission_details(event) if event is not None else None
        if (event is None or event.kind is not EventKind.COMMISSION or details is None
                or provenance.creation_event_id in creation_events
                or (provenance.creation_year, provenance.creation_month,
                    provenance.creation_sequence) != (event.year, event.month, event.sequence)):
            raise ValueError("WG-LEGENDARY-PROVENANCE: artifact lacks one successful commission event")
        settlement_id, material_id, workshop_id = details
        settlement = settlement_by_id.get(settlement_id)
        creator = people_by_id.get(artifact.creator_id)
        if (settlement is None or creator is None or artifact.culture_id not in civilization_ids
                or creator.civilization_id != artifact.culture_id
                or settlement.civilization_id != artifact.culture_id
                or settlement.site_id != artifact.site_id
                or artifact.material_id != material_id or artifact.workshop_id != workshop_id
                or workshop_id not in {workshop.workshop_id for workshop in settlement.workshops}
                or event.participants != (artifact.culture_id,)
                or event.locations != (artifact.site_id,)):
            raise ValueError("WG-LEGENDARY-REFERENCE: forged creator/culture/material/workshop/site link")
        expected_sources = tuple(sorted((event.event_id, artifact.creator_id, artifact.culture_id,
                                         artifact.material_id, artifact.workshop_id, artifact.site_id)))
        if provenance.source_ids != expected_sources:
            raise ValueError("WG-LEGENDARY-SOURCES: incomplete immutable creation sources")
        if (not artifact.objective_properties
                or artifact.objective_properties != tuple(sorted(artifact.objective_properties))
                or not artifact.attributed_meaning or not artifact.meaning_attributed_to):
            raise ValueError("WG-LEGENDARY-MEANING: properties or attributed meaning missing")
        creation_events.add(event.event_id)


def generate_legendary_artifacts(seed: int, events: tuple[HistoryEvent, ...],
                                 people: tuple[SocialAnchor, ...],
                                 civilizations: tuple[CivilizationState, ...],
                                 settlements: tuple[SettlementState, ...]) -> tuple[LegendaryArtifact, ...]:
    people_by_culture: dict[str, list[SocialAnchor]] = {}
    for person in sorted(people, key=lambda item: item.person_id):
        people_by_culture.setdefault(person.civilization_id, []).append(person)
    settlement_by_id = {settlement.settlement_id: settlement for settlement in settlements}
    artifacts = []
    for event in events:
        details = _commission_details(event)
        if event.kind is not EventKind.COMMISSION or details is None or len(event.participants) != 1:
            continue
        settlement_id, material_id, workshop_id = details
        culture_id = event.participants[0]
        settlement = settlement_by_id.get(settlement_id)
        candidates = people_by_culture.get(culture_id, [])
        if settlement is None or not candidates:
            raise ValueError("WG-LEGENDARY-REFERENCE: commission lacks settlement or creator")
        creator = candidates[0]
        artifact_id = stable_id("legendary_artifact", seed,
                                identity("creation_event_id", event.event_id))
        sources = tuple(sorted((event.event_id, creator.person_id, culture_id, material_id,
                                workshop_id, settlement.site_id)))
        artifacts.append(LegendaryArtifact(
            artifact_id, f"The Remembered Work of {event.year}", creator.person_id, culture_id,
            material_id, workshop_id, settlement.site_id,
            (("condition", "intact"), ("mass_kg", "5"), ("object_kind", "engraved waystone")),
            "said to preserve the covenant of its makers", culture_id,
            ArtifactProvenance(event.event_id, event.year, event.month, event.sequence, sources),
        ))
    result = tuple(artifacts)
    validate_legendary_artifacts(result, events, people, civilizations, settlements)
    return result
