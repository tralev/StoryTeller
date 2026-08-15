"""Selective event-sourced genealogy for consequential social anchors."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import Cohort, CivilizationState, SettlementState


@dataclass(frozen=True)
class ConsequentialPerson:
    person_id: str
    civilization_id: str
    cohort_id: str
    settlement_id: str
    house_id: str
    ordinal: int
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
    allowed = {"spouse", "parent_of", "adopted_parent_of", "house_member"}
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
    parents = {(item.source_person_id, item.target_person_id) for item in relations
               if item.relation_type in {"parent_of", "adopted_parent_of"}}
    if any((child, parent) in parents for parent, child in parents):
        raise ValueError("WG-GENEALOGY-CYCLE: reciprocal parentage")
    return tuple(relations)
