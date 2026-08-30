"""Event-sourced polity patronage of immutable religious identities."""

from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .magic import Religion, ReligiousInstitution
from .state import CivilizationState


@dataclass(frozen=True)
class ReligiousPatronage:
    patronage_id: str
    civilization_id: str
    religion_id: str
    institution_id: str
    holy_site_id: str
    event_id: str
    year: int


def project_religious_patronage(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    religions: tuple[Religion, ...],
    institutions: tuple[ReligiousInstitution, ...],
) -> tuple[ReligiousPatronage, ...]:
    """Project patronage facts exclusively from accepted history events."""
    civilization_ids = {item.civilization_id for item in civilizations}
    religion_by_id = {item.religion_id: item for item in religions}
    institution_by_id = {item.institution_id: item for item in institutions}
    patronages: list[ReligiousPatronage] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is not ConsequenceKind.RELIGIOUS_PATRONAGE_ADD:
                continue
            details = dict(consequence.details)
            patronages.append(
                ReligiousPatronage(
                    stable_id(
                        "religious_patronage",
                        seed,
                        identity("event_id", event.event_id),
                        identity("consequence_index", index),
                    ),
                    consequence.subject,
                    consequence.target,
                    consequence.value,
                    details.get("holy_site_id", ""),
                    event.event_id,
                    event.year,
                )
            )
    event_by_id = {item.event_id: item for item in events}
    for patronage in patronages:
        religion = religion_by_id.get(patronage.religion_id)
        institution = institution_by_id.get(patronage.institution_id)
        source_event = event_by_id.get(patronage.event_id)
        if (
            patronage.civilization_id not in civilization_ids
            or religion is None
            or institution is None
            or source_event is None
            or source_event.kind is not EventKind.RELIGION
            or institution.religion_id != religion.religion_id
            or institution.site_id != religion.holy_site_id
            or patronage.holy_site_id != religion.holy_site_id
            or patronage.civilization_id not in source_event.participants
            or patronage.holy_site_id not in source_event.locations
        ):
            raise ValueError("WG-RELIGIOUS-PATRONAGE: invalid event-sourced patronage")
    if len({item.patronage_id for item in patronages}) != len(patronages):
        raise ValueError("WG-RELIGIOUS-PATRONAGE: duplicate identity")
    return tuple(patronages)
