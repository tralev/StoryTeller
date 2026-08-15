"""Canonical evidence that every configured history tick was executed."""
from __future__ import annotations

from dataclasses import dataclass

from .events import HistoryEvent


@dataclass(frozen=True)
class HistoryTick:
    year: int
    month: int
    accepted_event_ids: tuple[str, ...]


def validate_history_clock(history_years: int, ticks: tuple[HistoryTick, ...],
                           events: tuple[HistoryEvent, ...]) -> None:
    if history_years < 0:
        raise ValueError("WG-HISTORY-CLOCK: years must be nonnegative")
    expected_coordinates = tuple((year, month) for year in range(1, history_years + 1)
                                 for month in range(1, 13))
    if tuple((tick.year, tick.month) for tick in ticks) != expected_coordinates:
        raise ValueError("WG-HISTORY-CLOCK: missing, duplicate, or reordered tick")
    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("WG-HISTORY-CLOCK: duplicate event identity")
    grouped: dict[tuple[int, int], list[str]] = {coordinate: []
                                                for coordinate in expected_coordinates}
    for event in events:
        coordinate = (event.year, event.month)
        if coordinate not in grouped:
            raise ValueError("WG-HISTORY-CLOCK: event lies outside configured history")
        grouped[coordinate].append(event.event_id)
    for tick in ticks:
        expected_ids = tuple(grouped[(tick.year, tick.month)])
        if tick.accepted_event_ids != expected_ids:
            raise ValueError("WG-HISTORY-CLOCK: tick does not match accepted ledger events")
    flattened = tuple(event_id for tick in ticks for event_id in tick.accepted_event_ids)
    if flattened != tuple(event_ids):
        raise ValueError("WG-HISTORY-CLOCK: ticks do not reproduce ledger order")


def build_history_clock(history_years: int,
                        events: tuple[HistoryEvent, ...]) -> tuple[HistoryTick, ...]:
    grouped: dict[tuple[int, int], list[str]] = {
        (year, month): [] for year in range(1, history_years + 1) for month in range(1, 13)
    }
    for event in events:
        coordinate = (event.year, event.month)
        if coordinate not in grouped:
            raise ValueError("WG-HISTORY-CLOCK: event lies outside configured history")
        grouped[coordinate].append(event.event_id)
    result = tuple(HistoryTick(year, month, tuple(grouped[(year, month)]))
                   for year in range(1, history_years + 1) for month in range(1, 13))
    validate_history_clock(history_years, result, events)
    return result
