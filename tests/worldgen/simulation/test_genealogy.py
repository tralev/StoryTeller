from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.genealogy import (
    ConsequentialPerson, DynastyHouse, project_genealogy,
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
        "spouse", "parent_of", "adopted_parent_of", "house_member",
    }
    assert {item.event_id for item in relations} == {event.event_id for event in relationship_events}
    assert len(payload["relationships"]) == len(relations)


def test_genealogy_rejects_unknown_people_and_population_weight(simulated_world):
    _, houses, people, events = _loaded(simulated_world)
    with pytest.raises(ValueError, match="GENEALOGY-POPULATION"):
        project_genealogy(42, events, houses, (replace(people[0], population_weight=1),
                                                *people[1:]))
    with pytest.raises(ValueError, match="GENEALOGY-RELATION"):
        project_genealogy(42, events, houses, people[1:])
