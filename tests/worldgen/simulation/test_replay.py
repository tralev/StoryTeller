import hashlib
import shutil
from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.projections import history_summary
from src.worldgen.simulation.replay import (
    ReplayDivergence,
    _event,
    _state,
    expected_snapshot_years,
    replay_snapshot_to_final,
    validate_history_batch_chain,
    validate_simulation_directory,
)


def test_snapshot_schedule_and_replay(simulated_world):
    _, historical, result = simulated_world
    assert result["present_year"] == 55
    validated = validate_simulation_directory(historical)
    snapshots = WorldArtifactRepository(historical / "artifacts").load_verified("snapshots").payload
    assert [snapshot["year"] for snapshot in snapshots] == [0, 10, 20, 30, 40, 50, 55]
    assert validated["events"] == result["events"]
    assert tuple(snapshot["year"] for snapshot in snapshots) == expected_snapshot_years(55)


def test_every_snapshot_replays_independently_to_identical_final_state(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    final = snapshots[-1]

    replayed = tuple(replay_snapshot_to_final(snapshot, history, final)
                     for snapshot in snapshots)
    assert all(state == replayed[-1] for state in replayed)


def test_replay_reports_first_missing_reordered_duplicated_and_tampered_event(
    simulated_world,
):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    start, final = snapshots[-2], snapshots[-1]
    suffix_indexes = [index for index, event in enumerate(history)
                      if event.year > start["year"]]
    first_index, second_index = suffix_indexes[:2]
    first, second = history[first_index], history[second_index]

    missing = history[:first_index] + history[first_index + 1:]
    with pytest.raises(ReplayDivergence) as missing_error:
        replay_snapshot_to_final(start, missing, final)
    assert missing_error.value.boundary_year == start["year"]
    assert missing_error.value.event_id == second.event_id

    reordered = list(history)
    reordered[first_index], reordered[second_index] = second, first
    with pytest.raises(ReplayDivergence) as reordered_error:
        replay_snapshot_to_final(start, tuple(reordered), final)
    assert reordered_error.value.event_id == second.event_id

    duplicated = history[:second_index] + (first,) + history[second_index:]
    with pytest.raises(ReplayDivergence) as duplicate_error:
        replay_snapshot_to_final(start, duplicated, final)
    assert duplicate_error.value.event_id == first.event_id

    tampered = replace(
        first,
        consequences=(replace(first.consequences[0], amount=first.consequences[0].amount + 1),)
        + first.consequences[1:],
    )
    altered = history[:first_index] + (tampered,) + history[first_index + 1:]
    with pytest.raises(ReplayDivergence) as tampered_error:
        replay_snapshot_to_final(start, altered, final)
    assert tampered_error.value.event_id == first.event_id

    shortened = history[:-1]
    with pytest.raises(ReplayDivergence) as final_error:
        replay_snapshot_to_final(start, shortened, final)
    assert final_error.value.event_id == ""
    assert "final snapshot" in str(final_error.value)


def test_every_committed_batch_boundary_is_chained_and_truncation_is_rejected(
    simulated_world, tmp_path,
):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    index = repository.load_verified("simulation_index").payload
    boundaries = validate_history_batch_chain(
        repository, history, index["ledger_prefix_sha256"],
    )

    assert boundaries
    assert sum(len(item.event_ids) for item in boundaries) == len(history)
    assert all(right.previous_prefix == left.prefix_sha256
               for left, right in zip(boundaries, boundaries[1:]))

    damaged_root = tmp_path / "artifacts"
    damaged_root.mkdir()
    batch_paths = sorted((historical / "artifacts").glob(
        "history_[0-9][0-9][0-9][0-9]_*.json"
    ))
    for source in batch_paths:
        shutil.copy2(source, damaged_root / source.name)
    damaged = WorldArtifactRepository(damaged_root)
    middle = batch_paths[len(batch_paths) // 2]
    damaged_middle = damaged_root / middle.name
    damaged_middle.unlink()
    with pytest.raises(ValueError, match="WG-LEDGER-BOUNDARY"):
        validate_history_batch_chain(damaged, history, index["ledger_prefix_sha256"])
    shutil.copy2(middle, damaged_middle)
    damaged_middle.write_bytes(b"{")
    with pytest.raises((ValueError, OSError)):
        validate_history_batch_chain(damaged, history, index["ledger_prefix_sha256"])


def test_unpublished_batch_temp_file_is_rejected(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    index = repository.load_verified("simulation_index").payload
    temporary = repository.root / "interrupted-history.json.tmp"
    temporary.write_bytes(b"partial")
    try:
        with pytest.raises(ValueError, match="WG-LEDGER-ATOMIC"):
            validate_history_batch_chain(repository, history, index["ledger_prefix_sha256"])
    finally:
        temporary.unlink()


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
