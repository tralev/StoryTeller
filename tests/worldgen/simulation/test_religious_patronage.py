from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind, HistoryEvent
from src.worldgen.simulation.magic import Religion, ReligiousInstitution
from src.worldgen.simulation.religious_patronage import project_religious_patronage
from src.worldgen.simulation.replay import _event, _state


def test_religious_patronage_is_event_sourced_and_identity_linked(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    patronages = repository.load_verified("religious_patronage").payload
    history = repository.load_verified("history").payload
    religion_events = {item["event_id"]: item for item in history
                       if item["kind"] == "religion"}
    identities = repository.load_verified("identities").payload
    religion_ids = {item["religion_id"] for item in identities["religions"]}
    institution_ids = {item["institution_id"] for item in
                       identities["religious_institutions"]}
    assert patronages and len(patronages) == len(religion_events)
    for patronage in patronages:
        event = religion_events[patronage["event_id"]]
        assert patronage["religion_id"] in religion_ids
        assert patronage["institution_id"] in institution_ids
        assert patronage["civilization_id"] in event["participants"]
        assert patronage["holy_site_id"] in event["locations"]
        additions = [item for item in event["consequences"]
                     if item["kind"] == "religious_patronage_add"]
        assert len(additions) == 1 and additions[0]["amount"] == 0


def test_patronage_projector_rejects_mismatched_holy_site(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    state = _state(repository.load_verified("snapshots").payload[0]["state"])
    identities = repository.load_verified("identities").payload
    religions = tuple(Religion(**item) for item in identities["religions"])
    institutions = tuple(ReligiousInstitution(**item)
                         for item in identities["religious_institutions"])
    patronage_event = next(item for item in events if item.kind is EventKind.RELIGION)
    malformed = replace(
        patronage_event,
        consequences=tuple(
            replace(item, details=(("holy_site_id", "forged-site"),))
            if item.kind is ConsequenceKind.RELIGIOUS_PATRONAGE_ADD else item
            for item in patronage_event.consequences
        ),
    )
    altered = tuple(malformed if item.event_id == malformed.event_id else item for item in events)
    with pytest.raises(ValueError, match="WG-RELIGIOUS-PATRONAGE"):
        project_religious_patronage(42, altered, state.civilizations, religions, institutions)


def test_event_applier_rejects_material_weight_on_patronage(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    state = _state(repository.load_verified("snapshots").payload[0]["state"])
    event = HistoryEvent(
        "invalid-patronage", 1, 1, 1, EventKind.RELIGION, (), (state.civilizations[0].civilization_id,),
        (state.civilizations[0].capital_site_id,),
        (Consequence(ConsequenceKind.RELIGIOUS_PATRONAGE_ADD,
                     state.civilizations[0].civilization_id, 1, "religion", "institution"),),
        "Invalid patronage.",
    )
    from src.worldgen.simulation.events import apply_event
    with pytest.raises(ValueError, match="WG-RELIGIOUS-PATRONAGE-CONSEQUENCE"):
        apply_event(state, event)
