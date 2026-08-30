from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.genealogy import (
    ConsequentialPerson,
    DynastyHouse,
    project_genealogy,
    project_inheritances,
    project_person_statuses,
)
from src.worldgen.simulation.replay import _event


def _loaded(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    payload = repository.load_verified("genealogy").payload
    houses = tuple(DynastyHouse(**item) for item in payload["houses"])
    people = tuple(ConsequentialPerson(**item) for item in payload["people"])
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    return payload, houses, people, events


def test_genealogy_is_selective_event_sourced_and_does_not_add_population(simulated_world):
    payload, houses, people, events = _loaded(simulated_world)
    relationship_events = [event for event in events if event.kind.value == "relationship"]
    assert houses and people and relationship_events
    assert all(person.population_weight == 0 for person in people)
    assert len(people) == len(houses) * 4
    relations = project_genealogy(42, events, houses, people)
    assert relations
    assert {item.relation_type for item in relations} >= {
        "spouse",
        "parent_of",
        "adopted_parent_of",
        "disputed_parent_of",
        "house_member",
    }
    assert {item.event_id for item in relations} == {
        event.event_id for event in relationship_events
    }
    assert len(payload["relationships"]) == len(relations)
    inheritances = project_inheritances(42, events, houses, people)
    assert inheritances
    assert len(payload["inheritances"]) == len(inheritances)
    assert all(item.year >= 0 for item in inheritances)
    statuses = project_person_statuses(42, events, people)
    assert statuses and all(item.new_status == "dead" for item in statuses)
    assert len(payload["person_statuses"]) == len(statuses)


def test_genealogy_rejects_unknown_people_and_population_weight(simulated_world):
    _, houses, people, events = _loaded(simulated_world)
    with pytest.raises(ValueError, match="GENEALOGY-POPULATION"):
        project_genealogy(
            42, events, houses, (replace(people[0], population_weight=1), *people[1:])
        )
    with pytest.raises(ValueError, match="GENEALOGY-RELATION"):
        project_genealogy(42, events, houses, people[1:])


def test_genealogy_rejects_person_used_before_creation(simulated_world):
    _, houses, people, events = _loaded(simulated_world)
    referenced = next(
        person
        for person in people
        if any(person.person_id in event.participants for event in events)
    )
    altered = tuple(
        replace(person, created_year=max(event.year for event in events) + 1)
        if person.person_id == referenced.person_id
        else person
        for person in people
    )
    with pytest.raises(ValueError, match="GENEALOGY-TIME"):
        project_genealogy(42, events, houses, altered)


def test_genealogy_rejects_deep_parentage_cycle(simulated_world):
    _, houses, people, events = _loaded(simulated_world)
    relationship_events = [event for event in events if event.kind.value == "relationship"]
    template = relationship_events[0]
    cycle_events = tuple(
        replace(
            template,
            event_id=f"cycle-{index}",
            year=template.year + index,
            consequences=(
                replace(
                    template.consequences[0],
                    subject=people[index].person_id,
                    target=people[(index + 1) % 3].person_id,
                    value="parent_of",
                ),
            ),
        )
        for index in range(3)
    )
    with pytest.raises(ValueError, match="GENEALOGY-CYCLE"):
        project_genealogy(42, cycle_events, houses, people)
