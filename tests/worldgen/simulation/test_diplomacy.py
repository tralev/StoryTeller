from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.diplomacy import project_diplomatic_transitions
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.replay import _event, _state


def _history_inputs(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    snapshots = repository.load_verified("snapshots").payload
    genesis = _state(snapshots[0]["state"])
    final = _state(snapshots[-1]["state"])
    return repository, events, genesis, final


def test_diplomacy_war_and_peace_are_typed_replayable_transitions(simulated_world):
    repository, events, genesis, final = _history_inputs(simulated_world)
    transitions = repository.load_verified("diplomatic_transitions").payload
    relation_events = [item for item in events
                       if item.kind in {EventKind.DIPLOMACY, EventKind.WAR, EventKind.PEACE}]

    assert transitions and len(transitions) == len(relation_events)
    assert any(item["new_status"] == "war" for item in transitions)
    for transition in transitions:
        source = next(item for item in relation_events
                      if item.event_id == transition["event_id"])
        assert source.participants == (
            transition["left_civilization_id"], transition["right_civilization_id"])
        assert transition["prior_status"] != transition["new_status"]
        if source.kind is EventKind.WAR:
            assert transition["left_material_cost"] <= 100
            assert transition["right_material_cost"] <= 100

    assert project_diplomatic_transitions(
        42, events, final.civilizations, genesis.relations, final.relations,
    )


def test_diplomacy_projector_rejects_forged_prior_status(simulated_world):
    _, events, genesis, final = _history_inputs(simulated_world)
    source = next(item for item in events if item.kind is EventKind.DIPLOMACY)
    malformed = replace(source, consequences=tuple(
        replace(item, details=(("prior_status", "war"), ("new_status", item.value)))
        if item.kind is ConsequenceKind.RELATION_SET else item
        for item in source.consequences
    ))
    altered = tuple(malformed if item.event_id == source.event_id else item for item in events)
    with pytest.raises(ValueError, match="WG-DIPLOMACY"):
        project_diplomatic_transitions(
            42, altered, final.civilizations, genesis.relations, final.relations,
        )


def test_war_is_the_only_relation_transition_allowed_to_spend_material(simulated_world):
    _, events, genesis, final = _history_inputs(simulated_world)
    source = next(item for item in events if item.kind is EventKind.DIPLOMACY)
    war = next(item for item in events if item.kind is EventKind.WAR)
    cost = next(item for item in war.consequences
                if item.kind is ConsequenceKind.MATERIAL_DELTA)
    malformed = replace(source, consequences=source.consequences + (cost,))
    altered = tuple(malformed if item.event_id == source.event_id else item for item in events)
    with pytest.raises(ValueError, match="WG-DIPLOMACY"):
        project_diplomatic_transitions(
            42, altered, final.civilizations, genesis.relations, final.relations,
        )
