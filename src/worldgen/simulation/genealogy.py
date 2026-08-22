"""Selective event-sourced genealogy for consequential social anchors."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, Cohort, SettlementState


@dataclass(frozen=True)
class ConsequentialPerson:
    person_id: str
    civilization_id: str
    cohort_id: str
    settlement_id: str
    house_id: str
    ordinal: int
    created_year: int = 0
    population_weight: int = 0


@dataclass(frozen=True)
class DynastyHouse:
    house_id: str
    civilization_id: str
    founding_site_id: str


@dataclass(frozen=True)
class GenealogyRelation:
    relation_id: str
    source_person_id: str
    target_person_id: str
    relation_type: str
    event_id: str
    year: int


@dataclass(frozen=True)
class InheritanceTransition:
    inheritance_id: str
    house_id: str
    outgoing_person_id: str
    incoming_person_id: str
    claim_event_id: str
    event_id: str
    year: int


@dataclass(frozen=True)
class PersonStatusTransition:
    transition_id: str
    person_id: str
    prior_status: str
    new_status: str
    event_id: str
    year: int


def genesis_genealogy(seed: int, civilizations: tuple[CivilizationState, ...],
                      cohorts: tuple[Cohort, ...], settlements: tuple[SettlementState, ...],
                      anchors_per_civilization: int = 4,
                      ) -> tuple[tuple[DynastyHouse, ...], tuple[ConsequentialPerson, ...]]:
    settlement_by_civ = {item.civilization_id: item for item in settlements}
    adult_by_civ = {item.civilization_id: item for item in cohorts if item.age_band == "adult"}
    houses: list[DynastyHouse] = []
    people: list[ConsequentialPerson] = []
    for civilization in sorted(civilizations, key=lambda item: item.civilization_id):
        settlement = settlement_by_civ[civilization.civilization_id]
        cohort = adult_by_civ[civilization.civilization_id]
        house_id = stable_id("dynasty_house", seed,
                             identity("civilization_id", civilization.civilization_id))
        houses.append(DynastyHouse(house_id, civilization.civilization_id,
                                   civilization.capital_site_id))
        people.extend(ConsequentialPerson(
            stable_id("historical_person", seed, identity("house_id", house_id),
                      identity("person_ordinal", ordinal)),
            civilization.civilization_id, cohort.cohort_id, settlement.settlement_id,
            house_id, ordinal,
        ) for ordinal in range(anchors_per_civilization))
    return tuple(houses), tuple(people)


def project_genealogy(seed: int, events: tuple[HistoryEvent, ...], houses: tuple[DynastyHouse, ...],
                      people: tuple[ConsequentialPerson, ...]) -> tuple[GenealogyRelation, ...]:
    person_ids = {person.person_id for person in people}
    allowed = {
        "spouse", "parent_of", "adopted_parent_of", "disputed_parent_of", "house_member",
    }
    relations = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is not ConsequenceKind.GENEALOGY_RELATION_ADD:
                continue
            relations.append(GenealogyRelation(
                stable_id("genealogy_relation", seed, identity("event_id", event.event_id),
                          identity("consequence_index", index)),
                consequence.subject, consequence.target, consequence.value, event.event_id,
                event.year,
            ))
    relation_ids = {item.relation_id for item in relations}
    if len(relation_ids) != len(relations) or any(
            relation.source_person_id not in person_ids
            or relation.target_person_id not in person_ids
            or relation.source_person_id == relation.target_person_id
            or relation.relation_type not in allowed
            or next(event for event in events if event.event_id == relation.event_id).kind
            is not EventKind.RELATIONSHIP
            for relation in relations):
        raise ValueError("WG-GENEALOGY-RELATION: invalid event-sourced relation")
    if any(person.population_weight != 0 for person in people):
        raise ValueError("WG-GENEALOGY-POPULATION: anchors must not duplicate cohorts")
    if any(person.house_id not in {house.house_id for house in houses} for person in people):
        raise ValueError("WG-GENEALOGY-HOUSE: person has unknown house")
    parents = {
        (item.source_person_id, item.target_person_id) for item in relations
        if item.relation_type in {"parent_of", "adopted_parent_of"}
    }
    children: dict[str, set[str]] = {}
    for parent, child in parents:
        children.setdefault(parent, set()).add(child)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(person_id: str) -> None:
        if person_id in visiting:
            raise ValueError("WG-GENEALOGY-CYCLE: cyclic parentage")
        if person_id in visited:
            return
        visiting.add(person_id)
        for child_id in sorted(children.get(person_id, ())):
            visit(child_id)
        visiting.remove(person_id)
        visited.add(person_id)

    for parent_id in sorted(children):
        visit(parent_id)
    if any(person.created_year < 0 for person in people) or any(
            event.year < person.created_year
            for event in events for person in people if person.person_id in event.participants
    ):
        raise ValueError("WG-GENEALOGY-TIME: person referenced before creation")
    return tuple(relations)


def project_inheritances(
    seed: int,
    events: tuple[HistoryEvent, ...],
    houses: tuple[DynastyHouse, ...],
    people: tuple[ConsequentialPerson, ...],
) -> tuple[InheritanceTransition, ...]:
    """Project explicit house inheritance from accepted succession events."""
    event_by_id = {event.event_id: event for event in events}
    person_by_id = {person.person_id: person for person in people}
    house_ids = {house.house_id for house in houses}
    transitions: list[InheritanceTransition] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is not ConsequenceKind.INHERITANCE_TRANSFER:
                continue
            details = dict(consequence.details)
            transitions.append(InheritanceTransition(
                stable_id("inheritance_transition", seed, identity("event_id", event.event_id),
                          identity("consequence_index", index)),
                consequence.value, consequence.subject, consequence.target,
                details.get("claim_event_id", ""), event.event_id, event.year,
            ))
    for transition in transitions:
        source_event = event_by_id.get(transition.event_id)
        claim = event_by_id.get(transition.claim_event_id)
        outgoing = person_by_id.get(transition.outgoing_person_id)
        incoming = person_by_id.get(transition.incoming_person_id)
        claim_edges = () if claim is None else tuple(
            consequence for consequence in claim.consequences
            if consequence.kind is ConsequenceKind.GENEALOGY_RELATION_ADD
        )
        if (source_event is None or source_event.kind is not EventKind.SUCCESSION
                or claim is None or claim.kind is not EventKind.RELATIONSHIP
                or claim.event_id not in source_event.causes
                or not any(edge.subject == transition.outgoing_person_id
                           and edge.target == transition.incoming_person_id
                           for edge in claim_edges)
                or transition.house_id not in house_ids
                or outgoing is None or incoming is None or outgoing == incoming
                or outgoing.house_id != transition.house_id
                or incoming.house_id != transition.house_id
                or source_event.year < outgoing.created_year
                or source_event.year < incoming.created_year
                or set(source_event.participants) != {outgoing.person_id, incoming.person_id}):
            raise ValueError("WG-INHERITANCE: invalid event-sourced inheritance")
    if len({item.inheritance_id for item in transitions}) != len(transitions):
        raise ValueError("WG-INHERITANCE: duplicate identity")
    return tuple(transitions)


def project_person_statuses(
    seed: int, events: tuple[HistoryEvent, ...], people: tuple[ConsequentialPerson, ...],
) -> tuple[PersonStatusTransition, ...]:
    """Project consequential-person living/dead status exactly once from events."""
    status = {person.person_id: "living" for person in people}
    transitions: list[PersonStatusTransition] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            if consequence.kind is not ConsequenceKind.PERSON_STATUS_SET:
                continue
            prior = status.get(consequence.subject)
            details = dict(consequence.details)
            if (event.kind is not EventKind.PERSON_STATUS or prior is None
                    or details.get("prior_status") != prior
                    or consequence.value != "dead" or event.year < 0):
                raise ValueError("WG-GENEALOGY-STATUS: invalid person status transition")
            status[consequence.subject] = consequence.value
            transitions.append(PersonStatusTransition(
                stable_id("person_status_transition", seed,
                          identity("event_id", event.event_id),
                          identity("consequence_index", index)),
                consequence.subject, prior, consequence.value, event.event_id, event.year,
            ))
    return tuple(transitions)
