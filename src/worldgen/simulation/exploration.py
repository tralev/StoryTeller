"""Route-bounded exploration discoveries projected from accepted events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..numeric import identity, stable_id
from .events import ConsequenceKind, EventKind, HistoryEvent
from .state import CivilizationState, SettlementState


@dataclass(frozen=True)
class ExplorationDiscovery:
    discovery_id: str
    civilization_id: str
    settlement_id: str
    origin_region_id: str
    destination_region_id: str
    route_ids: tuple[str, ...]
    currency_cost: int
    event_id: str
    year: int


def project_exploration_discoveries(
    seed: int,
    events: tuple[HistoryEvent, ...],
    civilizations: tuple[CivilizationState, ...],
    settlements: tuple[SettlementState, ...],
    region_ids: tuple[str, ...],
    routes: tuple[Mapping[str, object], ...],
) -> tuple[ExplorationDiscovery, ...]:
    """Validate physical route continuity and retain discoveries."""
    civilization_by_id = {item.civilization_id: item for item in civilizations}
    settlement_by_id = {item.settlement_id: item for item in settlements}
    route_by_id = {str(item["route_id"]): item for item in routes}
    known_regions = set(region_ids)
    # The projector receives the final simulation state, while an expedition must
    # be judged against ownership at the instant its event was accepted. Rewind
    # the event-sourced territory transfers once, then replay them alongside the
    # validation pass. This prevents a later conquest of a discovered region (or
    # loss of its origin) from retroactively invalidating valid history.
    ownership = {
        civilization.civilization_id: set(civilization.territory) for civilization in civilizations
    }
    ordered = tuple(
        sorted(
            events,
            key=lambda item: (
                item.year,
                item.month,
                item.sequence,
                item.event_id,
            ),
        )
    )
    for event in reversed(ordered):
        for operation in reversed(event.consequences):
            if operation.kind is not ConsequenceKind.TERRITORY_TRANSFER:
                continue
            territory = ownership.setdefault(operation.subject, set())
            if operation.amount < 0:
                territory.add(operation.value)
            else:
                territory.discard(operation.value)
    ownership_at_event: dict[str, dict[str, frozenset[str]]] = {}
    for event in ordered:
        ownership_at_event[event.event_id] = {
            civilization_id: frozenset(territory)
            for civilization_id, territory in ownership.items()
        }
        for operation in event.consequences:
            if operation.kind is not ConsequenceKind.TERRITORY_TRANSFER:
                continue
            territory = ownership.setdefault(operation.subject, set())
            if operation.amount < 0:
                territory.discard(operation.value)
            else:
                territory.add(operation.value)
    discoveries: list[ExplorationDiscovery] = []
    for event in events:
        additions = [
            item for item in event.consequences if item.kind is ConsequenceKind.REGION_DISCOVERY_ADD
        ]
        if event.kind is not EventKind.EXPLORATION:
            if additions:
                raise ValueError("WG-EXPLORATION-EVENT: discovery outside expedition")
            continue
        costs = [item for item in event.consequences if item.kind is ConsequenceKind.CURRENCY_DELTA]
        if len(additions) != 1 or len(costs) != 1:
            raise ValueError("WG-EXPLORATION-SHAPE: expedition must discover and pay once")
        addition, cost = additions[0], costs[0]
        details = dict(addition.details)
        discoveries.append(
            ExplorationDiscovery(
                stable_id("exploration_discovery", seed, identity("event_id", event.event_id)),
                addition.subject,
                addition.value,
                details.get("origin_region_id", ""),
                addition.target,
                tuple(filter(None, details.get("route_ids", "").split(","))),
                -cost.amount,
                event.event_id,
                event.year,
            )
        )
    seen: set[tuple[str, str]] = set()
    for discovery in discoveries:
        civilization = civilization_by_id.get(discovery.civilization_id)
        settlement = settlement_by_id.get(discovery.settlement_id)
        event = next(item for item in events if item.event_id == discovery.event_id)
        event_ownership = ownership_at_event[event.event_id]
        actor_territory = event_ownership.get(discovery.civilization_id, frozenset())
        owned = {region for territory in event_ownership.values() for region in territory}
        current = discovery.origin_region_id
        valid_path = bool(discovery.route_ids)
        for route_id in discovery.route_ids:
            route = route_by_id.get(route_id)
            if route is None:
                valid_path = False
                break
            endpoints = (str(route["start_region"]), str(route["end_region"]))
            traversable = route.get("traversable_seasons")
            if (
                current not in endpoints
                or not isinstance(traversable, Sequence)
                or len(traversable) != 4
                or not traversable[3]
            ):
                valid_path = False
                break
            current = endpoints[1] if endpoints[0] == current else endpoints[0]
        key = (discovery.civilization_id, discovery.destination_region_id)
        if (
            civilization is None
            or settlement is None
            or settlement.civilization_id != discovery.civilization_id
            or discovery.origin_region_id not in actor_territory
            or discovery.destination_region_id not in known_regions
            or discovery.destination_region_id in owned
            or current != discovery.destination_region_id
            or not valid_path
            or discovery.currency_cost <= 0
            or key in seen
            or discovery.civilization_id not in event.participants
            or settlement.site_id not in event.locations
        ):
            raise ValueError("WG-EXPLORATION: invalid route, destination, or duplicate")
        seen.add(key)
    return tuple(discoveries)
