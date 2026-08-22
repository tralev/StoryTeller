"""Temporal entity and exactly-once delta validation for authoritative history."""
from __future__ import annotations

from dataclasses import dataclass

from .conservation import ACCOUNT_BY_KIND, ConservationEntry
from .events import ConsequenceKind, HistoryEvent, apply_event, ordered_events
from .state import SimulationState


@dataclass(frozen=True)
class TemporalIntegrityReport:
    event_count: int
    consequence_count: int
    conserved_delta_count: int
    created_entity_count: int
    final_event_id: str


def _created_ids(event: HistoryEvent) -> tuple[str, ...]:
    created: list[str] = []
    for consequence in event.consequences:
        if consequence.kind is ConsequenceKind.RELIGIOUS_SCHISM_ADD:
            created.append(consequence.target)
        elif consequence.kind is ConsequenceKind.SETTLEMENT_WORKSHOP_ADD:
            created.append(consequence.value.split("|", 1)[0])
        elif consequence.kind is ConsequenceKind.ARTIFACT_CREATE:
            created.append(consequence.subject)
    return tuple(created)


def validate_temporal_integrity(
    events: tuple[HistoryEvent, ...],
    genesis_state: SimulationState,
    final_state: SimulationState,
    genesis_entity_ids: tuple[str, ...],
    conservation_entries: tuple[ConservationEntry, ...],
) -> TemporalIntegrityReport:
    """Replay sealed events while checking temporal references and delta ownership."""
    if events != ordered_events(events):
        raise ValueError("WG-HISTORY-TEMPORAL: events are not in canonical order")
    known = set(genesis_entity_ids)
    seen_events: set[str] = set()
    delta_owners: set[str] = set()
    conservation_by_owner = {entry.entry_id: entry for entry in conservation_entries}
    if len(conservation_by_owner) != len(conservation_entries):
        raise ValueError("WG-HISTORY-DELTA: duplicate conservation owner")
    state = genesis_state
    created_count = 0
    consequence_count = 0
    for event in events:
        if not event.envelope_version or any(cause not in seen_events for cause in event.causes):
            raise ValueError(f"WG-HISTORY-CAUSE: invalid ancestry for {event.event_id}")
        created = set(_created_ids(event))
        if created & known or len(created) != len(_created_ids(event)):
            raise ValueError(f"WG-HISTORY-ENTITY-CREATE: duplicate identity in {event.event_id}")
        addressable = known | created
        if (any(item not in addressable for item in event.participants)
                or any(item not in addressable for item in event.locations)
                or any(item not in addressable for item in event.source_ids)):
            raise ValueError(f"WG-HISTORY-ENTITY: unknown temporal reference in {event.event_id}")
        for index, consequence in enumerate(event.consequences):
            owner = f"{event.event_id}:{index}"
            if owner in delta_owners:
                raise ValueError(f"WG-HISTORY-DELTA: duplicate owner {owner}")
            delta_owners.add(owner)
            consequence_count += 1
            conservation = conservation_by_owner.get(owner)
            account = ACCOUNT_BY_KIND.get(consequence.kind)
            if consequence.amount and account:
                if (conservation is None or conservation.event_id != event.event_id
                        or conservation.subject_id != consequence.subject
                        or conservation.account != account
                        or conservation.delta != consequence.amount):
                    raise ValueError(f"WG-HISTORY-DELTA: uncovered material delta {owner}")
            elif conservation is not None:
                raise ValueError(f"WG-HISTORY-DELTA: spurious conservation owner {owner}")
        state = apply_event(state, event)
        seen_events.add(event.event_id)
        known.update(created)
        created_count += len(created)
    if state != final_state:
        raise ValueError("WG-HISTORY-REPLAY: temporal replay disagrees with final state")
    if set(conservation_by_owner) - delta_owners:
        raise ValueError("WG-HISTORY-DELTA: orphan conservation entries")
    return TemporalIntegrityReport(
        len(events), consequence_count, len(conservation_entries), created_count,
        events[-1].event_id if events else "",
    )
