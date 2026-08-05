"""Read-only bounded prompt projection; never an authoritative history store."""
from __future__ import annotations

from .events import HistoryEvent
from .state import SimulationState


def history_summary(state: SimulationState, ledger: tuple[HistoryEvent, ...], limit: int = 100) -> dict[str, object]:
    if limit < 0:
        raise ValueError("summary limit must be nonnegative")
    selected = ledger[-limit:] if limit else ()
    return {"present_year": state.year,
            "civilizations": tuple((c.civilization_id, c.name, c.population) for c in state.civilizations),
            "recent_events": tuple((e.event_id, e.year, e.kind.value, e.summary) for e in selected),
            "authoritative_event_count": len(ledger), "projection_is_complete": len(selected) == len(ledger)}
