"""Closed event registry, consequences, and exactly-once state applier."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .state import DiplomaticRelation, SimulationState


class EventKind(str, Enum):
    MONTHLY_DEMOGRAPHY = "monthly_demography"
    PRODUCTION = "production"
    CONSUMPTION = "consumption"
    TRADE = "trade"
    MIGRATION = "migration"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    PEACE = "peace"
    CONQUEST = "conquest"
    COLLAPSE = "collapse"
    RECOVERY = "recovery"
    TECHNOLOGY = "technology"
    REFORM = "reform"
    SCHISM = "schism"
    SUCCESSION = "succession"
    CONSTRUCTION = "construction"
    EXPLORATION = "exploration"


class ConsequenceKind(str, Enum):
    POPULATION_DELTA = "population_delta"
    GRAIN_DELTA = "grain_delta"
    MATERIAL_DELTA = "material_delta"
    CURRENCY_DELTA = "currency_delta"
    PRICE_SET = "price_set"
    RELATION_SET = "relation_set"
    TERRITORY_TRANSFER = "territory_transfer"
    ACTIVE_SET = "active_set"


@dataclass(frozen=True)
class Consequence:
    kind: ConsequenceKind
    subject: str
    amount: int = 0
    target: str = ""
    value: str = ""


@dataclass(frozen=True)
class HistoryEvent:
    event_id: str
    year: int
    month: int
    sequence: int
    kind: EventKind
    causes: tuple[str, ...]
    participants: tuple[str, ...]
    locations: tuple[str, ...]
    consequences: tuple[Consequence, ...]
    summary: str


def ordered_events(events: tuple[HistoryEvent, ...]) -> tuple[HistoryEvent, ...]:
    return tuple(sorted(events, key=lambda event: (event.year, event.month, event.sequence, event.event_id)))


def apply_event(state: SimulationState, event: HistoryEvent) -> SimulationState:
    if event.event_id in state.applied_events:
        raise ValueError(f"WG-EVENT-DUPLICATE: {event.event_id}")
    known_events = set(state.applied_events)
    if any(cause not in known_events for cause in event.causes):
        raise ValueError(f"WG-EVENT-CAUSE: cause must reference an earlier applied event: {event.event_id}")
    civilizations = {civilization.civilization_id: civilization for civilization in state.civilizations}
    cohorts = {cohort.cohort_id: cohort for cohort in state.cohorts}
    settlements = {settlement.settlement_id: settlement for settlement in state.settlements}
    relations = {(relation.left, relation.right): relation for relation in state.relations}
    for operation in event.consequences:
        if operation.kind in (ConsequenceKind.POPULATION_DELTA, ConsequenceKind.GRAIN_DELTA,
                              ConsequenceKind.MATERIAL_DELTA, ConsequenceKind.CURRENCY_DELTA,
                              ConsequenceKind.PRICE_SET, ConsequenceKind.TERRITORY_TRANSFER,
                              ConsequenceKind.ACTIVE_SET):
            civilization = civilizations[operation.subject]
            economy = civilization.economy
            if operation.kind == ConsequenceKind.POPULATION_DELTA:
                civilization = replace(civilization, population=max(0, civilization.population + operation.amount))
                matching = sorted(key for key, cohort in cohorts.items()
                                  if cohort.civilization_id == operation.subject)
                if matching:
                    cohort = cohorts[matching[0]]
                    cohorts[matching[0]] = replace(cohort, population=max(0, cohort.population + operation.amount))
                settlement_keys = sorted(key for key, settlement in settlements.items()
                                         if settlement.civilization_id == operation.subject)
                if settlement_keys:
                    settlement = settlements[settlement_keys[0]]
                    settlements[settlement_keys[0]] = replace(
                        settlement, population=max(0, settlement.population + operation.amount),
                    )
            elif operation.kind == ConsequenceKind.GRAIN_DELTA:
                economy = replace(economy, grain=max(0, economy.grain + operation.amount))
                civilization = replace(civilization, economy=economy)
            elif operation.kind == ConsequenceKind.MATERIAL_DELTA:
                economy = replace(economy, materials=max(0, economy.materials + operation.amount))
                civilization = replace(civilization, economy=economy)
            elif operation.kind == ConsequenceKind.CURRENCY_DELTA:
                economy = replace(economy, currency=max(0, economy.currency + operation.amount))
                civilization = replace(civilization, economy=economy)
            elif operation.kind == ConsequenceKind.PRICE_SET:
                economy = replace(economy, price_grain_ppm=max(1, operation.amount))
                civilization = replace(civilization, economy=economy)
            elif operation.kind == ConsequenceKind.TERRITORY_TRANSFER:
                territory = set(civilization.territory)
                if operation.amount < 0:
                    territory.discard(operation.value)
                else:
                    territory.add(operation.value)
                civilization = replace(civilization, territory=tuple(sorted(territory)))
            else:
                civilization = replace(civilization, active=operation.value == "active")
            civilizations[operation.subject] = civilization
        elif operation.kind == ConsequenceKind.RELATION_SET:
            pair = tuple(sorted((operation.subject, operation.target)))
            relations[(pair[0], pair[1])] = DiplomaticRelation(pair[0], pair[1], operation.value, operation.amount)
    return replace(state, year=event.year, month=event.month,
                   civilizations=tuple(civilizations[key] for key in sorted(civilizations)),
                   settlements=tuple(settlements[key] for key in sorted(settlements)),
                   cohorts=tuple(cohorts[key] for key in sorted(cohorts)),
                   relations=tuple(relations[key] for key in sorted(relations)),
                   applied_events=state.applied_events + (event.event_id,))
