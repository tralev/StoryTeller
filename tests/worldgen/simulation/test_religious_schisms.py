from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind, HistoryEvent
from src.worldgen.simulation.magic import Religion, ReligiousInstitution
from src.worldgen.simulation.religious_schisms import project_religious_schisms
from src.worldgen.simulation.replay import _event, _state


def _inputs(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    identities = repository.load_verified("identities").payload
    religions = tuple(Religion(**item) for item in identities["religions"])
    institutions = tuple(ReligiousInstitution(**item)
                         for item in identities["religious_institutions"])
    return repository, events, state, religions, institutions


def test_schism_is_event_sourced_and_preserves_parent_identity(simulated_world):
    repository, events, _, religions, institutions = _inputs(simulated_world)
    schisms = repository.load_verified("religious_schisms").payload
    schism_events = [item for item in events if item.kind is EventKind.SCHISM]
    parent_ids = {item.institution_id for item in institutions}

    assert schisms and len(schisms) == len(schism_events)
    for schism in schisms:
        event = next(item for item in schism_events if item.event_id == schism["event_id"])
        assert schism["parent_institution_id"] in parent_ids
        assert schism["child_institution_id"] not in parent_ids
        assert schism["parent_religion_id"] in {item.religion_id for item in religions}
        assert schism["parent_institution_id"] in event.participants
        assert schism["child_institution_id"] in event.participants
        assert event.locations == (schism["holy_site_id"],)


def test_schism_projector_rejects_forged_parent(simulated_world):
    _, events, state, religions, institutions = _inputs(simulated_world)
    source = next(item for item in events if item.kind is EventKind.SCHISM)
    malformed = replace(source, consequences=tuple(
        replace(item, value="forged-parent")
        if item.kind is ConsequenceKind.RELIGIOUS_SCHISM_ADD else item
        for item in source.consequences
    ))
    altered = tuple(malformed if item.event_id == source.event_id else item for item in events)
    with pytest.raises(ValueError, match="WG-RELIGIOUS-SCHISM"):
        project_religious_schisms(42, altered, state.civilizations, religions, institutions)


def test_event_applier_rejects_weighted_schism(simulated_world):
    _, _, state, _, _ = _inputs(simulated_world)
    event = HistoryEvent(
        "invalid-schism", 1, 1, 1, EventKind.SCHISM, (), ("civilization",), ("site",),
        (Consequence(ConsequenceKind.RELIGIOUS_SCHISM_ADD,
                     "religion", 1, "child", "parent"),), "Invalid schism.",
    )
    from src.worldgen.simulation.events import apply_event
    with pytest.raises(ValueError, match="WG-RELIGIOUS-SCHISM-CONSEQUENCE"):
        apply_event(state, event)
