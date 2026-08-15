"""Aggregate households and bounded social anchors for simulated populations."""
from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .registries import simulation_registry_entries
from .state import Cohort, SettlementState

MAX_HOUSEHOLD_SIZE = 5
MAX_SOCIAL_ANCHORS_PER_COHORT = 64


@dataclass(frozen=True)
class Household:
    household_id: str
    cohort_id: str
    settlement_id: str
    civilization_id: str
    member_count: int


@dataclass(frozen=True)
class SocialAnchor:
    person_id: str
    household_id: str
    cohort_id: str
    settlement_id: str
    civilization_id: str


@dataclass(frozen=True)
class PersonalRelationship:
    relationship_id: str
    source_person_id: str
    target_person_id: str
    relationship_type: str
    established_year: int


def _relationship_types() -> tuple[str, ...]:
    entry = next(item for item in simulation_registry_entries("people")
                 if item["id"] == "relationship_types_v1")
    value = entry["types"]
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise ValueError("WG-RELATIONSHIP-REGISTRY: types must be strings")
    return value


def validate_relationships(households: tuple[Household, ...],
                           people: tuple[SocialAnchor, ...],
                           relationships: tuple[PersonalRelationship, ...],
                           cohorts: tuple[Cohort, ...],
                           settlements: tuple[SettlementState, ...]) -> None:
    cohort_by_id = {cohort.cohort_id: cohort for cohort in cohorts}
    settlement_by_id = {settlement.settlement_id: settlement for settlement in settlements}
    household_ids = {household.household_id for household in households}
    if len(household_ids) != len(households):
        raise ValueError("WG-HOUSEHOLD-ID: duplicate household identity")
    totals = {cohort_id: 0 for cohort_id in cohort_by_id}
    for household in households:
        cohort = cohort_by_id.get(household.cohort_id)
        settlement = settlement_by_id.get(household.settlement_id)
        if (cohort is None or settlement is None or household.member_count <= 0
                or household.member_count > MAX_HOUSEHOLD_SIZE
                or household.civilization_id != cohort.civilization_id
                or household.civilization_id != settlement.civilization_id
                or cohort.site_id != settlement.site_id):
            raise ValueError("WG-HOUSEHOLD-REFERENCE: household contradicts cohort/settlement")
        totals[household.cohort_id] += household.member_count
    if any(totals[cohort.cohort_id] != cohort.population for cohort in cohorts):
        raise ValueError("WG-HOUSEHOLD-CONSERVATION: household members must equal cohort population")
    people_by_id = {person.person_id: person for person in people}
    if len(people_by_id) != len(people) or any(
            person.household_id not in household_ids
            or person.cohort_id not in cohort_by_id
            or person.settlement_id not in settlement_by_id
            for person in people):
        raise ValueError("WG-RELATIONSHIP-PERSON: invalid social anchor")
    households_by_id = {household.household_id: household for household in households}
    if any((person.cohort_id, person.settlement_id, person.civilization_id) != (
            households_by_id[person.household_id].cohort_id,
            households_by_id[person.household_id].settlement_id,
            households_by_id[person.household_id].civilization_id,
    ) for person in people):
        raise ValueError("WG-RELATIONSHIP-PERSON: anchor contradicts household")
    allowed = set(_relationship_types())
    relationship_ids = {relation.relationship_id for relation in relationships}
    if len(relationship_ids) != len(relationships) or any(
            relation.source_person_id not in people_by_id
            or relation.target_person_id not in people_by_id
            or relation.source_person_id == relation.target_person_id
            or relation.relationship_type not in allowed
            or relation.established_year < 0
            for relation in relationships):
        raise ValueError("WG-RELATIONSHIP-EDGE: invalid typed relationship")
    # Directed lineage must be acyclic.
    parents = {(relation.source_person_id, relation.target_person_id)
               for relation in relationships if relation.relationship_type == "parent_of"}
    children: dict[str, set[str]] = {}
    for parent, child in parents:
        children.setdefault(parent, set()).add(child)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(person_id: str) -> None:
        if person_id in visiting:
            raise ValueError("WG-RELATIONSHIP-LINEAGE: cyclic parentage")
        if person_id in visited:
            return
        visiting.add(person_id)
        for child_id in children.get(person_id, set()):
            visit(child_id)
        visiting.remove(person_id)
        visited.add(person_id)

    for parent_id in children:
        visit(parent_id)


def generate_relationships(seed: int, cohorts: tuple[Cohort, ...],
                           settlements: tuple[SettlementState, ...],
                           present_year: int) -> tuple[tuple[Household, ...],
                                                       tuple[SocialAnchor, ...],
                                                       tuple[PersonalRelationship, ...]]:
    settlement_by_key = {(item.civilization_id, item.site_id): item for item in settlements}
    households: list[Household] = []
    people: list[SocialAnchor] = []
    relationships: list[PersonalRelationship] = []
    for cohort in sorted(cohorts, key=lambda item: item.cohort_id):
        settlement = settlement_by_key.get((cohort.civilization_id, cohort.site_id))
        if settlement is None:
            raise ValueError("WG-HOUSEHOLD-REFERENCE: cohort has no settlement")
        complete_households, partial_members = divmod(cohort.population, MAX_HOUSEHOLD_SIZE)
        household_count = complete_households + int(partial_members > 0)
        base, remainder = divmod(cohort.population, household_count) if household_count else (0, 0)
        cohort_households = []
        for index in range(household_count):
            household_id = stable_id(
                "household", seed, identity("cohort_id", cohort.cohort_id),
                identity("household_index", index),
            )
            household = Household(household_id, cohort.cohort_id, settlement.settlement_id,
                                  cohort.civilization_id, base + (index < remainder))
            households.append(household); cohort_households.append(household)
        anchors = []
        for index, household in enumerate(cohort_households[:MAX_SOCIAL_ANCHORS_PER_COHORT]):
            person = SocialAnchor(
                stable_id("person", seed, identity("household_id", household.household_id),
                          identity("anchor_index", 0)),
                household.household_id, cohort.cohort_id, settlement.settlement_id,
                cohort.civilization_id,
            )
            people.append(person); anchors.append(person)
        edge_specs: list[tuple[SocialAnchor, SocialAnchor, str]] = []
        edge_specs.extend((anchors[index], anchors[index + 1], "spouse")
                          for index in range(0, len(anchors) - 1, 2))
        edge_specs.extend((anchors[index], anchors[index + 2], "parent_of")
                          for index in range(0, len(anchors) - 2, 3))
        edge_specs.extend((anchors[index], anchors[index + 1], "mentor")
                          for index in range(1, len(anchors) - 1, 4))
        for index, (source, target, relation_type) in enumerate(edge_specs):
            relationships.append(PersonalRelationship(
                stable_id("personal_relationship", seed,
                          identity("cohort_id", cohort.cohort_id),
                          identity("relationship_index", index)),
                source.person_id, target.person_id, relation_type, max(0, present_year - index % 20),
            ))
    result = (tuple(households), tuple(people), tuple(relationships))
    validate_relationships(*result, cohorts, settlements)
    return result
