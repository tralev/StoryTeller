"""Named officeholder successions projected from accepted history."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .genealogy import ConsequentialPerson, DynastyHouse
from .state import CivilizationState


@dataclass(frozen=True)
class OfficeholderSuccession:
    succession_id: str
    civilization_id: str
    house_id: str
    outgoing_person_id: str
    incoming_person_id: str
    claim_event_id: str
    claim_type: str
    event_id: str
    year: int


def project_successions(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    houses: tuple[DynastyHouse, ...],
    people: tuple[ConsequentialPerson, ...],
) -> tuple[OfficeholderSuccession, ...]:
    """Validate and retain named succession transitions and their claims."""
    event_by_id = {item.event_id: item for item in events}
    person_by_id = {item.person_id: item for item in people}
    house_ids = {item.house_id for item in houses}
    civilization_ids = {item.civilization_id for item in civilizations}
    successions: list[OfficeholderSuccession] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is not ConsequenceKind.OFFICEHOLDER_SET:
                continue
            details = dict(consequence.details)
            successions.append(OfficeholderSuccession(
                stable_id("officeholder_succession", seed,
                          identity("event_id", event.event_id),
                          identity("consequence_index", index)),
                consequence.subject, details.get("house_id", ""), consequence.value,
                consequence.target, details.get("claim_event_id", ""),
                details.get("claim_type", ""), event.event_id, event.year,
            ))
    allowed_claims = {"parent_of", "adopted_parent_of", "house_member", "spouse"}
    for succession in successions:
        source_event = event_by_id.get(succession.event_id)
        claim = event_by_id.get(succession.claim_event_id)
        outgoing = person_by_id.get(succession.outgoing_person_id)
        incoming = person_by_id.get(succession.incoming_person_id)
        claim_edges = () if claim is None else tuple(
            item for item in claim.consequences
            if item.kind is ConsequenceKind.GENEALOGY_RELATION_ADD
        )
        if (source_event is None or source_event.kind is not EventKind.SUCCESSION or claim is None
                or claim.kind is not EventKind.RELATIONSHIP
                or claim.event_id not in source_event.causes
                or (claim.year, claim.month, claim.sequence) >=
                   (source_event.year, source_event.month, source_event.sequence)
                or outgoing is None or incoming is None or outgoing == incoming
                or succession.civilization_id not in civilization_ids
                or succession.house_id not in house_ids
                or outgoing.civilization_id != succession.civilization_id
                or incoming.civilization_id != succession.civilization_id
                or outgoing.house_id != succession.house_id
                or incoming.house_id != succession.house_id
                or succession.claim_type not in allowed_claims
                or not any(edge.subject == outgoing.person_id
                           and edge.target == incoming.person_id
                           and edge.value == succession.claim_type for edge in claim_edges)
                or set(source_event.participants) !=
                   {outgoing.person_id, incoming.person_id}):
            raise ValueError("WG-SUCCESSION: invalid named succession or claim")
    if len({item.succession_id for item in successions}) != len(successions):
        raise ValueError("WG-SUCCESSION: duplicate identity")
    return tuple(successions)
