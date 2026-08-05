"""Deterministic twelve-tick scheduler and Phase 3 artifact publisher."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Any

from ...domain.run_spec import derive_seed
from ..artifacts import WorldArtifact, WorldArtifactRepository, canonical_json
from ..numeric import stable_id
from ...storage.fs import atomic_write_bytes
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from .magic import generate_supernatural
from .names import generate_identity
from .registries import validate_and_hash_registries
from .sites import found_sites
from .snapshots import StateSnapshot, make_snapshot
from .state import (Cohort, CivilizationState, DiplomaticRelation, EconomyState,
                    SettlementState, SimulationState)

PHYSICAL_KINDS = ("world_index", "plates", "terrain", "geology", "hydrology", "climate",
                  "soil", "biomes", "resources", "species", "ecology", "regions", "routes", "maps")


def _load_physical(root: Path) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    repository = WorldArtifactRepository(root / "artifacts")
    payloads: dict[str, Any] = {}
    artifact_ids: dict[str, str] = {}
    file_hashes: dict[str, str] = {}
    for kind in PHYSICAL_KINDS:
        path = root / "artifacts" / f"{kind}.json"
        file_hashes[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact = repository.load_verified(kind)
        payloads[kind] = artifact.payload
        artifact_ids[kind] = artifact.artifact_id
    return payloads, artifact_ids, file_hashes


def _genesis(seed: int, physical: dict[str, Any]) -> tuple[SimulationState, dict[str, object]]:
    count = min(int(physical["world_index"]["spec"]["civilization_count"]),
                len(physical["regions"]["regions"]))
    sites = found_sites(seed, physical, count)
    used: set[str] = set()
    civilizations: list[CivilizationState] = []
    cohorts: list[Cohort] = []
    settlements: list[SettlementState] = []
    languages: list[object] = []
    heraldry: dict[str, str] = {}
    governments = ("council", "monarchy", "clan_compact")
    for index, site in enumerate(sites):
        name, language, flag = generate_identity(seed, index, used)
        civilization_id = stable_id("civilization", seed, index)
        raw_capacity = int(physical["biomes"]["carrying_capacity"]["values"][site.cell])
        population = max(100, min(5_000, raw_capacity * 10 + 100))
        civilizations.append(CivilizationState(
            civilization_id, name, f"{name} river-and-stone culture",
            governments[index % len(governments)], language.language_id, site.site_id,
            ("agriculture", "masonry"), ("grain", "materials"), (site.region_id,), population,
            EconomyState(population * 18, population * 4, population * 3, 1_000_000),
        ))
        cohorts.append(Cohort(stable_id("cohort", seed, index, "adult"), civilization_id,
                              site.site_id, "adult", population))
        settlements.append(SettlementState(stable_id("settlement", seed, index), site.site_id,
                                           civilization_id, f"{name} Hold", 0,
                                           max(population, raw_capacity * 20 + 500), population))
        languages.append(language)
        heraldry[civilization_id] = flag
    relations = tuple(DiplomaticRelation(min(left.civilization_id, right.civilization_id),
                                         max(left.civilization_id, right.civilization_id), "rivalry", 350_000)
                      for left, right in combinations(civilizations, 2))
    laws, religions = generate_supernatural(seed, tuple(site.site_id for site in sites))
    state = SimulationState(0, 0, sites, tuple(settlements), tuple(civilizations),
                            tuple(cohorts), relations)
    identities: dict[str, object] = {"languages": tuple(languages), "heraldry": heraldry,
                                    "magic_laws": laws, "religions": religions}
    return state, identities


def _event(seed: int, year: int, month: int, sequence: int, kind: EventKind,
           participants: tuple[str, ...], locations: tuple[str, ...],
           consequences: tuple[Consequence, ...], summary: str,
           causes: tuple[str, ...] = ()) -> HistoryEvent:
    return HistoryEvent(stable_id("event", seed, year, month, sequence, kind.value), year, month,
                        sequence, kind, causes, participants, locations, consequences, summary)


def simulate_world(world: str | Path, history_years: int, output: str | Path) -> dict[str, Any]:
    if history_years < 0:
        raise ValueError("history years must be nonnegative")
    world_root, output_root = Path(world), Path(output)
    physical, physical_ids, physical_hashes_before = _load_physical(world_root)
    seed = int(physical["world_index"]["seed"])
    repository = WorldArtifactRepository(output_root / "artifacts")
    # Phase 3 is a self-contained immutable world repository. Preserve every
    # Phase 2 envelope byte-for-byte rather than reserializing physical facts.
    for physical_kind in PHYSICAL_KINDS:
        source = world_root / "artifacts" / f"{physical_kind}.json"
        atomic_write_bytes(repository.root / source.name, source.read_bytes())
    source_maps = world_root / "maps"
    if source_maps.is_dir():
        for source_map in sorted(source_maps.glob("*.png")):
            atomic_write_bytes(output_root / "maps" / source_map.name, source_map.read_bytes())
    # Monthly batches are derived output owned by this simulator. Prevent a
    # shorter rerun from retaining an invalid suffix from an earlier run.
    for stale_batch in repository.root.glob("history_[0-9][0-9][0-9][0-9]_*.json"):
        stale_batch.unlink()
    registry_hashes = validate_and_hash_registries()
    state, identities = _genesis(seed, physical)
    snapshots: list[StateSnapshot] = [make_snapshot(state)]
    ledger: list[HistoryEvent] = []
    previous_by_civ: dict[str, str] = {}
    sequence = 0
    site_by_id = {site.site_id: site for site in state.sites}
    capacity_by_civ = {
        civilization.civilization_id: max(500, int(physical["biomes"]["carrying_capacity"]["values"]
                                                    [site_by_id[civilization.capital_site_id].cell]) * 20 + 500)
        for civilization in state.civilizations
    }
    route_edges = {(route["start_region"], route["end_region"]) for route in physical["routes"]["routes"]}

    def route_connected(left_region: str, right_region: str) -> bool:
        frontier, visited = [left_region], {left_region}
        while frontier:
            current = frontier.pop(0)
            if current == right_region:
                return True
            neighbors = sorted(b if a == current else a for a, b in route_edges if a == current or b == current)
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor); frontier.append(neighbor)
        return False
    batch_dependency = tuple(physical_ids.values())
    producer = hashlib.sha256(canonical_json({"algorithm": "history-v1", "years": history_years,
                                              "registries": registry_hashes})).hexdigest()
    prefix_digest = hashlib.sha256(b"storyteller.history.prefix.v1").hexdigest()
    previous_batch_id = ""
    for year in range(1, history_years + 1):
        for month in range(1, 13):
            batch: list[HistoryEvent] = []
            for civilization in sorted(state.civilizations, key=lambda item: item.civilization_id):
                if not civilization.active:
                    continue
                capacity = capacity_by_civ[civilization.civilization_id]
                births = civilization.population * 2 // 1000
                outbreak = derive_seed(seed, "history.disease", year, month,
                                       civilization.civilization_id) % 97 == 0
                deaths = civilization.population // 1000 + (civilization.population // 200 if outbreak else 0)
                population_delta = min(max(0, capacity - civilization.population), births) - deaths
                production = max(1, civilization.population // 8)
                consumption = max(1, civilization.population // 10)
                next_grain = max(0, civilization.economy.grain + production - consumption)
                price = min(5_000_000, max(100_000, civilization.population * 1_000_000 // max(1, next_grain)))
                sequence += 1
                cause = previous_by_civ.get(civilization.civilization_id)
                event = _event(seed, year, month, sequence, EventKind.MONTHLY_DEMOGRAPHY,
                               (civilization.civilization_id,), (civilization.capital_site_id,),
                               (Consequence(ConsequenceKind.POPULATION_DELTA, civilization.civilization_id,
                                            population_delta),
                                Consequence(ConsequenceKind.GRAIN_DELTA, civilization.civilization_id,
                                            production - consumption),
                                Consequence(ConsequenceKind.MATERIAL_DELTA, civilization.civilization_id,
                                            max(1, civilization.population // 100)),
                                Consequence(ConsequenceKind.PRICE_SET, civilization.civilization_id, price)),
                               "Births, deaths, disease, harvest, production, spoilage, and consumption resolved.",
                               (cause,) if cause else ())
                state = apply_event(state, event)
                ledger.append(event); batch.append(event)
                previous_by_civ[civilization.civilization_id] = event.event_id
            active = sorted((c for c in state.civilizations if c.active), key=lambda item: item.civilization_id)
            if month == 12 and len(active) > 1:
                seller, buyer = max(active, key=lambda c: (c.economy.grain, c.civilization_id)), \
                                min(active, key=lambda c: (c.economy.grain, c.civilization_id))
                amount = min(100, seller.economy.grain // 20)
                seller_region = site_by_id[seller.capital_site_id].region_id
                buyer_region = site_by_id[buyer.capital_site_id].region_id
                if (seller.civilization_id != buyer.civilization_id and amount
                        and route_connected(seller_region, buyer_region)):
                    sequence += 1
                    trade = _event(seed, year, month, sequence, EventKind.TRADE,
                                   (seller.civilization_id, buyer.civilization_id),
                                   (seller.capital_site_id, buyer.capital_site_id),
                                   (Consequence(ConsequenceKind.GRAIN_DELTA, seller.civilization_id, -amount),
                                    Consequence(ConsequenceKind.GRAIN_DELTA, buyer.civilization_id, amount),
                                    Consequence(ConsequenceKind.CURRENCY_DELTA, seller.civilization_id, amount),
                                    Consequence(ConsequenceKind.CURRENCY_DELTA, buyer.civilization_id, -amount)),
                                   "A route-constrained annual grain exchange completed.",
                                   tuple(sorted({previous_by_civ[seller.civilization_id],
                                                 previous_by_civ[buyer.civilization_id]})))
                    state = apply_event(state, trade); ledger.append(trade); batch.append(trade)
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(bytes.fromhex(prior_prefix) + canonical_json(tuple(batch))).hexdigest()
            batch_artifact = WorldArtifact.build(f"history_{year:04d}_{month:02d}", {
                "events": tuple(batch), "previous_prefix": prior_prefix, "prefix_sha256": prefix_digest,
            }, depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                                                 producer_fingerprint=producer)
            repository.put(batch_artifact)
            previous_batch_id = batch_artifact.artifact_id
        annual_batch: list[HistoryEvent] = []
        if year % 5 == 0 and len(state.civilizations) > 1:
            ordered = sorted(state.civilizations, key=lambda c: (c.population, c.civilization_id))
            source_civ, target_civ = ordered[-1], ordered[0]
            migrants = min(25, source_civ.population // 100)
            if migrants:
                sequence += 1
                migration = _event(seed, year, 12, sequence, EventKind.MIGRATION,
                                   (source_civ.civilization_id, target_civ.civilization_id),
                                   (source_civ.capital_site_id, target_civ.capital_site_id),
                                   (Consequence(ConsequenceKind.POPULATION_DELTA, source_civ.civilization_id, -migrants),
                                    Consequence(ConsequenceKind.POPULATION_DELTA, target_civ.civilization_id, migrants)),
                                   "A conserved cohort migrated between settlements.",
                                   tuple(sorted({previous_by_civ[source_civ.civilization_id],
                                                 previous_by_civ[target_civ.civilization_id]})))
                state = apply_event(state, migration); ledger.append(migration)
                annual_batch.append(migration)
        if year % 25 == 0 and len(state.civilizations) > 1:
            left, right = sorted(state.civilizations, key=lambda c: c.civilization_id)[:2]
            relation = next(r for r in state.relations if r.left == left.civilization_id and r.right == right.civilization_id)
            transitions = {"neutral": ("rivalry", EventKind.DIPLOMACY),
                           "rivalry": ("alliance", EventKind.DIPLOMACY),
                           "alliance": ("war", EventKind.WAR),
                           "war": ("peace", EventKind.PEACE),
                           "peace": ("alliance", EventKind.DIPLOMACY)}
            new_status, diplomatic_kind = transitions[relation.status]
            sequence += 1
            consequences = [Consequence(ConsequenceKind.RELATION_SET, left.civilization_id,
                                        100_000 if new_status == "war" else
                                        700_000 if new_status == "alliance" else 500_000,
                                        right.civilization_id, new_status)]
            if new_status == "war" and right.territory:
                conquered = right.territory[-1]
                consequences.extend((
                    Consequence(ConsequenceKind.TERRITORY_TRANSFER, right.civilization_id, -1, value=conquered),
                    Consequence(ConsequenceKind.TERRITORY_TRANSFER, left.civilization_id, 1, value=conquered),
                    Consequence(ConsequenceKind.MATERIAL_DELTA, left.civilization_id, -min(100, left.economy.materials)),
                    Consequence(ConsequenceKind.MATERIAL_DELTA, right.civilization_id, -min(100, right.economy.materials)),
                ))
            diplomacy = _event(seed, year, 12, sequence, diplomatic_kind,
                               (left.civilization_id, right.civilization_id),
                               (left.capital_site_id, right.capital_site_id),
                               tuple(consequences),
                               f"The polities entered {new_status}.",
                               tuple(sorted({previous_by_civ[left.civilization_id],
                                             previous_by_civ[right.civilization_id]})))
            state = apply_event(state, diplomacy); ledger.append(diplomacy)
            annual_batch.append(diplomacy)
        if year % 200 == 0:
            actor = min((c for c in state.civilizations if c.active), key=lambda c: c.civilization_id)
            sequence += 1
            collapse = _event(seed, year, 12, sequence, EventKind.COLLAPSE,
                              (actor.civilization_id,), (actor.capital_site_id,),
                              (Consequence(ConsequenceKind.ACTIVE_SET, actor.civilization_id,
                                           value="inactive"),),
                              "Scarcity and institutional failure caused a polity collapse.",
                              (previous_by_civ[actor.civilization_id],))
            state = apply_event(state, collapse); ledger.append(collapse); annual_batch.append(collapse)
            previous_by_civ[actor.civilization_id] = collapse.event_id
        if year % 200 == 10:
            inactive = sorted((c for c in state.civilizations if not c.active), key=lambda c: c.civilization_id)
            if inactive:
                actor = inactive[0]
                sequence += 1
                recovery = _event(seed, year, 12, sequence, EventKind.RECOVERY,
                                  (actor.civilization_id,), (actor.capital_site_id,),
                                  (Consequence(ConsequenceKind.ACTIVE_SET, actor.civilization_id,
                                               value="active"),),
                                  "Local institutions restored the collapsed polity.",
                                  (previous_by_civ[actor.civilization_id],))
                state = apply_event(state, recovery); ledger.append(recovery); annual_batch.append(recovery)
                previous_by_civ[actor.civilization_id] = recovery.event_id
        proposal_schedule = ((20, EventKind.EXPLORATION, ConsequenceKind.CURRENCY_DELTA, -10),
                             (30, EventKind.SUCCESSION, ConsequenceKind.CURRENCY_DELTA, -5),
                             (40, EventKind.CONSTRUCTION, ConsequenceKind.MATERIAL_DELTA, -20),
                             (50, EventKind.TECHNOLOGY, ConsequenceKind.MATERIAL_DELTA, -15),
                             (75, EventKind.REFORM, ConsequenceKind.CURRENCY_DELTA, -5),
                             (100, EventKind.SCHISM, ConsequenceKind.CURRENCY_DELTA, -5))
        for interval, proposal_kind, consequence_kind, amount in proposal_schedule:
            if year % interval:
                continue
            actor = min((c for c in state.civilizations if c.active), key=lambda c: c.civilization_id)
            sequence += 1
            proposal = _event(seed, year, 12, sequence, proposal_kind,
                              (actor.civilization_id,), (actor.capital_site_id,),
                              (Consequence(consequence_kind, actor.civilization_id, amount),),
                              f"A deterministic {proposal_kind.value} proposal was supplied and resolved.",
                              (previous_by_civ[actor.civilization_id],))
            state = apply_event(state, proposal); ledger.append(proposal); annual_batch.append(proposal)
        if annual_batch:
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(bytes.fromhex(prior_prefix) + canonical_json(tuple(annual_batch))).hexdigest()
            annual_artifact = WorldArtifact.build(f"history_{year:04d}_12_final", {
                "events": tuple(annual_batch), "previous_prefix": prior_prefix,
                "prefix_sha256": prefix_digest,
            }, depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                                                   producer_fingerprint=producer)
            repository.put(annual_artifact)
            previous_batch_id = annual_artifact.artifact_id
        if year % 10 == 0 or year == history_years:
            snapshots.append(make_snapshot(state))
    # Avoid duplicate final snapshots by construction.
    snapshot_by_year = {snapshot.year: snapshot for snapshot in snapshots}
    snapshots = [snapshot_by_year[year] for year in sorted(snapshot_by_year)]
    dependencies = tuple(sorted(physical_ids.values()))
    refs = []
    for artifact_kind, payload in (("sites", state.sites), ("settlements", state.settlements),
                          ("civilizations", state.civilizations),
                          ("history", tuple(ledger)), ("snapshots", tuple(snapshots)),
                          ("registries", registry_hashes), ("identities", identities)):
        artifact = WorldArtifact.build(artifact_kind, payload, depends_on=dependencies,
                                       producer_fingerprint=producer)
        repository.put(artifact); refs.append(artifact)
    physical_after = {kind: hashlib.sha256((world_root / "artifacts" / f"{kind}.json").read_bytes()).hexdigest()
                      for kind in PHYSICAL_KINDS}
    if physical_after != physical_hashes_before:
        raise ValueError("WG-PHYSICAL-MUTATION: Phase 2 input changed during simulation")
    index = WorldArtifact.build("simulation_index", {
        "algorithm_version": 1, "seed": seed, "present_year": history_years,
        "physical_artifacts": physical_ids, "physical_file_hashes": physical_after,
        "registry_hashes": registry_hashes,
        "ledger_prefix_sha256": prefix_digest,
        "artifacts": {ref.kind: {"artifact_id": ref.artifact_id, "sha256": ref.sha256} for ref in refs},
        "event_count": len(ledger), "snapshot_years": [snapshot.year for snapshot in snapshots],
    }, depends_on=tuple(ref.artifact_id for ref in refs), producer_fingerprint=producer)
    repository.put(index)
    return {"simulation_index": index.artifact_id, "present_year": history_years,
            "events": len(ledger), "snapshots": len(snapshots), "civilizations": len(state.civilizations)}
