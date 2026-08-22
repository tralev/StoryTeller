"""Complete-history retention inventory and validation."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass

from ..artifacts import canonical_json
from .events import HistoryEvent
from .snapshots import StateSnapshot
from .state import SettlementStatus, SimulationState


@dataclass(frozen=True)
class RetentionInventory:
    event_count: int
    event_ids: tuple[str, ...]
    snapshot_years: tuple[int, ...]
    civilization_ids: tuple[str, ...]
    settlement_ids: tuple[str, ...]
    site_ids: tuple[str, ...]
    extinct_civilization_ids: tuple[str, ...]
    abandoned_settlement_ids: tuple[str, ...]
    identity_ids: tuple[str, ...]
    unreferenced_identity_ids: tuple[str, ...]
    ledger_sha256: str
    snapshots_sha256: str
    identities_sha256: str
    registries_sha256: str
    dead_megabeast_ids: tuple[str, ...] = ()
    lost_artifact_ids: tuple[str, ...] = ()
    destroyed_artifact_ids: tuple[str, ...] = ()


def collect_identity_ids(value: object) -> tuple[str, ...]:
    """Collect every explicitly named identity field from a canonical payload."""
    found: set[str] = set()

    def visit(item: object, field_name: str = "") -> None:
        if is_dataclass(item) and not isinstance(item, type):
            visit(asdict(item), field_name)
        elif isinstance(item, Mapping):
            for key, child in item.items():
                visit(child, str(key))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                visit(child, field_name)
        elif isinstance(item, str) and field_name.endswith("_id") and item:
            found.add(item)

    visit(value)
    return tuple(sorted(found))


def build_retention_inventory(
    events: tuple[HistoryEvent, ...],
    snapshots: tuple[StateSnapshot, ...],
    registry_hashes: Mapping[str, str],
    identity_ids: tuple[str, ...],
    genesis_state: SimulationState,
    final_state: SimulationState,
    dead_megabeast_ids: tuple[str, ...] = (),
    lost_artifact_ids: tuple[str, ...] = (),
    destroyed_artifact_ids: tuple[str, ...] = (),
) -> RetentionInventory:
    """Prove authoritative entities survive regardless of downstream selection."""
    event_ids = tuple(event.event_id for event in events)
    canonical_identity_ids = tuple(sorted(set(identity_ids)))
    if len(event_ids) != len(set(event_ids)) or identity_ids != canonical_identity_ids:
        raise ValueError("WG-HISTORY-RETENTION: non-canonical event or identity inventory")
    genesis_civilizations = {item.civilization_id for item in genesis_state.civilizations}
    final_civilizations = {item.civilization_id for item in final_state.civilizations}
    genesis_settlements = {item.settlement_id for item in genesis_state.settlements}
    final_settlements = {item.settlement_id for item in final_state.settlements}
    genesis_sites = {item.site_id for item in genesis_state.sites}
    final_sites = {item.site_id for item in final_state.sites}
    if (not genesis_civilizations <= final_civilizations
            or not genesis_settlements <= final_settlements
            or not genesis_sites <= final_sites):
        raise ValueError("WG-HISTORY-RETENTION: original entity was discarded")
    referenced = {source_id for event in events for source_id in event.source_ids}
    return RetentionInventory(
        len(events), event_ids, tuple(snapshot.year for snapshot in snapshots),
        tuple(sorted(final_civilizations)), tuple(sorted(final_settlements)),
        tuple(sorted(final_sites)),
        tuple(sorted(item.civilization_id for item in final_state.civilizations
                     if not item.active)),
        tuple(sorted(item.settlement_id for item in final_state.settlements
                     if item.status is SettlementStatus.ABANDONED)),
        canonical_identity_ids,
        tuple(sorted(set(canonical_identity_ids) - referenced)),
        hashlib.sha256(canonical_json(events)).hexdigest(),
        hashlib.sha256(canonical_json(snapshots)).hexdigest(),
        hashlib.sha256(canonical_json(canonical_identity_ids)).hexdigest(),
        hashlib.sha256(canonical_json(dict(sorted(registry_hashes.items())))).hexdigest(),
        tuple(sorted(set(dead_megabeast_ids))),
        tuple(sorted(set(lost_artifact_ids))),
        tuple(sorted(set(destroyed_artifact_ids))),
    )
