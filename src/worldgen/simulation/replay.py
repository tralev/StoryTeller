"""Snapshot/ledger replay and simulation-directory validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast
import hashlib

from ..artifacts import WorldArtifactRepository
from ..artifacts import canonical_json
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from .history_clock import HistoryTick, validate_history_clock
from .snapshots import state_hash
from .sites import validate_site_lifecycle
from .state import (Cohort, CivilizationState, DiplomaticRelation, EconomyLedgerEntry, EconomyState,
                    InventoryStack, ResourceStock, SettlementState, SettlementStatus,
                    SimulationState, SiteState, WorkshopState)


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
                              for item in value["consequences"]), value["summary"])


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
    if not snapshots or snapshots[0]["year"] != 0 or snapshots[-1]["year"] != index["present_year"]:
        raise ValueError("WG-SNAPSHOT-COVERAGE: missing genesis or final snapshot")
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
        order = (event.year, event.month, event.sequence, event.event_id)
        if order <= previous_order:
            raise ValueError("WG-LEDGER-ORDER: history is not strictly ordered")
        if any(cause not in seen for cause in event.causes):
            raise ValueError("WG-LEDGER-CAUSE: cause does not precede consequence")
        seen.add(event.event_id); previous_order = order
    prefix = hashlib.sha256(b"storyteller.history.prefix.v1").hexdigest()
    batched_ids: list[str] = []
    artifact_root = Path(root) / "artifacts"
    for path in sorted(artifact_root.glob("history_[0-9][0-9][0-9][0-9]_*.json")):
        payload = cast(dict[str, Any], repository.load_verified(path.stem).payload)
        if payload["previous_prefix"] != prefix:
            raise ValueError("WG-LEDGER-PREFIX: broken monthly batch chain")
        prefix = hashlib.sha256(bytes.fromhex(prefix) + canonical_json(payload["events"])).hexdigest()
        if payload["prefix_sha256"] != prefix:
            raise ValueError("WG-LEDGER-PREFIX: invalid monthly prefix hash")
        batched_ids.extend(str(item["event_id"]) for item in payload["events"])
    if prefix != index["ledger_prefix_sha256"] or batched_ids != [event.event_id for event in history]:
        raise ValueError("WG-LEDGER-PREFIX: batches do not reproduce full ledger")
    for start_raw, expected_raw in zip(snapshots, snapshots[1:]):
        state = _state(start_raw["state"])
        if state_hash(state) != start_raw["state_hash"]:
            raise ValueError("WG-SNAPSHOT-HASH: corrupt starting snapshot")
        for event in history:
            if start_raw["year"] < event.year <= expected_raw["year"]:
                state = apply_event(state, event)
        if state_hash(state) != expected_raw["state_hash"]:
            raise ValueError(f"WG-REPLAY: snapshot mismatch at year {expected_raw['year']}")
    return {"events": len(history), "snapshots": len(snapshots),
            "present_year": int(index["present_year"])}
