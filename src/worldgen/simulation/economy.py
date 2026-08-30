"""Validation for the replayed settlement-level economy ledger."""

from __future__ import annotations

from .state import EconomyLedgerEntry

PRICE_EQUATION_VERSION = "grain-scarcity-v1"
PRICE_MIN_PPM = 100_000
PRICE_MAX_PPM = 5_000_000


def grain_price_ppm(population: int, available_grain: int) -> int:
    from ..numeric import div_round_half_up

    if population < 0 or available_grain < 0:
        raise ValueError("WG-PRICE-INPUT: population and grain must be nonnegative")
    return min(
        PRICE_MAX_PPM,
        max(
            PRICE_MIN_PPM,
            div_round_half_up(population * 1_000_000, max(1, available_grain)),
        ),
    )


ECONOMY_LEDGER_KINDS = frozenset(
    {
        "trade",
        "scarcity_price",
        "tax_assessment",
        "route_maintenance",
        "resource_depletion",
        "resource_recovery",
    }
)


def validate_economy_ledger(entries: tuple[EconomyLedgerEntry, ...]) -> None:
    ids = {entry.event_id for entry in entries}
    if len(ids) != len(entries):
        raise ValueError("WG-ECONOMY-LEDGER-ID: duplicate entry")
    for entry in entries:
        if entry.kind not in ECONOMY_LEDGER_KINDS or entry.amount < 0 or not entry.subject_id:
            raise ValueError(f"WG-ECONOMY-LEDGER: {entry.event_id}")
        if entry.kind == "trade":
            if (
                not entry.route_ids
                or entry.transport_capacity < 1
                or entry.amount > entry.transport_capacity
            ):
                raise ValueError(f"WG-ECONOMY-TRANSPORT: {entry.event_id}")
        elif entry.route_ids or entry.transport_capacity:
            raise ValueError(f"WG-ECONOMY-ROUTE-SCOPE: {entry.event_id}")
