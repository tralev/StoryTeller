"""Event-sourced doctrinal schisms and their derived child institutions."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .magic import Religion, ReligiousInstitution
from .state import CivilizationState


@dataclass(frozen=True)
class ReligiousSchism:
    schism_id: str
    parent_religion_id: str
    parent_institution_id: str
    child_institution_id: str
    registry_id: str
    rite: str
    holy_site_id: str
    disputed_claim: str
    civilization_id: str
    event_id: str
    year: int


def project_religious_schisms(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    religions: tuple[Religion, ...],
    institutions: tuple[ReligiousInstitution, ...],
) -> tuple[ReligiousSchism, ...]:
    """Derive child institutions only from accepted, causally linked events."""
    civilization_ids = {item.civilization_id for item in civilizations}
    religion_by_id = {item.religion_id: item for item in religions}
    institution_by_id = {item.institution_id: item for item in institutions}
    genesis_institution_ids = set(institution_by_id)
    projected: list[ReligiousSchism] = []
    for event in events:
        additions = [item for item in event.consequences
                     if item.kind is ConsequenceKind.RELIGIOUS_SCHISM_ADD]
        if not additions:
            continue
        if event.kind is not EventKind.SCHISM or len(additions) != 1:
            raise ValueError("WG-RELIGIOUS-SCHISM: invalid event shape")
        consequence = additions[0]
        details = dict(consequence.details)
        parent = institution_by_id.get(consequence.value)
        religion = religion_by_id.get(consequence.subject)
        civilization_id = event.participants[0] if event.participants else ""
        expected_child_id = stable_id(
            "religious_institution", seed,
            identity("parent_institution_id", consequence.value),
            identity("schism_year", event.year),
        )
        if (parent is None or religion is None
                or parent.religion_id != religion.religion_id
                or consequence.target != expected_child_id
                or consequence.target in genesis_institution_ids
                or civilization_id not in civilization_ids
                or tuple(event.participants) != (
                    civilization_id, parent.institution_id, consequence.target)
                or event.locations != (religion.holy_site_id,)
                or details.get("holy_site_id") != religion.holy_site_id
                or details.get("registry_id") != parent.registry_id
                or details.get("rite") != parent.rite
                or not details.get("disputed_claim")):
            raise ValueError("WG-RELIGIOUS-SCHISM: invalid parent or child institution")
        projected.append(ReligiousSchism(
            stable_id("historical_schism", seed, identity("event_id", event.event_id)),
            religion.religion_id, parent.institution_id, consequence.target,
            parent.registry_id, parent.rite, religion.holy_site_id,
            details["disputed_claim"], civilization_id, event.event_id, event.year,
        ))
    child_ids = [item.child_institution_id for item in projected]
    if len(child_ids) != len(set(child_ids)):
        raise ValueError("WG-RELIGIOUS-SCHISM: duplicate child institution")
    return tuple(projected)
