import hashlib

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.replay import validate_simulation_directory
from src.worldgen.simulation.projections import history_summary
from src.worldgen.simulation.replay import _event, _state


def test_snapshot_schedule_and_replay(simulated_world):
    _, historical, result = simulated_world
    assert result["present_year"] == 55
    validated = validate_simulation_directory(historical)
    snapshots = WorldArtifactRepository(historical / "artifacts").load_verified("snapshots").payload
    assert [snapshot["year"] for snapshot in snapshots] == [0, 10, 20, 30, 40, 50, 55]
    assert validated["events"] == result["events"]


def test_physical_inputs_remain_byte_identical(simulated_world):
    physical, historical, _ = simulated_world
    index = WorldArtifactRepository(historical / "artifacts").load_verified("simulation_index").payload
    for kind, expected in index["physical_file_hashes"].items():
        assert hashlib.sha256((physical / "artifacts" / f"{kind}.json").read_bytes()).hexdigest() == expected


def test_summary_projection_never_replaces_full_ledger(simulated_world):
    _, historical, result = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    final_state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    ledger = tuple(_event(item) for item in repository.load_verified("history").payload)
    projection = history_summary(final_state, ledger, limit=3)
    assert len(projection["recent_events"]) == 3
    assert projection["authoritative_event_count"] == result["events"]
    assert projection["projection_is_complete"] is False
