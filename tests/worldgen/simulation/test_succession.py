from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.genealogy import (
    ConsequentialPerson,
    DynastyHouse,
    project_inheritances,
)
from src.worldgen.simulation.replay import _event, _state
from src.worldgen.simulation.succession import project_successions


def test_succession_names_officeholders_and_cites_genealogical_claim(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    successions = repository.load_verified("successions").payload
    history = repository.load_verified("history").payload
    by_id = {item["event_id"]: item for item in history}
    genealogy = repository.load_verified("genealogy").payload
    person_ids = {item["person_id"] for item in genealogy["people"]}
    assert successions
    for succession in successions:
        event = by_id[succession["event_id"]]
        claim = by_id[succession["claim_event_id"]]
        assert event["kind"] == "succession" and claim["kind"] == "relationship"
        assert succession["claim_event_id"] in event["causes"]
        assert {succession["outgoing_person_id"], succession["incoming_person_id"]} == set(
            event["participants"]
        )
        assert succession["outgoing_person_id"] in person_ids
        assert succession["incoming_person_id"] in person_ids
        assert any(item["kind"] == "officeholder_set" for item in event["consequences"])
        assert any(
            item["kind"] == "inheritance_transfer"
            and item["subject"] == succession["outgoing_person_id"]
            and item["target"] == succession["incoming_person_id"]
            and item["value"] == succession["house_id"]
            for item in event["consequences"]
        )
        assert any(
            item["kind"] == "currency_delta" and item["amount"] == -5
            for item in event["consequences"]
        )


def test_succession_projector_rejects_forged_claim_causality(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    succession = next(item for item in events if item.kind is EventKind.SUCCESSION)
    forged = replace(succession, causes=())
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    genealogy = repository.load_verified("genealogy").payload
    houses = tuple(DynastyHouse(**item) for item in genealogy["houses"])
    people = tuple(ConsequentialPerson(**item) for item in genealogy["people"])
    state = _state(repository.load_verified("snapshots").payload[0]["state"])
    with pytest.raises(ValueError, match="WG-SUCCESSION"):
        project_successions(42, altered, state.civilizations, houses, people)


def test_inheritance_projection_rejects_unknown_heir(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    genealogy = repository.load_verified("genealogy").payload
    houses = tuple(DynastyHouse(**item) for item in genealogy["houses"])
    people = tuple(ConsequentialPerson(**item) for item in genealogy["people"])
    succession = next(item for item in events if item.kind is EventKind.SUCCESSION)
    altered_consequences = tuple(
        replace(item, target="unknown-heir")
        if item.kind is ConsequenceKind.INHERITANCE_TRANSFER
        else item
        for item in succession.consequences
    )
    forged = replace(succession, consequences=altered_consequences)
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    with pytest.raises(ValueError, match="WG-INHERITANCE"):
        project_inheritances(42, altered, houses, people)
