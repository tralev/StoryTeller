import ast
from dataclasses import replace
from pathlib import Path

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.scheduler import (_demographic_change, _monthly_economy,
                                               _crime_currency_loss, _crime_occurs,
                                               _disaster_losses, _disaster_occurs,
                                               _route_transport_plan, _stock_extraction)
from src.worldgen.simulation.economy import validate_economy_ledger
from src.worldgen.simulation.economy import (
    PRICE_EQUATION_VERSION, PRICE_MAX_PPM, PRICE_MIN_PPM, grain_price_ppm,
)
from src.worldgen.simulation.conservation import ConservationEntry, validate_conservation_ledger
from src.worldgen.simulation.replay import _event
from src.worldgen.simulation.state import EconomyLedgerEntry
from src.worldgen.simulation.state import ResourceStock
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from src.worldgen.simulation.legendary_artifacts import (
    ArtifactProvenance, LegendaryArtifact, validate_legendary_artifacts,
)
from src.worldgen.simulation.settlements import validate_settlements
from src.worldgen.simulation.state import SettlementStatus


def test_scheduler_has_no_raw_floor_division_operators():
    source = Path("src/worldgen/simulation/scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FloorDiv)
    ]


def test_monthly_demography_rounding_and_capacity_vectors():
    assert _demographic_change(100, 1_000, outbreak=False) == (0, 0, 0)
    assert _demographic_change(250, 1_000, outbreak=False) == (1, 0, 1)
    assert _demographic_change(500, 1_000, outbreak=False) == (1, 1, 0)
    assert _demographic_change(500, 500, outbreak=False) == (1, 1, -1)
    assert _demographic_change(500, 1_000, outbreak=True) == (1, 4, -3)


def test_monthly_economy_rounding_and_price_vectors():
    assert _monthly_economy(100, 1_800) == (13, 10, 1_803, 1, 100_000)
    assert _monthly_economy(1_000, 100) == (125, 100, 125, 10, 5_000_000)
    assert _monthly_economy(1, 0) == (1, 1, 0, 1, 1_000_000)


def test_disaster_trigger_and_losses_are_bounded_deterministic_and_hazard_driven():
    assert not _disaster_occurs(7, "civ-a", 1, 1, 0)
    assert _disaster_occurs(5, "civ-a", 1, 1, 900_000)
    assert _disaster_occurs(5, "civ-a", 1, 1, 900_000) == \
        _disaster_occurs(5, "civ-a", 1, 1, 900_000)
    assert _disaster_losses(1_000, 500, 0) == (0, 0)
    casualties, materials = _disaster_losses(1_000, 500, 1_000_000)
    assert (casualties, materials) == (10, 10)
    assert 0 <= casualties <= 1_000 and 0 <= materials <= 500
    with pytest.raises(ValueError, match="DISASTER-HAZARD"):
        _disaster_occurs(7, "civ-a", 1, 1, 1_000_001)


def test_crime_trigger_and_loss_are_bounded_deterministic_and_pressure_driven():
    assert not _crime_occurs(5, "civ-a", 1, 1, 0, 1_000_000)
    assert _crime_occurs(5, "civ-a", 1, 1, 1_000_000, 0) == \
        _crime_occurs(5, "civ-a", 1, 1, 1_000_000, 0)
    assert _crime_currency_loss(0, 1_000_000) == 0
    assert _crime_currency_loss(10_000, 1_000_000) == 50
    with pytest.raises(ValueError, match="CRIME-PRESSURE"):
        _crime_occurs(5, "civ-a", 1, 1, -1, 0)


def test_integer_price_equation_has_frozen_bounds_and_vectors():
    assert PRICE_EQUATION_VERSION == "grain-scarcity-v1"
    assert (PRICE_MIN_PPM, PRICE_MAX_PPM) == (100_000, 5_000_000)
    assert grain_price_ppm(0, 0) == PRICE_MIN_PPM
    assert grain_price_ppm(100, 1_000) == PRICE_MIN_PPM
    assert grain_price_ppm(100, 25) == 4_000_000
    assert grain_price_ppm(100, 0) == PRICE_MAX_PPM


