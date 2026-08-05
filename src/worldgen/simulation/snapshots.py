"""Canonical snapshots and state hashing."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import canonical_json
from .state import SimulationState


def state_payload(state: SimulationState) -> dict[str, Any]:
    return asdict(state)


def state_hash(state: SimulationState) -> str:
    return hashlib.sha256(canonical_json(state_payload(state))).hexdigest()


@dataclass(frozen=True)
class StateSnapshot:
    year: int
    state_hash: str
    state: dict[str, Any]


def make_snapshot(state: SimulationState) -> StateSnapshot:
    return StateSnapshot(state.year, state_hash(state), state_payload(state))
