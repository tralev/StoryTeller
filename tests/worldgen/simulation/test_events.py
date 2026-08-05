import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import apply_event
from src.worldgen.simulation.replay import _event, _state


def test_closed_events_have_complete_causal_envelopes(simulated_world):
    _, historical, _ = simulated_world
    history = WorldArtifactRepository(historical / "artifacts").load_verified("history").payload
    seen = set()
    for raw in history:
        event = _event(raw)
        assert event.participants
        assert event.locations
        assert event.consequences
        assert all(cause in seen for cause in event.causes)
        seen.add(event.event_id)
    assert any(raw["kind"] == "war" for raw in history)


def test_event_application_is_exactly_once(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshot = repository.load_verified("snapshots").payload[0]
    event = _event(repository.load_verified("history").payload[0])
    state = apply_event(_state(snapshot["state"]), event)
    with pytest.raises(ValueError, match="WG-EVENT-DUPLICATE"):
        apply_event(state, event)
