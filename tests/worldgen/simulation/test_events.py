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


def test_conquest_is_a_distinct_causal_territory_transition(simulated_world):
    _, historical, _ = simulated_world
    history = WorldArtifactRepository(historical / "artifacts").load_verified("history").payload
    by_id = {raw["event_id"]: raw for raw in history}
    conquests = [raw for raw in history if raw["kind"] == "conquest"]
    assert conquests
    for conquest in conquests:
        assert len(conquest["causes"]) == 1
        war = by_id[conquest["causes"][0]]
        assert war["kind"] == "war"
        assert conquest["year"] == war["year"] and conquest["month"] == war["month"]
        assert [item["kind"] for item in war["consequences"]].count("territory_transfer") == 0
        transfers = [item for item in conquest["consequences"]
                     if item["kind"] == "territory_transfer"]
        assert len(transfers) == 2
        assert {item["amount"] for item in transfers} == {-1, 1}
        assert len({item["value"] for item in transfers}) == 1


def test_event_application_is_exactly_once(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshot = repository.load_verified("snapshots").payload[0]
    event = _event(repository.load_verified("history").payload[0])
    state = apply_event(_state(snapshot["state"]), event)
    with pytest.raises(ValueError, match="WG-EVENT-DUPLICATE"):
        apply_event(state, event)
