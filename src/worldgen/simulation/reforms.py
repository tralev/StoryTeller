"""Typed government reforms projected from accepted history."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState


@dataclass(frozen=True)
class GovernmentReform:
    reform_id: str
    civilization_id: str
    prior_government: str
    new_government: str
    pressure_kind: str
    pressure_ppm: int
    currency_cost: int
    event_id: str
    year: int


def project_government_reforms(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    government_entries: tuple[Mapping[str, object], ...],
) -> tuple[GovernmentReform, ...]:
    """Validate non-no-op reform chains and their pressure evidence."""
    valid_governments = {str(item["id"]) for item in government_entries}
    civilization_by_id = {item.civilization_id: item for item in civilizations}
    reforms: list[GovernmentReform] = []
    for event in events:
        changes = [
            item for item in event.consequences if item.kind is ConsequenceKind.GOVERNMENT_SET
        ]
        if event.kind is not EventKind.REFORM:
            if changes:
                raise ValueError("WG-REFORM-EVENT: government change outside reform")
            continue
        costs = [item for item in event.consequences if item.kind is ConsequenceKind.CURRENCY_DELTA]
        if len(changes) != 1 or len(costs) != 1:
            raise ValueError("WG-REFORM-SHAPE: reform must change once and pay once")
        change, cost = changes[0], costs[0]
        details = dict(change.details)
        try:
            pressure_ppm = int(details.get("pressure_ppm", ""))
        except ValueError as error:
            raise ValueError("WG-REFORM-PRESSURE: invalid pressure") from error
        reforms.append(
            GovernmentReform(
                stable_id("government_reform", seed, identity("event_id", event.event_id)),
                change.subject,
                change.value,
                change.target,
                details.get("pressure_kind", ""),
                pressure_ppm,
                -cost.amount,
                event.event_id,
                event.year,
            )
        )
    current: dict[str, str] = {}
    for reform in reforms:
        civilization = civilization_by_id.get(reform.civilization_id)
        event = next(item for item in events if item.event_id == reform.event_id)
        expected_prior = current.get(reform.civilization_id, reform.prior_government)
        if (
            civilization is None
            or reform.prior_government not in valid_governments
            or reform.new_government not in valid_governments
            or reform.prior_government == reform.new_government
            or reform.prior_government != expected_prior
            or reform.pressure_kind not in {"scarcity", "instability"}
            or not 0 <= reform.pressure_ppm <= 1_000_000
            or reform.currency_cost <= 0
            or reform.civilization_id not in event.participants
            or civilization.capital_site_id not in event.locations
        ):
            raise ValueError("WG-REFORM: invalid government transition")
        current[reform.civilization_id] = reform.new_government
    if any(civilization_by_id[key].government != value for key, value in current.items()):
        raise ValueError("WG-REFORM: projection disagrees with final government")
    if len({item.reform_id for item in reforms}) != len(reforms):
        raise ValueError("WG-REFORM: duplicate identity")
    return tuple(reforms)
