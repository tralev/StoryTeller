"""Closed event registry, consequences, and exactly-once state applier."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from enum import Enum

from ..artifacts import canonical_json
from .state import (
    DiplomaticRelation,
    EconomyLedgerEntry,
    InventoryStack,
    SettlementStatus,
    SimulationState,
    WorkshopState,
)

EVENT_ENVELOPE_VERSION = "storyteller.history-event.v1"
EVENT_ALGORITHM_VERSION = 1


def _event_state_hash(state: SimulationState, event: HistoryEvent) -> str:
    """Hash only state records addressable by this event's declared envelope."""
    ids = set(event.participants) | set(event.locations)
    ids.update(item.subject for item in event.consequences)
    ids.update(item.target for item in event.consequences if item.target)
    payload = {
        "year": state.year,
        "month": state.month,
        "causal_head": state.applied_events[-1:] if state.applied_events else (),
        "civilizations": tuple(asdict(item) for item in state.civilizations
                               if item.civilization_id in ids),
        "cohorts": tuple(asdict(item) for item in state.cohorts if item.cohort_id in ids),
        "settlements": tuple(asdict(item) for item in state.settlements
                             if item.settlement_id in ids or item.site_id in ids),
        "relations": tuple(asdict(item) for item in state.relations
                           if item.left in ids or item.right in ids),
        "resource_stocks": tuple(asdict(item) for item in state.resource_stocks
                                 if item.stock_id in ids),
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


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
    COMMISSION = "commission"
    AGEING = "ageing"
    DISASTER = "disaster"
    CRIME = "crime"
    RELATIONSHIP = "relationship"
    RELIGION = "religion"
    ARTIFACT_HISTORY = "artifact_history"
    MEGABEAST_MOVEMENT = "megabeast_movement"
    MEGABEAST_ENCOUNTER = "megabeast_encounter"
    MEGABEAST_HUNT = "megabeast_hunt"
    MEGABEAST_DEATH = "megabeast_death"
    PERSON_STATUS = "person_status"
    MEGABEAST_ORIGIN = "megabeast_origin"


class ConsequenceKind(str, Enum):
    POPULATION_DELTA = "population_delta"
    GRAIN_DELTA = "grain_delta"
    MATERIAL_DELTA = "material_delta"
    CURRENCY_DELTA = "currency_delta"
    PRICE_SET = "price_set"
    RELATION_SET = "relation_set"
    TERRITORY_TRANSFER = "territory_transfer"
    ACTIVE_SET = "active_set"
    RESOURCE_STOCK_DELTA = "resource_stock_delta"
    SETTLEMENT_BUILDING_ADD = "settlement_building_add"
    SETTLEMENT_WORKSHOP_ADD = "settlement_workshop_add"
    SETTLEMENT_STATUS_SET = "settlement_status_set"
    SETTLEMENT_INVENTORY_DELTA = "settlement_inventory_delta"
    ECONOMY_LEDGER_APPEND = "economy_ledger_append"
    COHORT_TRANSFER = "cohort_transfer"
    GENEALOGY_RELATION_ADD = "genealogy_relation_add"
    RELIGIOUS_PATRONAGE_ADD = "religious_patronage_add"
    RELIGIOUS_SCHISM_ADD = "religious_schism_add"
    OFFICEHOLDER_SET = "officeholder_set"
    INHERITANCE_TRANSFER = "inheritance_transfer"
    CAPABILITY_ADD = "capability_add"
    REGION_DISCOVERY_ADD = "region_discovery_add"
    GOVERNMENT_SET = "government_set"
    ARTIFACT_CREATE = "artifact_create"
    ARTIFACT_TRANSITION = "artifact_transition"
    MEGABEAST_TRANSITION = "megabeast_transition"
    PERSON_STATUS_SET = "person_status_set"


@dataclass(frozen=True)
class Consequence:
    kind: ConsequenceKind
    subject: str
    amount: int = 0
    target: str = ""
    value: str = ""
    details: tuple[tuple[str, str], ...] = ()


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
    envelope_version: str = ""
    algorithm_version: int = 0
    source_ids: tuple[str, ...] = ()
    before_state_sha256: str = ""
    after_state_sha256: str = ""


def ordered_events(events: tuple[HistoryEvent, ...]) -> tuple[HistoryEvent, ...]:
    return tuple(sorted(events, key=lambda event: (event.year, event.month, event.sequence, event.event_id)))


def apply_event(state: SimulationState, event: HistoryEvent) -> SimulationState:
    if event.event_id in state.applied_events:
        raise ValueError(f"WG-EVENT-DUPLICATE: {event.event_id}")
    if event.envelope_version and (
            event.envelope_version != EVENT_ENVELOPE_VERSION
            or event.algorithm_version != EVENT_ALGORITHM_VERSION
            or event.source_ids != tuple(sorted(set(event.source_ids)))
            or not event.source_ids
            or event.before_state_sha256 != _event_state_hash(state, event)):
        raise ValueError(f"WG-EVENT-ENVELOPE: invalid before-state envelope: {event.event_id}")
    known_events = set(state.applied_events)
    if any(cause not in known_events for cause in event.causes):
        raise ValueError(f"WG-EVENT-CAUSE: cause must reference an earlier applied event: {event.event_id}")
    civilizations = {civilization.civilization_id: civilization for civilization in state.civilizations}
    cohorts = {cohort.cohort_id: cohort for cohort in state.cohorts}
    settlements = {settlement.settlement_id: settlement for settlement in state.settlements}
    relations = {(relation.left, relation.right): relation for relation in state.relations}
    stocks = {stock.stock_id: stock for stock in state.resource_stocks}
    economy_ledger = list(state.economy_ledger)
    for operation_index, operation in enumerate(event.consequences):
        if operation.kind is ConsequenceKind.GOVERNMENT_SET:
            civilization = civilizations.get(operation.subject)
            if (civilization is None or operation.amount != 0 or not operation.target
                    or operation.target == civilization.government):
                raise ValueError(f"WG-REFORM-CONSEQUENCE: {event.event_id}")
            civilizations[operation.subject] = replace(
                civilization, government=operation.target,
            )
            continue
        if operation.kind is ConsequenceKind.REGION_DISCOVERY_ADD:
            if operation.amount != 0 or not operation.target or not operation.value:
                raise ValueError(f"WG-EXPLORATION-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.CAPABILITY_ADD:
            civilization = civilizations.get(operation.subject)
            if (civilization is None or operation.amount != 0 or not operation.target
                    or operation.target in civilization.capabilities):
                raise ValueError(f"WG-TECHNOLOGY-CONSEQUENCE: {event.event_id}")
            civilizations[operation.subject] = replace(
                civilization,
                capabilities=tuple(sorted(civilization.capabilities + (operation.target,))),
            )
            continue
        if operation.kind is ConsequenceKind.OFFICEHOLDER_SET:
            if operation.amount != 0 or not operation.target or not operation.value:
                raise ValueError(f"WG-SUCCESSION-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.INHERITANCE_TRANSFER:
            if (operation.amount != 0 or not operation.subject or not operation.target
                    or not operation.value or operation.subject == operation.target):
                raise ValueError(f"WG-INHERITANCE-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.ARTIFACT_CREATE:
            if (operation.amount != 0 or not operation.subject or not operation.target
                    or not operation.value):
                raise ValueError(f"WG-ARTIFACT-CREATE-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.ARTIFACT_TRANSITION:
            details = dict(operation.details)
            if (operation.amount != 0 or not operation.subject
                    or not details.get("transition") or not details.get("prior_event_id")
                    or not details.get("prior_status") or not details.get("new_status")
                    or not details.get("prior_site_id") or not details.get("new_site_id")):
                raise ValueError(f"WG-ARTIFACT-TRANSITION-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.MEGABEAST_TRANSITION:
            details = dict(operation.details)
            if (operation.amount != 0 or not operation.subject or not operation.target
                    or not operation.value or not details.get("transition")
                    or not details.get("prior_region_id")
                    or not details.get("prior_condition")):
                raise ValueError(f"WG-MEGABEAST-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.PERSON_STATUS_SET:
            details = dict(operation.details)
            if (operation.amount != 0 or operation.value not in {"living", "dead"}
                    or details.get("prior_status") not in {"living", "dead"}
                    or details.get("prior_status") == operation.value):
                raise ValueError(f"WG-PERSON-STATUS-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.RELIGIOUS_PATRONAGE_ADD:
            if operation.amount != 0 or not operation.target or not operation.value:
                raise ValueError(f"WG-RELIGIOUS-PATRONAGE-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.RELIGIOUS_SCHISM_ADD:
            if operation.amount != 0 or not operation.subject or not operation.target \
                    or not operation.value:
                raise ValueError(f"WG-RELIGIOUS-SCHISM-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.GENEALOGY_RELATION_ADD:
            if operation.amount != 0 or not operation.target or not operation.value:
                raise ValueError(f"WG-GENEALOGY-CONSEQUENCE: {event.event_id}")
            continue
        if operation.kind is ConsequenceKind.COHORT_TRANSFER:
            source = cohorts.get(operation.subject)
            target = cohorts.get(operation.target)
            if (source is None or target is None or operation.amount <= 0
                    or operation.amount > source.population
                    or source.civilization_id != target.civilization_id
                    or source.site_id != target.site_id):
                raise ValueError(f"WG-COHORT-TRANSFER: {event.event_id}")
            cohorts[source.cohort_id] = replace(source, population=source.population - operation.amount)
            cohorts[target.cohort_id] = replace(target, population=target.population + operation.amount)
            continue
        if operation.kind == ConsequenceKind.ECONOMY_LEDGER_APPEND:
            details = dict(operation.details)
            route_ids = tuple(filter(None, details.get("route_ids", "").split(",")))
            economy_ledger.append(EconomyLedgerEntry(
                f"{event.event_id}:{operation_index}", event.year, event.month, operation.value,
                operation.subject, operation.amount, operation.target, route_ids,
                int(details.get("transport_capacity", "0")),
            ))
            continue
        if operation.kind == ConsequenceKind.SETTLEMENT_INVENTORY_DELTA:
            settlement = settlements[operation.subject]
            inventory = {stack.material_id: stack for stack in settlement.inventory}
            current = inventory.get(operation.target, InventoryStack(operation.target, 0))
            inventory[operation.target] = replace(
                current, quantity=max(0, current.quantity + operation.amount),
            )
            settlements[operation.subject] = replace(
                settlement, inventory=tuple(inventory[key] for key in sorted(inventory)),
            )
            continue
        if operation.kind == ConsequenceKind.SETTLEMENT_BUILDING_ADD:
            settlement = settlements[operation.subject]
            settlements[operation.subject] = replace(
                settlement, buildings=tuple(sorted(settlement.buildings + (operation.value,))),
            )
            continue
        if operation.kind == ConsequenceKind.SETTLEMENT_WORKSHOP_ADD:
            settlement = settlements[operation.subject]
            parts = operation.value.split("|")
            if len(parts) != 6:
                raise ValueError(f"WG-SETTLEMENT-WORKSHOP: {operation.subject}")
            workshop = WorkshopState(parts[0], parts[1], parts[2], parts[3], parts[4], int(parts[5]))
            settlements[operation.subject] = replace(
                settlement, workshops=tuple(sorted(settlement.workshops + (workshop,),
                                                    key=lambda item: item.workshop_id)),
            )
            continue
        if operation.kind == ConsequenceKind.SETTLEMENT_STATUS_SET:
            settlement = settlements[operation.subject]
            status = SettlementStatus(operation.value)
            settlements[operation.subject] = replace(
                settlement, status=status,
                abandoned_year=event.year if status is SettlementStatus.ABANDONED else None,
            )
            continue
        if operation.kind == ConsequenceKind.RESOURCE_STOCK_DELTA:
            stock = stocks[operation.subject]
            stocks[operation.subject] = replace(
                stock, quantity_kg=max(0, min(stock.capacity_kg,
                                             stock.quantity_kg + operation.amount)),
            )
            continue
        if operation.kind in (ConsequenceKind.POPULATION_DELTA, ConsequenceKind.GRAIN_DELTA,
                              ConsequenceKind.MATERIAL_DELTA, ConsequenceKind.CURRENCY_DELTA,
                              ConsequenceKind.PRICE_SET, ConsequenceKind.TERRITORY_TRANSFER,
                              ConsequenceKind.ACTIVE_SET):
            civilization = civilizations[operation.subject]
            economy = civilization.economy
            if operation.kind is ConsequenceKind.ACTIVE_SET and operation.value not in {
                    "active", "inactive"}:
                raise ValueError(f"WG-POLITY-LIFECYCLE-CONSEQUENCE: {event.event_id}")
            if operation.kind == ConsequenceKind.POPULATION_DELTA:
                civilization = replace(civilization, population=max(0, civilization.population + operation.amount))
                age_order = ({"child": 0, "adult": 1, "elder": 2} if operation.amount >= 0
                             else {"elder": 0, "adult": 1, "child": 2})
                matching = sorted(
                    (key for key, cohort in cohorts.items()
                     if cohort.civilization_id == operation.subject),
                    key=lambda key: (age_order.get(cohorts[key].age_band, 3), key),
                )
                if operation.target:
                    matching = [operation.target] if operation.target in cohorts else []
                if matching:
                    cohort = cohorts[matching[0]]
                    if cohort.population + operation.amount < 0:
                        raise ValueError(f"WG-COHORT-POPULATION: {event.event_id}")
                    cohorts[matching[0]] = replace(cohort, population=cohort.population + operation.amount)
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
            if (operation.subject not in civilizations or operation.target not in civilizations
                    or operation.subject == operation.target
                    or operation.value not in {"neutral", "rivalry", "alliance", "war", "peace"}
                    or not 0 <= operation.amount <= 1_000_000):
                raise ValueError(f"WG-DIPLOMACY-CONSEQUENCE: {event.event_id}")
            pair = tuple(sorted((operation.subject, operation.target)))
            relations[(pair[0], pair[1])] = DiplomaticRelation(pair[0], pair[1], operation.value, operation.amount)
    result = replace(state, year=event.year, month=event.month,
                     civilizations=tuple(civilizations[key] for key in sorted(civilizations)),
                     settlements=tuple(settlements[key] for key in sorted(settlements)),
                     cohorts=tuple(cohorts[key] for key in sorted(cohorts)),
                     relations=tuple(relations[key] for key in sorted(relations)),
                     resource_stocks=tuple(stocks[key] for key in sorted(stocks)),
                     economy_ledger=tuple(economy_ledger),
                     applied_events=state.applied_events + (event.event_id,))
    if event.envelope_version and event.after_state_sha256 != _event_state_hash(result, event):
        raise ValueError(f"WG-EVENT-ENVELOPE: invalid after-state envelope: {event.event_id}")
    return result


def seal_event(state: SimulationState, event: HistoryEvent) -> HistoryEvent:
    """Freeze a replay-verifiable envelope around an event's declared deltas."""
    if event.envelope_version:
        raise ValueError(f"WG-EVENT-ENVELOPE: event already sealed: {event.event_id}")
    reference_target_kinds = {
        ConsequenceKind.RELATION_SET, ConsequenceKind.COHORT_TRANSFER,
        ConsequenceKind.GENEALOGY_RELATION_ADD, ConsequenceKind.RELIGIOUS_PATRONAGE_ADD,
        ConsequenceKind.RELIGIOUS_SCHISM_ADD, ConsequenceKind.OFFICEHOLDER_SET,
        ConsequenceKind.CAPABILITY_ADD, ConsequenceKind.REGION_DISCOVERY_ADD,
        ConsequenceKind.GOVERNMENT_SET, ConsequenceKind.ARTIFACT_CREATE,
        ConsequenceKind.ARTIFACT_TRANSITION, ConsequenceKind.MEGABEAST_TRANSITION,
        ConsequenceKind.PERSON_STATUS_SET,
    }
    references = list(event.participants + event.locations)
    references.extend(item.subject for item in event.consequences)
    references.extend(item.target for item in event.consequences
                      if item.target and item.kind in reference_target_kinds)
    references.extend(item.value for item in event.consequences
                      if item.value and item.kind is ConsequenceKind.TERRITORY_TRANSFER)
    references.extend(item.value for item in event.consequences
                      if item.value and item.kind is ConsequenceKind.ARTIFACT_CREATE)
    source_ids = tuple(sorted(set(references)))
    draft = replace(
        event, envelope_version=EVENT_ENVELOPE_VERSION,
        algorithm_version=EVENT_ALGORITHM_VERSION, source_ids=source_ids,
        before_state_sha256=_event_state_hash(state, event),
    )
    after = apply_event(state, replace(draft, envelope_version=""))
    return replace(draft, after_state_sha256=_event_state_hash(after, event))
