from pathlib import Path

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.history_checkpoint import (
    CommittedHistoryCheckpoint,
    recover_committed_checkpoints,
    resume_committed_history,
)
from src.worldgen.simulation.replay import HISTORY_PREFIX_GENESIS, _event, _state
from src.worldgen.simulation.scheduler import PHYSICAL_KINDS, simulate_world


def test_every_committed_batch_resumes_exactly_once_to_the_next_boundary(
    simulated_world,
) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    genesis = _state(snapshots[0]["state"])
    final = _state(snapshots[-1]["state"])
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    checkpoints = recover_committed_checkpoints(repository, genesis)
    previous = CommittedHistoryCheckpoint(
        "genesis", "", HISTORY_PREFIX_GENESIS, 0, "", 0, 0, 0, genesis,
    )

    assert checkpoints
    for checkpoint in checkpoints:
        suffix = history[previous.event_count:checkpoint.event_count]
        resumed = resume_committed_history(previous, suffix)
        assert resumed == checkpoint.state
        assert resumed.applied_events == tuple(
            event.event_id for event in history[:checkpoint.event_count]
        )
        previous = checkpoint
    assert previous.state == final
    assert previous.event_count == len(history)


def test_resume_rejects_reapplication_of_a_committed_event(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    genesis = _state(repository.load_verified("snapshots").payload[0]["state"])
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    checkpoint = recover_committed_checkpoints(repository, genesis)[-1]

    with pytest.raises(ValueError, match="WG-HISTORY-RESUME-DUPLICATE"):
        resume_committed_history(checkpoint, (history[0],))


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_interrupted_rerun_matches_uninterrupted_bytes(simulated_world, tmp_path) -> None:
    physical, _, _ = simulated_world
    resumed = tmp_path / "resumed"
    uninterrupted = tmp_path / "uninterrupted"

    simulate_world(physical, 1, resumed)
    for path in (resumed / "artifacts").glob("*.json"):
        is_batch = path.stem.startswith("history_") and path.stem[8:12].isdigit()
        if path.stem not in PHYSICAL_KINDS and not is_batch:
            path.unlink()
    interrupted = resumed / "artifacts" / "history_0002_01.json.tmp"
    interrupted.write_bytes(b"partial-publication")
    simulate_world(physical, 2, resumed)
    simulate_world(physical, 2, uninterrupted)

    assert not interrupted.exists()
    assert _files(resumed) == _files(uninterrupted)
