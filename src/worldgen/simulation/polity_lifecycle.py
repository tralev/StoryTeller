"""Event-sourced collapse and recovery without deleting polity identities."""

from __future__ import annotations

from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, SettlementState, SettlementStatus


@dataclass(frozen=True)
class PolityLifecycleTransition:
    transition_id: str
    civilization_id: str
    settlement_id: str
    prior_polity_state: str
    new_polity_state: str
    prior_settlement_status: str
    new_settlement_status: str
    collapse_event_id: str
    event_id: str
    year: int


def project_polity_lifecycle(
    seed: int,
    events: tuple[HistoryEvent, ...],
    genesis_civilizations: tuple[CivilizationState, ...],
    genesis_settlements: tuple[SettlementState, ...],
    final_civilizations: tuple[CivilizationState, ...],
    final_settlements: tuple[SettlementState, ...],
) -> tuple[PolityLifecycleTransition, ...]:
    """Replay paired polity/settlement state changes and verify recovery ancestry."""
    active = {item.civilization_id: item.active for item in genesis_civilizations}
    settlement_status = {item.settlement_id: item.status for item in genesis_settlements}
    settlement_by_civ = {item.civilization_id: item for item in genesis_settlements}
    civilization_by_id = {item.civilization_id: item for item in genesis_civilizations}
    last_collapse: dict[str, str] = {}
    projected: list[PolityLifecycleTransition] = []
    for event in events:
        active_changes = [
            item for item in event.consequences if item.kind is ConsequenceKind.ACTIVE_SET
        ]
        status_changes = [
            item
            for item in event.consequences
            if item.kind is ConsequenceKind.SETTLEMENT_STATUS_SET
        ]
        if not active_changes and not status_changes:
            continue
        if (
            event.kind not in {EventKind.COLLAPSE, EventKind.RECOVERY}
            or len(active_changes) != 1
            or len(status_changes) != 1
        ):
            raise ValueError("WG-POLITY-LIFECYCLE: unpaired lifecycle transition")
        active_change, status_change = active_changes[0], status_changes[0]
        civilization = civilization_by_id.get(active_change.subject)
        settlement = settlement_by_civ.get(active_change.subject)
        details = dict(active_change.details)
        expected_collapse = last_collapse.get(active_change.subject, "")
        is_collapse = event.kind is EventKind.COLLAPSE
        expected_details = {
            "prior_polity_state": "active" if is_collapse else "inactive",
            "new_polity_state": "inactive" if is_collapse else "active",
            "prior_settlement_status": (
                SettlementStatus.INHABITED.value
                if is_collapse
                else SettlementStatus.ABANDONED.value
            ),
            "new_settlement_status": (
                SettlementStatus.ABANDONED.value
                if is_collapse
                else SettlementStatus.INHABITED.value
            ),
            "settlement_id": settlement.settlement_id if settlement else "",
        }
        if not is_collapse:
            expected_details["collapse_event_id"] = expected_collapse
        conflict_keys = tuple(details.get("conflict_keys", "").split(","))
        expected_conflict_keys = tuple(
            sorted(
                (
                    f"institution-polity:{active_change.subject}:{event.year:04d}",
                    f"institution-settlement:{settlement.settlement_id if settlement else ''}:"
                    f"{event.year:04d}",
                )
            )
        )
        proposal_details_valid = (
            set(details)
            == set(expected_details)
            | {
                "proposal_id",
                "conflict_keys",
                "snapshot",
            }
            and all(details.get(key) == value for key, value in expected_details.items())
            and details.get("proposal_id", "").startswith("history_proposal_")
            and conflict_keys == expected_conflict_keys
            and details.get("snapshot") == f"{event.year:04d}:12"
        )
        if (
            civilization is None
            or settlement is None
            or status_change.subject != settlement.settlement_id
            or status_change.details != active_change.details
            or event.participants != (civilization.civilization_id,)
            or event.locations != (civilization.capital_site_id,)
            or not proposal_details_valid
            or active[active_change.subject] is not is_collapse
            or settlement_status[settlement.settlement_id]
            is not (SettlementStatus.INHABITED if is_collapse else SettlementStatus.ABANDONED)
            or active_change.value != expected_details["new_polity_state"]
            or status_change.value != expected_details["new_settlement_status"]
            or (not is_collapse and event.causes != (expected_collapse,))
        ):
            raise ValueError("WG-POLITY-LIFECYCLE: invalid collapse or recovery")
        if is_collapse:
            last_collapse[active_change.subject] = event.event_id
        active[active_change.subject] = not is_collapse
        settlement_status[settlement.settlement_id] = (
            SettlementStatus.ABANDONED if is_collapse else SettlementStatus.INHABITED
        )
        projected.append(
            PolityLifecycleTransition(
                stable_id("polity_lifecycle", seed, identity("event_id", event.event_id)),
                civilization.civilization_id,
                settlement.settlement_id,
                expected_details["prior_polity_state"],
                expected_details["new_polity_state"],
                expected_details["prior_settlement_status"],
                expected_details["new_settlement_status"],
                event.event_id if is_collapse else expected_collapse,
                event.event_id,
                event.year,
            )
        )
    if active != {item.civilization_id: item.active for item in final_civilizations}:
        raise ValueError("WG-POLITY-LIFECYCLE: final polity state mismatch")
    if settlement_status != {item.settlement_id: item.status for item in final_settlements}:
        raise ValueError("WG-POLITY-LIFECYCLE: final settlement state mismatch")
    return tuple(projected)
