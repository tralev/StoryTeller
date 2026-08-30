"""Explicit source, sink, and transfer accounting for simulation quantities."""

from __future__ import annotations

from dataclasses import dataclass

from .events import ConsequenceKind, EventKind, HistoryEvent


@dataclass(frozen=True)
class ConservationEntry:
    entry_id: str
    event_id: str
    account: str
    subject_id: str
    delta: int
    classification: str


ACCOUNT_BY_KIND = {
    ConsequenceKind.POPULATION_DELTA: "people",
    ConsequenceKind.GRAIN_DELTA: "civilization_goods",
    ConsequenceKind.MATERIAL_DELTA: "civilization_goods",
    ConsequenceKind.CURRENCY_DELTA: "currency",
    ConsequenceKind.RESOURCE_STOCK_DELTA: "resource_goods",
    ConsequenceKind.SETTLEMENT_INVENTORY_DELTA: "settlement_goods",
}


def build_conservation_ledger(events: tuple[HistoryEvent, ...]) -> tuple[ConservationEntry, ...]:
    result: list[ConservationEntry] = []
    for event in events:
        for index, consequence in enumerate(event.consequences):
            account = ACCOUNT_BY_KIND.get(consequence.kind)
            if account is None or consequence.amount == 0:
                continue
            transfer = event.kind in (EventKind.TRADE, EventKind.MIGRATION)
            classification = (
                "transfer" if transfer else "source" if consequence.amount > 0 else "sink"
            )
            result.append(
                ConservationEntry(
                    f"{event.event_id}:{index}",
                    event.event_id,
                    account,
                    consequence.subject,
                    consequence.amount,
                    classification,
                )
            )
    return tuple(result)


def validate_conservation_ledger(
    events: tuple[HistoryEvent, ...], entries: tuple[ConservationEntry, ...]
) -> None:
    expected = build_conservation_ledger(events)
    if entries != expected:
        raise ValueError("WG-CONSERVATION-COVERAGE: ledger does not cover exact consequences")
    if len({entry.entry_id for entry in entries}) != len(entries):
        raise ValueError("WG-CONSERVATION-ID: duplicate entry")
    grouped: dict[tuple[str, str], int] = {}
    for entry in entries:
        if entry.classification == "source" and entry.delta <= 0:
            raise ValueError(f"WG-CONSERVATION-SOURCE: {entry.entry_id}")
        if entry.classification == "sink" and entry.delta >= 0:
            raise ValueError(f"WG-CONSERVATION-SINK: {entry.entry_id}")
        if entry.classification == "transfer":
            key = (entry.event_id, entry.account)
            grouped[key] = grouped.get(key, 0) + entry.delta
    if any(balance for balance in grouped.values()):
        raise ValueError("WG-CONSERVATION-TRANSFER: unbalanced transfer")
