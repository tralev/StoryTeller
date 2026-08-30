from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.conservation import build_conservation_ledger
from src.worldgen.simulation.events import apply_event
from src.worldgen.simulation.replay import _event, _state
from src.worldgen.simulation.temporal_integrity import validate_temporal_integrity


def test_temporal_integrity_report_covers_the_complete_ledger(simulated_world) -> None:
    _, historical, result = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    report = repository.load_verified("temporal_integrity").payload
    history = repository.load_verified("history").payload

    assert report["event_count"] == result["events"] == len(history)
    assert report["consequence_count"] == sum(len(event["consequences"]) for event in history)
    assert report["conserved_delta_count"] > 0
    assert report["final_event_id"] == history[-1]["event_id"]


def test_temporal_integrity_rejects_unknown_entities_causes_and_delta_owners(
    simulated_world,
) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    genesis = _state(repository.load_verified("snapshots").payload[0]["state"])
    event = _event(repository.load_verified("history").payload[0])
    final = apply_event(genesis, event)
    conservation = build_conservation_ledger((event,))
    known = event.source_ids

    validate_temporal_integrity((event,), genesis, final, known, conservation)
    with pytest.raises(ValueError, match="WG-HISTORY-ENTITY"):
        validate_temporal_integrity(
            (replace(event, participants=("unknown_entity",)),),
            genesis,
            final,
            known,
            conservation,
        )
    with pytest.raises(ValueError, match="WG-HISTORY-CAUSE"):
        validate_temporal_integrity(
            (replace(event, causes=("future_event",)),),
            genesis,
            final,
            known,
            conservation,
        )
    with pytest.raises(ValueError, match="WG-HISTORY-DELTA"):
        validate_temporal_integrity(
            (event,),
            genesis,
            final,
            known,
            conservation + conservation[:1],
        )
