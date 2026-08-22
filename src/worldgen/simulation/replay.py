"""Snapshot/ledger replay and simulation-directory validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast
import hashlib
from dataclasses import dataclass

from ..artifacts import WorldArtifactRepository
from ..artifacts import canonical_json
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from .history_clock import HistoryTick, validate_history_clock
from .snapshots import state_hash
from .sites import validate_site_lifecycle
from .state import (Cohort, CivilizationState, DiplomaticRelation, EconomyLedgerEntry, EconomyState,
                    InventoryStack, ResourceStock, SettlementState, SettlementStatus,
                    SimulationState, SiteState, WorkshopState)

HISTORY_PREFIX_GENESIS = hashlib.sha256(b"storyteller.history.prefix.v1").hexdigest()


@dataclass(frozen=True)
class HistoryBatchBoundary:
    artifact_id: str
    kind: str
    previous_prefix: str
    prefix_sha256: str
    event_ids: tuple[str, ...]


class ReplayDivergence(ValueError):
    """First deterministic divergence while replaying a snapshot suffix."""

    def __init__(self, boundary_year: int, event_id: str, reason: str) -> None:
        self.boundary_year = boundary_year
        self.event_id = event_id
        self.reason = reason
        location = f"event {event_id}" if event_id else "final snapshot"
        super().__init__(
            f"WG-REPLAY-DIVERGENCE: from year {boundary_year}, {location}: {reason}"
        )


def expected_snapshot_years(present_year: int) -> tuple[int, ...]:
    years = set(range(0, present_year + 1, 10))
    years.add(present_year)
    return tuple(sorted(years))


def validate_history_batch_chain(
    repository: WorldArtifactRepository,
    history: tuple[HistoryEvent, ...],
    expected_final_prefix: str,
) -> tuple[HistoryBatchBoundary, ...]:
    """Verify every atomically published batch and its exact prefix boundary."""
    if tuple(repository.root.glob("*.tmp")):
        raise ValueError("WG-LEDGER-ATOMIC: unpublished temporary batch remains")
    prefix = HISTORY_PREFIX_GENESIS
    batched_ids: list[str] = []
    boundaries: list[HistoryBatchBoundary] = []
    previous_artifact_id = ""
    paths = sorted(repository.root.glob("history_[0-9][0-9][0-9][0-9]_*.json"))
    for path in paths:
        artifact = repository.load_verified(path.stem)
        payload = cast(dict[str, Any], artifact.payload)
        events = cast(list[dict[str, Any]], payload.get("events", ()))
        if (not events or payload.get("previous_prefix") != prefix
                or (previous_artifact_id
                    and previous_artifact_id not in artifact.depends_on)):
            raise ValueError(f"WG-LEDGER-BOUNDARY: invalid committed batch {path.stem}")
        prefix = hashlib.sha256(bytes.fromhex(prefix) + canonical_json(events)).hexdigest()
        if payload.get("prefix_sha256") != prefix:
            raise ValueError(f"WG-LEDGER-PREFIX: invalid committed batch {path.stem}")
        event_ids = tuple(str(item["event_id"]) for item in events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError(f"WG-LEDGER-BOUNDARY: duplicate event in {path.stem}")
        batched_ids.extend(event_ids)
        boundaries.append(HistoryBatchBoundary(
            artifact.artifact_id, path.stem, str(payload["previous_prefix"]),
            str(payload["prefix_sha256"]), event_ids,
        ))
        previous_artifact_id = artifact.artifact_id
    if ((history and not boundaries) or prefix != expected_final_prefix
            or batched_ids != [event.event_id for event in history]):
        raise ValueError("WG-LEDGER-BOUNDARY: committed batches do not equal full ledger")
    return tuple(boundaries)


def replay_snapshot_to_final(
    start_snapshot: dict[str, Any],
    history: tuple[HistoryEvent, ...],
    final_snapshot: dict[str, Any],
) -> SimulationState:
    """Replay one snapshot suffix and identify its first divergent transition."""
    boundary_year = int(start_snapshot["year"])
    state = _state(cast(dict[str, Any], start_snapshot["state"]))
    if state_hash(state) != start_snapshot["state_hash"]:
        raise ReplayDivergence(boundary_year, "", "starting snapshot hash mismatch")
    previous_order = (boundary_year, 12, -1, "")
    for event in history:
        if event.year <= boundary_year:
            continue
        order = (event.year, event.month, event.sequence, event.event_id)
        if order <= previous_order:
            raise ReplayDivergence(boundary_year, event.event_id, "non-increasing event order")
        try:
            state = apply_event(state, event)
        except ValueError as error:
            raise ReplayDivergence(boundary_year, event.event_id, str(error)) from error
        previous_order = order
    expected_hash = str(final_snapshot["state_hash"])
    if state_hash(state) != expected_hash:
        raise ReplayDivergence(boundary_year, "", "final snapshot state mismatch")
    return state


def _state(value: dict[str, Any]) -> SimulationState:
    civilizations = tuple(CivilizationState(
        item["civilization_id"], item["name"], item["culture"], item["government"],
        item["language_id"], item["capital_site_id"], tuple(item["capabilities"]),
        tuple(item["needs"]), tuple(item["territory"]), item["population"],
        EconomyState(**item["economy"]), item["active"],
    ) for item in value["civilizations"])
    return SimulationState(
        value["year"], value["month"],
        tuple(SiteState(
            item["site_id"], item["region_id"], item["cell"], item["suitability_ppm"],
            item["water_access"], item["resource_access"],
            tuple((str(name), int(score)) for name, score in item["score_components"]),
        ) for item in value["sites"]),
        tuple(SettlementState(
            item["settlement_id"], item["site_id"], item["civilization_id"], item["name"],
            item["founded_year"], item["carrying_capacity"], item["population"],
            SettlementStatus(item["status"]), item["abandoned_year"], tuple(item["land_use"]),
            tuple(item["buildings"]), tuple(WorkshopState(**workshop)
                                             for workshop in item["workshops"]),
            tuple(InventoryStack(**stack) for stack in item["inventory"]),
        ) for item in value["settlements"]), civilizations,
        tuple(Cohort(**item) for item in value["cohorts"]),
        tuple(DiplomaticRelation(**item) for item in value["relations"]),
        tuple(ResourceStock(**item) for item in value["resource_stocks"]),
        tuple(EconomyLedgerEntry(
            item["event_id"], item["year"], item["month"], item["kind"], item["subject_id"],
            item["amount"], item["material_id"], tuple(item["route_ids"]),
            item["transport_capacity"],
        ) for item in value.get("economy_ledger", ())),
        tuple(value["applied_events"]),
    )


def _event(value: dict[str, Any]) -> HistoryEvent:
    return HistoryEvent(value["event_id"], value["year"], value["month"], value["sequence"],
                        EventKind(value["kind"]), tuple(value["causes"]),
                        tuple(value["participants"]), tuple(value["locations"]),
                        tuple(Consequence(ConsequenceKind(item["kind"]), item["subject"],
                                          item["amount"], item["target"], item["value"],
                                          tuple(tuple(pair) for pair in item.get("details", ())))
                              for item in value["consequences"]), value["summary"],
                        value.get("envelope_version", ""),
                        int(value.get("algorithm_version", 0)),
                        tuple(value.get("source_ids", ())),
                        value.get("before_state_sha256", ""),
                        value.get("after_state_sha256", ""))


def validate_simulation_directory(root: str | Path) -> dict[str, int]:
    repository = WorldArtifactRepository(Path(root) / "artifacts")
    index = cast(dict[str, Any], repository.load_verified("simulation_index").payload)
    history_raw = cast(list[dict[str, Any]], repository.load_verified("history").payload)
    history = tuple(_event(item) for item in history_raw)
    clock_raw = cast(list[dict[str, Any]], repository.load_verified("history_clock").payload)
    clock = tuple(HistoryTick(int(item["year"]), int(item["month"]),
                              tuple(item["accepted_event_ids"])) for item in clock_raw)
    validate_history_clock(int(index["present_year"]), clock, history)
    snapshots = cast(list[dict[str, Any]], repository.load_verified("snapshots").payload)
    actual_snapshot_years = tuple(int(item["year"]) for item in snapshots)
    required_snapshot_years = expected_snapshot_years(int(index["present_year"]))
    if actual_snapshot_years != required_snapshot_years:
        raise ValueError("WG-SNAPSHOT-COVERAGE: expected genesis, ten-year, and final snapshots")
    genesis_state = _state(snapshots[0]["state"])
    seed = int(index["seed"])
    for snapshot in snapshots:
        snapshot_state = _state(snapshot["state"])
        validate_site_lifecycle(seed, genesis_state.sites, snapshot_state.sites,
                                snapshot_state.settlements)
    published_sites_raw = cast(list[dict[str, Any]], repository.load_verified("sites").payload)
    published_sites = _state({**snapshots[-1]["state"], "sites": published_sites_raw}).sites
    validate_site_lifecycle(seed, genesis_state.sites, published_sites,
                            _state(snapshots[-1]["state"]).settlements)
    seen: set[str] = set()
    previous_order = (-1, -1, -1, "")
    for event in history:
        if not event.envelope_version:
            raise ValueError(f"WG-EVENT-ENVELOPE: unsealed persisted event: {event.event_id}")
        order = (event.year, event.month, event.sequence, event.event_id)
        if order <= previous_order:
            raise ValueError("WG-LEDGER-ORDER: history is not strictly ordered")
        if any(cause not in seen for cause in event.causes):
            raise ValueError("WG-LEDGER-CAUSE: cause does not precede consequence")
        seen.add(event.event_id); previous_order = order
    validate_history_batch_chain(repository, history, str(index["ledger_prefix_sha256"]))
    final_snapshot = snapshots[-1]
    for start_raw in snapshots:
        replay_snapshot_to_final(start_raw, history, final_snapshot)
    return {"events": len(history), "snapshots": len(snapshots),
            "present_year": int(index["present_year"])}
