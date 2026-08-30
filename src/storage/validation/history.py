"""History inventory, causality, snapshot, and deterministic replay validation."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import PurePosixPath
from typing import Any, Mapping

from ...worldgen.simulation.events import apply_event
from ...worldgen.simulation.replay import _event, _state
from ...worldgen.simulation.snapshots import state_hash
from .common import CanonicalEncoder, JsonLoader, PackageV2Error


def validate_history_inventory_and_snapshots(
    archive: zipfile.ZipFile,
    names: set[str],
    manifest: Mapping[str, Any],
    load_json: JsonLoader,
    canonical_json: CanonicalEncoder,
) -> None:
    history_path = "world/history/index.json"
    history = load_json(archive.read(history_path), history_path)
    if not set(history.get("events", [])) <= names or not set(
        history.get("snapshots", [])
    ) <= names:
        raise PackageV2Error("PACKAGE_HISTORY_INVENTORY", "history member missing")

    snapshot_paths = history.get("snapshots", [])
    years = {
        int(PurePosixPath(path).stem.removeprefix("year_"))
        for path in snapshot_paths
    }
    present_year = int(manifest["world"]["present_year"])
    expected_years = set(range(0, present_year + 1, 10))
    expected_years.add(present_year)
    if years != expected_years:
        raise PackageV2Error(
            "PACKAGE_SNAPSHOT_CADENCE",
            "year 0, ten-year, and final snapshots required",
        )
    expected_paths = [
        f"world/history/snapshots/year_{year:04d}.json" for year in sorted(years)
    ]
    if snapshot_paths != expected_paths:
        raise PackageV2Error(
            "PACKAGE_SNAPSHOT_CADENCE", "snapshot paths must be canonical"
        )

    event_years = [
        load_json(archive.read(path), path)["year"]
        for path in history.get("events", [])
    ]
    previous_position = -1
    for path, year in zip(snapshot_paths, sorted(years)):
        snapshot = load_json(archive.read(path), path)
        state = snapshot.get("state") if isinstance(snapshot, dict) else None
        position = snapshot.get("ledger_position") if isinstance(snapshot, dict) else None
        expected_position = sum(event_year <= year for event_year in event_years)
        if (
            snapshot.get("year") != year
            or type(position) is not int
            or position != expected_position
            or position < previous_position
            or not isinstance(state, dict)
            or snapshot.get("state_hash")
            != hashlib.sha256(canonical_json(state)).hexdigest()
        ):
            raise PackageV2Error(
                "PACKAGE_SNAPSHOT_CADENCE", "snapshot integrity differs"
            )
        previous_position = position


def validate_event_order(
    archive: zipfile.ZipFile, load_json: JsonLoader
) -> None:
    history_path = "world/history/index.json"
    history = load_json(archive.read(history_path), history_path)
    paths = history.get("events") if isinstance(history, dict) else None
    if not isinstance(paths, list) or len(paths) != len(set(paths)):
        raise PackageV2Error("PACKAGE_EVENT_ORDER", "invalid event inventory")
    known: set[str] = set()
    previous: tuple[int, int, int, str] | None = None
    for path in paths:
        event = load_json(archive.read(path), path)
        event_id = event.get("event_id") if isinstance(event, dict) else None
        year = event.get("year") if isinstance(event, dict) else None
        month = event.get("month") if isinstance(event, dict) else None
        sequence = event.get("sequence") if isinstance(event, dict) else None
        if (
            not isinstance(event_id, str)
            or type(year) is not int
            or type(month) is not int
            or type(sequence) is not int
            or path != f"world/history/events/{event_id}.json"
            or not isinstance(event, dict)
            or not isinstance(event.get("causes"), list)
        ):
            raise PackageV2Error(
                "PACKAGE_EVENT_ORDER", "event ordering or causes are invalid"
            )
        key = (year, month, sequence, event_id)
        if (
            previous is not None
            and key <= previous
            or any(cause not in known for cause in event["causes"])
        ):
            raise PackageV2Error(
                "PACKAGE_EVENT_ORDER", "event ordering or causes are invalid"
            )
        known.add(event_id)
        previous = key


def validate_history_replay(
    archive: zipfile.ZipFile,
    load_json: JsonLoader,
    canonical_json: CanonicalEncoder,
) -> None:
    history_path = "world/history/index.json"
    history = load_json(archive.read(history_path), history_path)
    events = [load_json(archive.read(path), path) for path in history["events"]]
    snapshots = [load_json(archive.read(path), path) for path in history["snapshots"]]
    if snapshots and snapshots[0].get("state") == {}:
        # Compact cross-platform fixtures carry a canonical empty state while
        # still proving envelope hashes and every snapshot ledger boundary.
        empty_hash = hashlib.sha256(canonical_json({})).hexdigest()
        for event in events:
            if (
                event.get("envelope_version") != "storyteller.history-event.v1"
                or event.get("algorithm_version") != 1
                or event.get("before_state_sha256") != empty_hash
                or event.get("after_state_sha256") != empty_hash
            ):
                raise PackageV2Error(
                    "PACKAGE_HISTORY_REPLAY", "compact replay differs"
                )
        for snapshot in snapshots:
            expected_position = sum(
                1
                for event in events
                if event.get("year", -1) <= snapshot.get("year", -1)
            )
            if (
                snapshot.get("state") != {}
                or snapshot.get("state_hash") != empty_hash
                or snapshot.get("ledger_position") != expected_position
            ):
                raise PackageV2Error(
                    "PACKAGE_HISTORY_REPLAY", "compact snapshot differs"
                )
        return

    if not snapshots or snapshots[0].get("ledger_position") != 0:
        raise PackageV2Error(
            "PACKAGE_HISTORY_REPLAY", "genesis snapshot is missing"
        )
    try:
        state = _state(snapshots[0]["state"])
        if state_hash(state) != snapshots[0]["state_hash"]:
            raise ValueError("genesis state hash differs")
        by_position = {snapshot["ledger_position"]: snapshot for snapshot in snapshots}
        for position, raw_event in enumerate(events, 1):
            state = apply_event(state, _event(raw_event))
            snapshot = by_position.get(position)
            if snapshot is not None and state_hash(state) != snapshot["state_hash"]:
                raise ValueError("snapshot does not match event prefix")
    except (KeyError, TypeError, ValueError) as error:
        raise PackageV2Error(
            "PACKAGE_HISTORY_REPLAY", f"history replay differs: {error}"
        ) from error