def test_finite_extraction_and_renewable_capacity_rules():
    stocks = (
        ResourceStock("finite", "iron", "r1", False, 7, 7, 0),
        ResourceStock("renewable", "biomass", "r1", True, 10, 4, 3),
    )
    assert _stock_extraction(stocks, ("r1",), 9) == (("finite", 7), ("renewable", 2))
    assert _stock_extraction(stocks, ("r2",), 9) == ()


def test_transport_plan_uses_deterministic_path_bottleneck_and_maintenance():
    routes = (
        {"route_id": "route-b", "start_region": "b", "end_region": "c",
         "traversable_seasons": (True,) * 4, "seasonal_capacity": (7,) * 4,
         "annual_maintenance": 3},
        {"route_id": "route-a", "start_region": "a", "end_region": "b",
         "traversable_seasons": (True,) * 4, "seasonal_capacity": (11,) * 4,
         "annual_maintenance": 2},
    )
    assert _route_transport_plan(routes, "a", "c", 3) == (("route-a", "route-b"), 7, 5)
    blocked = ({**routes[1], "traversable_seasons": (True, True, True, False)}, routes[0])
    assert _route_transport_plan(blocked, "a", "c", 3) is None


def test_history_and_snapshot_artifact_golden_vectors(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    assert (
        repository.load_verified("history").sha256,
        repository.load_verified("snapshots").sha256,
    ) == (
        "88fdc45d57328f7ff37dea6c3e98a8877685428e104b14595b57b2331ed3db25",
        "304d2161ca0fc16929e329bb0c7bb155abc1ebce3b436a8eef3eb71198cbdddf",
    )


def test_population_cohorts_and_goods_remain_conserved_and_nonnegative(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    for snapshot in snapshots:
        state = snapshot["state"]
        cohort_totals = {}
        for cohort in state["cohorts"]:
            cohort_totals[cohort["civilization_id"]] = cohort_totals.get(cohort["civilization_id"], 0) + cohort["population"]
        assert all(civilization["population"] == cohort_totals[civilization["civilization_id"]]
                   for civilization in state["civilizations"])
        assert all(civilization["population"] >= 0 and civilization["economy"]["grain"] >= 0
                   and civilization["economy"]["currency"] >= 0
                   for civilization in state["civilizations"])
        assert all(0 <= stock["quantity_kg"] <= stock["capacity_kg"]
                   for stock in state["resource_stocks"])


def test_ageing_events_transfer_cohorts_without_changing_population(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    history = repository.load_verified("history").payload
    ageing = [event for event in history if event["kind"] == "ageing"]
    assert ageing
    assert all(event["month"] == 12 for event in ageing)
    assert all({item["kind"] for item in event["consequences"]} == {"cohort_transfer"}
               for event in ageing)
    snapshots = repository.load_verified("snapshots").payload
    assert all({cohort["age_band"] for cohort in snapshot["state"]["cohorts"]}
               == {"child", "adult", "elder"} for snapshot in snapshots)
    for snapshot in snapshots:
        state = snapshot["state"]
        totals = {}
        for cohort in state["cohorts"]:
            totals[cohort["civilization_id"]] = totals.get(cohort["civilization_id"], 0) \
                + cohort["population"]
        assert totals == {civilization["civilization_id"]: civilization["population"]
                          for civilization in state["civilizations"]}


def test_ageing_transfer_rejects_overdraw_and_cross_civilization(simulated_world):
    _, historical, _ = simulated_world
    snapshot = WorldArtifactRepository(historical / "artifacts").load_verified(
        "snapshots"
    ).payload[0]
    from src.worldgen.simulation.replay import _state
    state = _state(snapshot["state"])
    source = next(cohort for cohort in state.cohorts if cohort.age_band == "child")
    same_civ_target = next(cohort for cohort in state.cohorts
                           if cohort.civilization_id == source.civilization_id
                           and cohort.age_band == "adult")
    other_target = next(cohort for cohort in state.cohorts
                        if cohort.civilization_id != source.civilization_id)
    for target, amount in ((same_civ_target, source.population + 1), (other_target, 1)):
        event = HistoryEvent(
            f"ageing-invalid-{amount}-{target.cohort_id}", 1, 12, 1, EventKind.AGEING, (),
            (source.civilization_id,), (source.site_id,),
            (Consequence(ConsequenceKind.COHORT_TRANSFER, source.cohort_id, amount,
                         target=target.cohort_id),), "invalid ageing",
        )
        with pytest.raises(ValueError, match="COHORT-TRANSFER"):
            apply_event(state, event)


def test_disasters_cite_climate_and_apply_exact_bounded_damage(simulated_world):
    physical, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    climate_id = WorldArtifactRepository(physical / "artifacts").load_verified(
        "climate"
    ).artifact_id
    disasters = [event for event in repository.load_verified("history").payload
                 if event["kind"] == "disaster"]
    assert disasters
    for event in disasters:
        assert event["participants"] and event["locations"] and event["causes"]
        assert all(dict(consequence["details"])["source_id"] == climate_id
                   for consequence in event["consequences"])
        assert all(0 <= int(dict(consequence["details"])["hazard_ppm"]) <= 1_000_000
                   for consequence in event["consequences"])
        population_loss = -sum(item["amount"] for item in event["consequences"]
                               if item["kind"] == "population_delta")
        civilization_material_loss = -sum(
            item["amount"] for item in event["consequences"]
            if item["kind"] == "material_delta")
        settlement_material_loss = -sum(
            item["amount"] for item in event["consequences"]
            if item["kind"] == "settlement_inventory_delta")
        assert population_loss >= 0
        assert civilization_material_loss == settlement_material_loss >= 0


def test_crime_events_have_actor_victim_pressure_resolution_and_exact_loss(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    crimes = [event for event in repository.load_verified("history").payload
              if event["kind"] == "crime"]
    assert crimes
    for event in crimes:
        assert len(event["participants"]) == 2 and event["participants"][0] != \
            event["participants"][1]
        assert len(event["locations"]) == 1 and event["causes"]
        assert len(event["consequences"]) == 1
        consequence = event["consequences"][0]
        details = dict(consequence["details"])
        assert consequence["kind"] == "currency_delta" and consequence["amount"] < 0
        assert consequence["value"] == "institutional_resolution_cost"
        assert details["actor_cohort_id"] == event["participants"][0]
        assert details["victim_cohort_id"] == event["participants"][1]
        assert details["resolution"] == "restitution_and_public_censure"
        assert 0 <= int(details["scarcity_ppm"]) <= 1_000_000
        assert 0 <= int(details["stability_ppm"]) <= 1_000_000
        assert details["government_registry_id"] in {"council", "monarchy", "clan_compact"}


def test_trade_and_migration_are_balanced(simulated_world):
    _, historical, _ = simulated_world
    history = WorldArtifactRepository(historical / "artifacts").load_verified("history").payload
    for event in history:
        if event["kind"] == "trade":
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "grain_delta") == 0
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "currency_delta") == 0
        if event["kind"] == "migration":
            assert sum(c["amount"] for c in event["consequences"] if c["kind"] == "population_delta") == 0


def test_economy_ledger_covers_capacity_scarcity_tax_maintenance_and_resources(simulated_world):
    _, historical, _ = simulated_world
    payload = WorldArtifactRepository(historical / "artifacts").load_verified("economy").payload
    activity = payload["activity"]
    kinds = {entry["kind"] for entry in activity}
    assert {"scarcity_price", "tax_assessment", "route_maintenance",
            "resource_depletion", "resource_recovery"} <= kinds
    trades = [entry for entry in activity if entry["kind"] == "trade"]
    assert trades
    assert all(entry["route_ids"] and 0 < entry["amount"] <= entry["transport_capacity"]
               for entry in trades)
    typed = tuple(EconomyLedgerEntry(
        entry["event_id"], entry["year"], entry["month"], entry["kind"],
        entry["subject_id"], entry["amount"], entry["material_id"],
        tuple(entry["route_ids"]), entry["transport_capacity"],
    ) for entry in activity)
    validate_economy_ledger(typed)


def test_conservation_ledger_covers_every_quantity_change_and_balances_transfers(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    economy = repository.load_verified("economy").payload
    history = tuple(_event(item) for item in repository.load_verified("history").payload)
    conservation = tuple(ConservationEntry(
        entry["entry_id"], entry["event_id"], entry["account"], entry["subject_id"],
        entry["delta"], entry["classification"],
    ) for entry in economy["conservation"])
    validate_conservation_ledger(history, conservation)
    assert {entry.classification for entry in conservation} == {"source", "sink", "transfer"}
    assert {entry.account for entry in conservation} == {
        "people", "civilization_goods", "currency", "resource_goods", "settlement_goods",
    }
    assert economy["price_equation"] == {
        "version": PRICE_EQUATION_VERSION,
        "minimum_ppm": PRICE_MIN_PPM,
        "maximum_ppm": PRICE_MAX_PPM,
    }


def test_material_creation_is_backed_by_stock_depletion(simulated_world):
    _, historical, _ = simulated_world
    history = WorldArtifactRepository(historical / "artifacts").load_verified("history").payload
    for event in history:
        materials = sum(c["amount"] for c in event["consequences"]
                        if c["kind"] == "material_delta" and c["amount"] > 0)
        extracted = -sum(c["amount"] for c in event["consequences"]
                         if c["kind"] == "resource_stock_delta" and c["amount"] < 0)
        assert materials == extracted


def test_legendary_artifacts_only_follow_successful_commissions_with_full_provenance(
        simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    artifacts = repository.load_verified("legendary_artifacts").payload
    history = repository.load_verified("history").payload
    peoples = repository.load_verified("peoples").payload
    settlements = repository.load_verified("settlements").payload
    civilizations = repository.load_verified("civilizations").payload
    assert len(artifacts) == len([event for event in history if event["kind"] == "commission"]) == 1
    artifact = artifacts[0]
    event = next(event for event in history
                 if event["event_id"] == artifact["provenance"]["creation_event_id"])
    assert event["kind"] == "commission"
    assert any(consequence["amount"] < 0 and consequence["details"]
               for consequence in event["consequences"])
    assert set(artifact["provenance"]["source_ids"]) == {
        event["event_id"], artifact["creator_id"], artifact["culture_id"],
        artifact["material_id"], artifact["workshop_id"], artifact["site_id"],
    }
    assert artifact["objective_properties"] and artifact["attributed_meaning"]
    assert artifact["meaning_attributed_to"] == artifact["culture_id"]
    assert artifact["creator_id"] in {person["person_id"] for person in peoples["people"]}
    assert artifact["workshop_id"] in {
        workshop["workshop_id"] for settlement in settlements for workshop in settlement["workshops"]
    }
    assert artifact["culture_id"] in {item["civilization_id"] for item in civilizations}


def test_legendary_artifact_validator_rejects_forged_creation_provenance(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    from src.worldgen.simulation.replay import _event, _state
    event_data = repository.load_verified("history").payload
    events = tuple(_event(item) for item in event_data)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    peoples_payload = repository.load_verified("peoples").payload["people"]
    from src.worldgen.simulation.relationships import SocialAnchor
    people = tuple(SocialAnchor(**item) for item in peoples_payload)
    payload = repository.load_verified("legendary_artifacts").payload[0]
    provenance = ArtifactProvenance(**payload["provenance"])
    artifact = LegendaryArtifact(
        payload["artifact_id"], payload["name"], payload["creator_id"], payload["culture_id"],
        payload["material_id"], payload["workshop_id"], payload["site_id"],
        tuple(tuple(item) for item in payload["objective_properties"]),
        payload["attributed_meaning"], payload["meaning_attributed_to"], provenance,
    )
    forged = ArtifactProvenance("event_missing", provenance.creation_year,
                                provenance.creation_month, provenance.creation_sequence,
                                provenance.source_ids)
    with pytest.raises(ValueError, match="LEGENDARY-PROVENANCE"):
        validate_legendary_artifacts((replace(artifact, provenance=forged),), events, people,
                                     state.civilizations, state.settlements)


def test_settlement_lifecycle_land_use_workshops_and_inventory_are_retained(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    settlements = repository.load_verified("settlements").payload
    assert all(settlement["status"] == "inhabited" and settlement["founded_year"] == 0
               for settlement in settlements)
    assert all(settlement["land_use"] and settlement["buildings"]
               and settlement["workshops"] and settlement["inventory"]
               for settlement in settlements)
    assert all(workshop["recipe_id"] == "food" and workshop["input_material"] == "grain"
               and workshop["output_material"] == "food"
               for settlement in settlements for workshop in settlement["workshops"])
    assert all(stack["quantity"] >= 0 for settlement in settlements
               for stack in settlement["inventory"])
    history = repository.load_verified("history").payload
    construction = next(event for event in history if event["kind"] == "construction")
    assert {item["kind"] for item in construction["consequences"]} >= {
        "material_delta", "settlement_building_add", "settlement_workshop_add",
    }
    monthly = next(event for event in history if event["kind"] == "monthly_demography")
    inventory_changes = [item for item in monthly["consequences"]
                         if item["kind"] == "settlement_inventory_delta"]
    assert {item["target"] for item in inventory_changes} == {"grain", "food", "materials"}
    assert sum(item["amount"] for item in inventory_changes if item["target"] == "grain") == 0


def test_abandonment_and_recovery_preserve_site_and_settlement_identity(simulated_world):
    _, historical, _ = simulated_world
    snapshot = WorldArtifactRepository(historical / "artifacts").load_verified(
        "snapshots"
    ).payload[0]["state"]
    from src.worldgen.simulation.replay import _state
    state = _state(snapshot)
    settlement = state.settlements[0]
    abandoned = HistoryEvent(
        "event-abandon", 60, 1, 1, EventKind.COLLAPSE, (),
        (settlement.civilization_id,), (settlement.site_id,),
        (Consequence(ConsequenceKind.SETTLEMENT_STATUS_SET, settlement.settlement_id,
                     value=SettlementStatus.ABANDONED.value),), "abandoned",
    )
    after_state = apply_event(state, abandoned)
    after = next(item for item in after_state.settlements
                 if item.settlement_id == settlement.settlement_id)
    assert (after.settlement_id, after.site_id) == (settlement.settlement_id, settlement.site_id)
    assert after.status is SettlementStatus.ABANDONED and after.abandoned_year == 60
    recovered = HistoryEvent(
        "event-recover", 61, 1, 2, EventKind.RECOVERY, (abandoned.event_id,),
        (settlement.civilization_id,), (settlement.site_id,),
        (Consequence(ConsequenceKind.SETTLEMENT_STATUS_SET, settlement.settlement_id,
                     value=SettlementStatus.INHABITED.value),), "recovered",
    )
    final_state = apply_event(after_state, recovered)
    final = next(item for item in final_state.settlements
                 if item.settlement_id == settlement.settlement_id)
    assert (final.settlement_id, final.site_id) == (settlement.settlement_id, settlement.site_id)
    assert final.status is SettlementStatus.INHABITED and final.abandoned_year is None
    validate_settlements((final,))
