"""Committed-batch checkpoint recovery and exactly-once history resume."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, cast

from ..artifacts import WorldArtifactRepository, canonical_json
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from .replay import HISTORY_PREFIX_GENESIS
from .state import SimulationState


@dataclass(frozen=True)
class CommittedHistoryCheckpoint:
    batch_kind: str
    batch_artifact_id: str
    prefix_sha256: str
    event_count: int
    final_event_id: str
    final_year: int
    final_month: int
    final_sequence: int
    state: SimulationState


def _event(value: dict[str, Any]) -> HistoryEvent:
    return HistoryEvent(
        str(value["event_id"]), int(value["year"]), int(value["month"]),
        int(value["sequence"]), EventKind(value["kind"]), tuple(value["causes"]),
        tuple(value["participants"]), tuple(value["locations"]),
        tuple(Consequence(
            ConsequenceKind(item["kind"]), str(item["subject"]), int(item["amount"]),
            str(item["target"]), str(item["value"]),
            tuple(tuple(pair) for pair in item.get("details", ())),
        ) for item in value["consequences"]), str(value["summary"]),
        str(value["envelope_version"]), int(value["algorithm_version"]),
        tuple(value["source_ids"]), str(value["before_state_sha256"]),
        str(value["after_state_sha256"]),
    )


def recover_committed_checkpoints(
    repository: WorldArtifactRepository,
    genesis_state: SimulationState,
) -> tuple[CommittedHistoryCheckpoint, ...]:
    """Recover every complete batch prefix; never expose a partial publication."""
    if tuple(repository.root.glob("*.tmp")):
        raise ValueError("WG-HISTORY-CHECKPOINT: interrupted publication remains")
    state = genesis_state
    prefix = HISTORY_PREFIX_GENESIS
    previous_artifact_id = ""
    event_count = 0
    checkpoints: list[CommittedHistoryCheckpoint] = []
    for path in sorted(repository.root.glob("history_[0-9][0-9][0-9][0-9]_*.json")):
        artifact = repository.load_verified(path.stem)
        payload = cast(dict[str, Any], artifact.payload)
        raw_events = cast(list[dict[str, Any]], payload.get("events", ()))
        if (not raw_events or payload.get("previous_prefix") != prefix
                or (previous_artifact_id
                    and previous_artifact_id not in artifact.depends_on)):
            raise ValueError(f"WG-HISTORY-CHECKPOINT: broken boundary {path.stem}")
        prefix = hashlib.sha256(bytes.fromhex(prefix) + canonical_json(raw_events)).hexdigest()
        if payload.get("prefix_sha256") != prefix:
            raise ValueError(f"WG-HISTORY-CHECKPOINT: invalid prefix {path.stem}")
        events = tuple(_event(item) for item in raw_events)
        for event in events:
            state = apply_event(state, event)
        event_count += len(events)
        checkpoints.append(CommittedHistoryCheckpoint(
            path.stem, artifact.artifact_id, prefix, event_count,
            events[-1].event_id, events[-1].year, events[-1].month,
            events[-1].sequence, state,
        ))
        previous_artifact_id = artifact.artifact_id
    return tuple(checkpoints)


def resume_committed_history(
    checkpoint: CommittedHistoryCheckpoint,
    suffix: tuple[HistoryEvent, ...],
) -> SimulationState:
    """Apply only events beyond a committed checkpoint, exactly once and in order."""
    state = checkpoint.state
    previous = (
        checkpoint.final_year, checkpoint.final_month,
        checkpoint.final_sequence, checkpoint.final_event_id,
    )
    for event in suffix:
        if event.event_id in state.applied_events:
            raise ValueError(f"WG-HISTORY-RESUME-DUPLICATE: {event.event_id}")
        order = (event.year, event.month, event.sequence, event.event_id)
        if order <= previous:
            raise ValueError(f"WG-HISTORY-RESUME-ORDER: {event.event_id}")
        state = apply_event(state, event)
        previous = order
    return state
