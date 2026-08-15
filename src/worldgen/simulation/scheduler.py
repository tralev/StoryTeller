"""Deterministic twelve-tick scheduler and Phase 3 artifact publisher."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from ...domain.run_spec import derive_seed
from ..artifacts import WorldArtifact, WorldArtifactRepository, canonical_json, freeze_canonical
from ..hydrology_reader import VerifiedHydrologyReader
from ..biome_reader import VerifiedBiomeReader
from ..climate_reader import VerifiedClimateReader
from ..resource_reader import VerifiedResourceReader
from ..region_reader import VerifiedRegionReader
from ..terrain_reader import VerifiedTerrainReader
from ..numeric import div_floor_exact, div_round_half_up, identity, stable_id
from ...storage.fs import atomic_write_bytes
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event
from .conservation import build_conservation_ledger, validate_conservation_ledger
from .construction import project_construction
from .cosmology import generate_cosmology
from .economy import (PRICE_EQUATION_VERSION, PRICE_MAX_PPM, PRICE_MIN_PPM,
                      grain_price_ppm, validate_economy_ledger)
from .diplomacy import project_diplomatic_transitions
from .exploration import project_exploration_discoveries
from .magic import Religion, ReligiousInstitution, generate_supernatural
from .language_evolution import evolve_language
from .legendary_artifacts import generate_legendary_artifacts
from .heraldry import VectorHeraldry
from .history_clock import build_history_clock
from .genealogy import genesis_genealogy, project_genealogy
from .religious_patronage import project_religious_patronage
from .religious_schisms import project_religious_schisms
from .succession import project_successions
from .technology import project_technology_discoveries
from .names import CulturePressure, LanguageIdentity, generate_identity
from .polity_lifecycle import project_polity_lifecycle
from .registries import simulation_stage_fingerprint, validate_and_hash_registries
from .registries import simulation_registry_entries
from .reforms import project_government_reforms
from .relationships import generate_relationships
from .sites import found_sites, validate_site_lifecycle
from .settlements import validate_settlements
from .snapshots import StateSnapshot, make_snapshot
from .state import (Cohort, CivilizationState, DiplomaticRelation, EconomyState,
                    InventoryStack, ResourceStock, SettlementState, SettlementStatus,
                    SimulationState, WorkshopState)

PHYSICAL_KINDS = ("world_index", "plates", "terrain", "terrain_grid_catalog",
                  "geology", "geology_grid_catalog", "hydrology", "hydrology_grid_catalog", "climate",
                  "climate_grid_catalog",
                  "soil", "soil_grid_catalog", "biomes", "biome_grid_catalog", "resources",
                  "resource_grid_catalog", "species",
                  "ecology", "regions", "region_grid_catalog", "routes", "spatial_index",
                  "reference_index", "map_layers", "maps",
                  "validation_report")


def _demographic_change(
    population: int, capacity: int, *, outbreak: bool,
) -> tuple[int, int, int]:
    """Return births, deaths, and bounded population delta for one month."""
    births = div_round_half_up(population * 2, 1_000)
    deaths = div_round_half_up(population, 1_000)
    if outbreak:
        deaths += div_round_half_up(population, 200)
    delta = min(max(0, capacity - population), births) - deaths
    return births, deaths, delta


def _monthly_economy(
    population: int, grain: int,
) -> tuple[int, int, int, int, int]:
    """Return production, consumption, next grain, materials, and price."""
    production = max(1, div_round_half_up(population, 8))
    consumption = max(1, div_round_half_up(population, 10))
    next_grain = max(0, grain + production - consumption)
    materials = max(1, div_round_half_up(population, 100))
    price = grain_price_ppm(population, next_grain)
    return production, consumption, next_grain, materials, price


def _disaster_occurs(seed: int, civilization_id: str, year: int, month: int,
                     hazard_ppm: int) -> bool:
    """Return a stable bounded hazard draw; even maximum hazard stays rare."""
    if not 0 <= hazard_ppm <= 1_000_000:
        raise ValueError("WG-DISASTER-HAZARD: hazard must be bounded ppm")
    threshold = min(100_000, max(0, div_round_half_up(hazard_ppm, 10)))
    roll = derive_seed(seed, "history.disaster", civilization_id,
                       f"{year:04d}:{month:02d}") % 1_000_000
    return roll < threshold


def _disaster_losses(population: int, materials: int,
                     hazard_ppm: int) -> tuple[int, int]:
    if population < 0 or materials < 0 or not 0 <= hazard_ppm <= 1_000_000:
        raise ValueError("WG-DISASTER-LOSS: invalid population, materials, or hazard")
    casualties = min(population, div_round_half_up(population * hazard_ppm, 100_000_000))
    material_loss = min(materials, div_round_half_up(materials * hazard_ppm, 50_000_000))
    return casualties, material_loss


def _crime_occurs(seed: int, civilization_id: str, year: int, month: int,
                  scarcity_ppm: int, stability_ppm: int) -> bool:
    if not 0 <= scarcity_ppm <= 1_000_000 or not 0 <= stability_ppm <= 1_000_000:
        raise ValueError("WG-CRIME-PRESSURE: scarcity and stability must be bounded ppm")
    institutional_pressure = 1_000_000 - stability_ppm
    combined = div_round_half_up(scarcity_ppm + institutional_pressure, 2)
    threshold = min(50_000, div_round_half_up(combined, 20))
    roll = derive_seed(seed, "history.crime", civilization_id,
                       f"{year:04d}:{month:02d}") % 1_000_000
    return roll < threshold


def _crime_currency_loss(currency: int, scarcity_ppm: int) -> int:
    if currency < 0 or not 0 <= scarcity_ppm <= 1_000_000:
        raise ValueError("WG-CRIME-LOSS: invalid currency or scarcity")
    return min(currency, max(1, div_round_half_up(currency * scarcity_ppm, 200_000_000))) \
        if currency and scarcity_ppm else 0


def _route_transport_plan(
    routes: Any, start_region: str, end_region: str, season: int,
) -> tuple[tuple[str, ...], int, int] | None:
    """Return deterministic route IDs, bottleneck capacity, and maintenance."""
    if start_region == end_region:
        return (), 2_147_483_647, 0
    frontier: list[tuple[str, tuple[Any, ...]]] = [(start_region, ())]
    visited = {start_region}
    ordered_routes = sorted(routes, key=lambda route: str(route["route_id"]))
    while frontier:
        region, path = frontier.pop(0)
        candidates = []
        for route in ordered_routes:
            endpoints = (str(route["start_region"]), str(route["end_region"]))
            if region not in endpoints or not bool(route["traversable_seasons"][season]):
                continue
            neighbor = endpoints[1] if endpoints[0] == region else endpoints[0]
            if neighbor not in visited:
                candidates.append((neighbor, route))
        for neighbor, route in candidates:
            next_path = path + (route,)
            if neighbor == end_region:
                return (
                    tuple(str(item["route_id"]) for item in next_path),
                    min(int(item["seasonal_capacity"][season]) for item in next_path),
                    sum(int(item["annual_maintenance"]) for item in next_path),
                )
            visited.add(neighbor)
            frontier.append((neighbor, next_path))
    return None


def _initial_resource_stocks(
    seed: int, physical: dict[str, Any], sites: tuple[Any, ...],
) -> tuple[ResourceStock, ...]:
    regions = physical["regions"]["regions"]
    region_by_cell = {
        int(cell): str(region["region_id"])
        for region in regions for cell in region["cells"]
    }
    stocks: list[ResourceStock] = []
    for deposit in physical["resources"]["deposits"]:
        region_id = region_by_cell[int(deposit["cells"][0])]
        quantity = int(deposit["quantity_kg"])
        stocks.append(ResourceStock(
            stable_id("stock", seed, identity("deposit_id", deposit["deposit_id"])),
            str(deposit["resource"]), region_id, False, quantity, quantity, 0,
        ))
    renewable = physical["resources"]["renewable_yield"]["values"]
    for site in sites:
        annual_yield = max(1, int(renewable[site.cell]))
        capacity = annual_yield * 12
        stocks.append(ResourceStock(
            stable_id("stock", seed, identity("site_id", site.site_id),
                      identity("resource", "biomass")),
            "biomass", site.region_id, True, capacity, capacity, annual_yield,
        ))
    return tuple(sorted(stocks, key=lambda stock: stock.stock_id))


def _stock_extraction(
    stocks: tuple[ResourceStock, ...], regions: tuple[str, ...], requested_kg: int,
) -> tuple[tuple[str, int], ...]:
    remaining = max(0, requested_kg)
    extracted: list[tuple[str, int]] = []
    for stock in sorted(
        (item for item in stocks if item.region_id in regions and item.quantity_kg > 0),
        key=lambda item: (item.renewable, item.stock_id),
    ):
        amount = min(remaining, stock.quantity_kg)
        if amount:
            extracted.append((stock.stock_id, amount))
            remaining -= amount
        if remaining == 0:
            break
    return tuple(extracted)


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
    # Legacy simulation selectors still consume mapping-shaped physical facts;
    # source them from the verified typed reader rather than persisted arrays.
    payloads["hydrology"] = freeze_canonical(asdict(
        VerifiedHydrologyReader(root).load().hydrology
    ))
    payloads["biomes"] = freeze_canonical(asdict(
        VerifiedBiomeReader(root).load().biomes
    ))
    payloads["climate"] = freeze_canonical(asdict(
        VerifiedClimateReader(root).load().climate
    ))
    payloads["climate_typed"] = VerifiedClimateReader(root).load().climate
    payloads["resources"] = freeze_canonical(asdict(
        VerifiedResourceReader(root).load().resources
    ))
    payloads["regions"] = freeze_canonical(asdict(
        VerifiedRegionReader(root).load().regions
    ))
    payloads["terrain_typed"] = VerifiedTerrainReader(root).load().terrain
    return payloads, artifact_ids, file_hashes


def _genesis(seed: int, physical: dict[str, Any]) -> tuple[SimulationState, dict[str, object]]:
    count = int(physical["world_index"]["spec"]["civilization_count"])
    sites = found_sites(seed, physical, count)
    used: set[str] = set()
    civilizations: list[CivilizationState] = []
    cohorts: list[Cohort] = []
    settlements: list[SettlementState] = []
    languages: list[object] = []
    heraldry: dict[str, VectorHeraldry] = {}
    flags: dict[str, str] = {}
    governments = ("council", "monarchy", "clan_compact")
    recipe = simulation_registry_entries("recipes")[0]
    recipe_ratio = recipe["ratio_ppm"]
    if isinstance(recipe_ratio, bool) or not isinstance(recipe_ratio, int):
        raise ValueError("WG-SETTLEMENT-RECIPE: ratio must be an integer")
    for index, site in enumerate(sites):
        resources = tuple(sorted({str(deposit["resource"])
                                  for deposit in physical["resources"]["deposits"]
                                  if site.cell in deposit["cells"]}))
        route_degree = sum(site.region_id in (route["start_region"], route["end_region"])
                           for route in physical["routes"]["routes"])
        identity_design = generate_identity(seed, site.site_id, used, CulturePressure(
            int(physical["biomes"]["biome_id"]["values"][site.cell]),
            int(physical["climate"]["weather_regime"]["values"][site.cell]),
            site.water_access, route_degree, resources,
        ))
        name, language = identity_design.name, identity_design.language
        civilization_id = stable_id(
            "civilization", seed, identity("founding_site_id", site.site_id),
        )
        raw_capacity = int(physical["biomes"]["carrying_capacity"]["values"][site.cell])
        population = max(100, min(5_000, raw_capacity * 10 + 100))
        civilizations.append(CivilizationState(
            civilization_id, name, "; ".join(identity_design.culture_traits),
            governments[index % len(governments)], language.language_id, site.site_id,
            ("agriculture", "masonry"), ("grain", "materials"), (site.region_id,), population,
            EconomyState(population * 18, population * 4, population * 3, 1_000_000),
        ))
        child_population = div_round_half_up(population * 200_000, 1_000_000)
        elder_population = div_round_half_up(population * 150_000, 1_000_000)
        cohort_populations = {
            "child": child_population,
            "adult": population - child_population - elder_population,
            "elder": elder_population,
        }
        cohorts.extend(Cohort(stable_id(
            "cohort", seed, identity("civilization_id", civilization_id),
            identity("life_stage", age_band),
        ), civilization_id, site.site_id, age_band, cohort_population)
                       for age_band, cohort_population in cohort_populations.items())
        settlement_id = stable_id(
            "settlement", seed, identity("site_id", site.site_id),
            identity("founder_civilization_id", civilization_id),
        )
        workshop = WorkshopState(
            stable_id("workshop", seed, identity("settlement_id", settlement_id),
                      identity("recipe_id", str(recipe["id"]))),
            "communal kitchen", str(recipe["id"]), str(recipe["input"]),
            str(recipe["output"]), recipe_ratio,
        )
        settlements.append(SettlementState(
            settlement_id, site.site_id, civilization_id, f"{name} Hold", 0,
            max(population, raw_capacity * 20 + 500), population,
            SettlementStatus.INHABITED, None,
            ("irrigated fields" if site.water_access else "dry fields", "managed commons"),
            ("granary", "housing"), (workshop,),
            (InventoryStack("grain", population * 18),
             InventoryStack("materials", population * 4),
             InventoryStack("food", population * 14)),
        ))
        languages.append(language)
        heraldry[civilization_id] = identity_design.heraldry
        flags[civilization_id] = identity_design.flag
    relations = tuple(DiplomaticRelation(min(left.civilization_id, right.civilization_id),
                                         max(left.civilization_id, right.civilization_id), "rivalry", 350_000)
                      for left, right in combinations(civilizations, 2))
    (laws, magic_sources, magic_effects, religions, religious_institutions,
     schisms, cultural_interpretations) = generate_supernatural(
        seed, tuple(site.site_id for site in sites),
    )
    cosmology = generate_cosmology(seed, laws, magic_sources, religions,
                                   tuple(site.site_id for site in sites))
    stocks = _initial_resource_stocks(seed, physical, sites)
    state = SimulationState(0, 0, sites, tuple(settlements), tuple(civilizations),
                            tuple(cohorts), relations, stocks)
    validate_settlements(state.settlements)
    identities: dict[str, object] = {"languages": tuple(languages), "heraldry": heraldry,
                                    "flags": flags,
                                    "magic_laws": laws, "magic_sources": magic_sources,
                                    "magic_effects": magic_effects, "religions": religions,
                                    "religious_institutions": religious_institutions,
                                    "schisms": schisms,
                                    "cultural_interpretations": cultural_interpretations,
                                    "cosmological_layers": cosmology.layers,
                                    "celestial_cycles": cosmology.cycles,
                                    "cosmological_entities": cosmology.entities,
                                    "afterlife_claims": cosmology.afterlife_claims,
                                    "supernatural_places": cosmology.places,
                                    "cults": cosmology.cults, "sacred_relics": cosmology.relics}
    return state, identities


def _event(seed: int, year: int, month: int, sequence: int, kind: EventKind,
           participants: tuple[str, ...], locations: tuple[str, ...],
           consequences: tuple[Consequence, ...], summary: str,
           causes: tuple[str, ...] = ()) -> HistoryEvent:
    event_id = stable_id(
        "event", seed, identity("year", year), identity("month", month),
        identity("kind", kind.value),
        identity("participants", "|".join(sorted(participants)) or "none"),
        identity("locations", "|".join(sorted(locations)) or "none"),
        identity("causes", "|".join(sorted(causes)) or "none"),
    )
    return HistoryEvent(event_id, year, month,
                        sequence, kind, causes, participants, locations, consequences, summary)


def simulate_world(world: str | Path, history_years: int, output: str | Path) -> dict[str, Any]:
    if history_years < 0:
        raise ValueError("history years must be nonnegative")
    world_root, output_root = Path(world), Path(output)
    physical, physical_ids, physical_hashes_before = _load_physical(world_root)
    seed = int(physical["world_index"]["seed"])
    registry_hashes = validate_and_hash_registries()
    # Capacity and genesis validation must finish before creating any output.
    state, identities = _genesis(seed, physical)
    dynasty_houses, consequential_people = genesis_genealogy(
        seed, state.civilizations, state.cohorts, state.settlements,
    )
    people_by_civ = {
        civilization.civilization_id: tuple(
            person for person in consequential_people
            if person.civilization_id == civilization.civilization_id)
        for civilization in state.civilizations
    }
    genesis_sites = state.sites
    genesis_civilizations = state.civilizations
    genesis_settlements = state.settlements
    genesis_relations = state.relations
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
    source_chunks = world_root / "chunks"
    if source_chunks.is_dir():
        for source_chunk in sorted(source_chunks.rglob("*.grid")):
            relative = source_chunk.relative_to(source_chunks)
            atomic_write_bytes(output_root / "chunks" / relative, source_chunk.read_bytes())
    # Monthly batches are derived output owned by this simulator. Prevent a
    # shorter rerun from retaining an invalid suffix from an earlier run.
    for stale_batch in repository.root.glob("history_[0-9][0-9][0-9][0-9]_*.json"):
        stale_batch.unlink()
    snapshots: list[StateSnapshot] = [make_snapshot(state)]
    ledger: list[HistoryEvent] = []
    previous_by_civ: dict[str, str] = {}
    last_collapse_by_civ: dict[str, str] = {}
    sequence = 0
    site_by_id = {site.site_id: site for site in state.sites}
    settlement_by_civ = {settlement.civilization_id: settlement.settlement_id
                         for settlement in state.settlements}
    recipe_ratio_by_settlement = {
        settlement.settlement_id: settlement.workshops[0].ratio_ppm
        for settlement in state.settlements
    }
    government_stability: dict[str, int] = {}
    for entry in simulation_registry_entries("governments"):
        stability = entry["stability_ppm"]
        if isinstance(stability, bool) or not isinstance(stability, int):
            raise ValueError("WG-CRIME-REGISTRY: stability must be an integer")
        government_stability[str(entry["id"])] = stability
    capacity_by_civ = {
        civilization.civilization_id: max(500, int(physical["biomes"]["carrying_capacity"]["values"]
                                                    [site_by_id[civilization.capital_site_id].cell]) * 20 + 500)
        for civilization in state.civilizations
    }
    routes = physical["routes"]["routes"]
    batch_dependency = tuple(physical_ids.values())
    history_producer = simulation_stage_fingerprint("history", history_years, registry_hashes)
    prefix_digest = hashlib.sha256(b"storyteller.history.prefix.v1").hexdigest()
    previous_batch_id = ""
    for year in range(1, history_years + 1):
        for month in range(1, 13):
            batch: list[HistoryEvent] = []
            ordered_civilizations = sorted(
                (item for item in state.civilizations if item.active),
                key=lambda item: item.civilization_id,
            )
            for civilization_index, civilization in enumerate(ordered_civilizations):
                capacity = capacity_by_civ[civilization.civilization_id]
                outbreak = derive_seed(
                    seed, "history.disease",
                    f"{civilization.civilization_id}:{year:04d}:{month:02d}",
                    "outbreak",
                ) % 97 == 0
                _, _, population_delta = _demographic_change(
                    civilization.population, capacity, outbreak=outbreak,
                )
                production, consumption, _, materials, price = _monthly_economy(
                    civilization.population, civilization.economy.grain,
                )
                regeneration = tuple(
                    (stock.stock_id, min(stock.regeneration_kg,
                                         stock.capacity_kg - stock.quantity_kg))
                    for stock in state.resource_stocks
                    if civilization_index == 0 and stock.renewable
                    and stock.quantity_kg < stock.capacity_kg
                )
                effective_stocks = tuple(
                    stock if not any(stock.stock_id == stock_id for stock_id, _ in regeneration)
                    else stock.__class__(
                        stock.stock_id, stock.resource, stock.region_id, stock.renewable,
                        stock.capacity_kg,
                        min(stock.capacity_kg, stock.quantity_kg + next(
                            amount for stock_id, amount in regeneration if stock_id == stock.stock_id
                        )), stock.regeneration_kg,
                    )
                    for stock in state.resource_stocks
                )
                extraction = _stock_extraction(
                    effective_stocks, civilization.territory, materials,
                )
                extracted_materials = sum(amount for _, amount in extraction)
                settlement_id = settlement_by_civ[civilization.civilization_id]
                processed_food = div_round_half_up(
                    production * recipe_ratio_by_settlement[settlement_id], 1_000_000,
                )
                scarcity_ppm = min(1_000_000, div_round_half_up(
                    civilization.population * 1_000_000,
                    max(1, civilization.economy.grain),
                ))
                ledger_consequences = tuple(
                    Consequence(ConsequenceKind.ECONOMY_LEDGER_APPEND, settlement_id, amount,
                                target="resources", value=kind)
                    for kind, amount in (("resource_recovery", sum(item[1] for item in regeneration)),
                                         ("resource_depletion", sum(item[1] for item in extraction)))
                    if amount
                )
                if month == 12:
                    adjacent = tuple(route for route in routes
                                     if site_by_id[civilization.capital_site_id].region_id in (
                                         route["start_region"], route["end_region"]))
                    maintenance = sum(int(route["annual_maintenance"]) for route in adjacent)
                    tax = div_round_half_up(civilization.economy.currency, 100)
                    ledger_consequences += (
                        Consequence(ConsequenceKind.ECONOMY_LEDGER_APPEND, settlement_id, tax,
                                    target="currency", value="tax_assessment"),
                        Consequence(ConsequenceKind.ECONOMY_LEDGER_APPEND, settlement_id, maintenance,
                                    target="currency", value="route_maintenance"),
                    )
                sequence += 1
                cause = previous_by_civ.get(civilization.civilization_id)
                event = _event(seed, year, month, sequence, EventKind.MONTHLY_DEMOGRAPHY,
                               (civilization.civilization_id,), (civilization.capital_site_id,),
                               tuple(Consequence(ConsequenceKind.RESOURCE_STOCK_DELTA, stock_id, amount)
                                     for stock_id, amount in regeneration) +
                               tuple(Consequence(ConsequenceKind.RESOURCE_STOCK_DELTA, stock_id, -amount)
                                     for stock_id, amount in extraction) +
                               (Consequence(
                                   ConsequenceKind.POPULATION_DELTA, civilization.civilization_id,
                                   population_delta,
                                   target=next(cohort.cohort_id for cohort in state.cohorts
                                               if cohort.civilization_id == civilization.civilization_id
                                               and cohort.age_band == (
                                                   "child" if population_delta >= 0 else "elder")),
                               ),
                                Consequence(ConsequenceKind.GRAIN_DELTA, civilization.civilization_id,
                                            production - consumption),
                                Consequence(ConsequenceKind.MATERIAL_DELTA, civilization.civilization_id,
                                            extracted_materials),
                                Consequence(ConsequenceKind.PRICE_SET, civilization.civilization_id, price),
                                Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                            settlement_id, production, target="grain"),
                                Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                            settlement_id, -production, target="grain"),
                                Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                            settlement_id, processed_food - consumption,
                                            target="food"),
                                Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                            settlement_id, extracted_materials,
                                            target="materials"),
                                Consequence(ConsequenceKind.ECONOMY_LEDGER_APPEND,
                                            settlement_id, scarcity_ppm, target="grain",
                                            value="scarcity_price",
                                            details=(("price_ppm", str(price)),))) +
                               ledger_consequences,
                               "Births, deaths, disease, harvest, production, spoilage, and consumption resolved.",
                               (cause,) if cause else ())
                state = apply_event(state, event)
                ledger.append(event); batch.append(event)
                previous_by_civ[civilization.civilization_id] = event.event_id
                season_count = len(physical["climate_typed"].seasons)
                season_index = min(season_count - 1,
                                   div_floor_exact((month - 1) * season_count, 12))
                hazard_ppm = int(physical["climate_typed"].seasons[
                    season_index
                ].hazard_ppm.values[site_by_id[civilization.capital_site_id].cell])
                if _disaster_occurs(seed, civilization.civilization_id, year, month, hazard_ppm):
                    current_civilization = next(
                        item for item in state.civilizations
                        if item.civilization_id == civilization.civilization_id)
                    current_settlement = next(
                        item for item in state.settlements
                        if item.settlement_id == settlement_id)
                    target_cohort = max(
                        (cohort for cohort in state.cohorts
                         if cohort.civilization_id == civilization.civilization_id),
                        key=lambda cohort: (cohort.population, cohort.cohort_id),
                    )
                    available_materials = min(
                        current_civilization.economy.materials,
                        next((stack.quantity for stack in current_settlement.inventory
                              if stack.material_id == "materials"), 0),
                    )
                    casualties, material_loss = _disaster_losses(
                        target_cohort.population, available_materials, hazard_ppm)
                    disaster_consequences = tuple(item for item in (
                        Consequence(ConsequenceKind.POPULATION_DELTA,
                                    civilization.civilization_id, -casualties,
                                    target=target_cohort.cohort_id,
                                    details=(("hazard_ppm", str(hazard_ppm)),
                                             ("source_id", physical_ids["climate"]))),
                        Consequence(ConsequenceKind.MATERIAL_DELTA,
                                    civilization.civilization_id, -material_loss,
                                    details=(("hazard_ppm", str(hazard_ppm)),
                                             ("source_id", physical_ids["climate"]))),
                        Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                    settlement_id, -material_loss, target="materials",
                                    details=(("hazard_ppm", str(hazard_ppm)),
                                             ("source_id", physical_ids["climate"]))),
                    ) if item.amount != 0)
                    if disaster_consequences:
                        sequence += 1
                        disaster = _event(
                            seed, year, month, sequence, EventKind.DISASTER,
                            (civilization.civilization_id,), (civilization.capital_site_id,),
                            disaster_consequences,
                            "A climate-derived disaster caused bounded casualties and material damage.",
                            (previous_by_civ[civilization.civilization_id],),
                        )
                        state = apply_event(state, disaster)
                        ledger.append(disaster); batch.append(disaster)
                        previous_by_civ[civilization.civilization_id] = disaster.event_id
                current_civilization = next(
                    item for item in state.civilizations
                    if item.civilization_id == civilization.civilization_id)
                stability_ppm = government_stability[current_civilization.government]
                if _crime_occurs(seed, civilization.civilization_id, year, month,
                                 scarcity_ppm, stability_ppm):
                    cohort_actors = sorted(
                        (cohort for cohort in state.cohorts
                         if cohort.civilization_id == civilization.civilization_id
                         and cohort.population > 0),
                        key=lambda cohort: (cohort.age_band, cohort.cohort_id),
                    )
                    currency_loss = _crime_currency_loss(
                        current_civilization.economy.currency, scarcity_ppm)
                    if len(cohort_actors) >= 2 and currency_loss:
                        actor_cohort, victim_cohort = cohort_actors[0], cohort_actors[-1]
                        sequence += 1
                        crime = _event(
                            seed, year, month, sequence, EventKind.CRIME,
                            (actor_cohort.cohort_id, victim_cohort.cohort_id),
                            (civilization.capital_site_id,),
                            (Consequence(
                                ConsequenceKind.CURRENCY_DELTA,
                                civilization.civilization_id, -currency_loss,
                                target=victim_cohort.cohort_id, value="institutional_resolution_cost",
                                details=(("actor_cohort_id", actor_cohort.cohort_id),
                                         ("victim_cohort_id", victim_cohort.cohort_id),
                                         ("scarcity_ppm", str(scarcity_ppm)),
                                         ("stability_ppm", str(stability_ppm)),
                                         ("government_registry_id",
                                          current_civilization.government),
                                         ("resolution", "restitution_and_public_censure")),
                            ),),
                            "Scarcity-driven theft incurred a bounded institutional resolution cost.",
                            (previous_by_civ[civilization.civilization_id],),
                        )
                        state = apply_event(state, crime)
                        ledger.append(crime); batch.append(crime)
                        previous_by_civ[civilization.civilization_id] = crime.event_id
                if month == 12:
                    current_cohorts = {cohort.age_band: cohort for cohort in state.cohorts
                                       if cohort.civilization_id == civilization.civilization_id}
                    child_to_adult = min(current_cohorts["child"].population,
                                         max(1, div_round_half_up(
                                             current_cohorts["child"].population, 20)))
                    adult_to_elder = min(current_cohorts["adult"].population,
                                         max(1, div_round_half_up(
                                             current_cohorts["adult"].population, 50)))
                    ageing_consequences = tuple(consequence for consequence in (
                        Consequence(ConsequenceKind.COHORT_TRANSFER,
                                    current_cohorts["child"].cohort_id, child_to_adult,
                                    target=current_cohorts["adult"].cohort_id),
                        Consequence(ConsequenceKind.COHORT_TRANSFER,
                                    current_cohorts["adult"].cohort_id, adult_to_elder,
                                    target=current_cohorts["elder"].cohort_id),
                    ) if consequence.amount > 0)
                    if not ageing_consequences:
                        continue
                    sequence += 1
                    ageing = _event(
                        seed, year, month, sequence, EventKind.AGEING,
                        (civilization.civilization_id,), (civilization.capital_site_id,),
                        ageing_consequences,
                        "A conserved annual cohort aged from childhood to adulthood and elderhood.",
                        (previous_by_civ[civilization.civilization_id],),
                    )
                    state = apply_event(state, ageing)
                    ledger.append(ageing); batch.append(ageing)
                    previous_by_civ[civilization.civilization_id] = ageing.event_id
                if month == 12 and year % 5 == 0:
                    social_people = people_by_civ[civilization.civilization_id]
                    relation_types = ("spouse", "parent_of", "adopted_parent_of", "house_member")
                    relation_index = div_floor_exact(year, 5) - 1
                    source_person = social_people[relation_index % len(social_people)]
                    target_person = social_people[(relation_index + 1) % len(social_people)]
                    relation_type = relation_types[relation_index % len(relation_types)]
                    sequence += 1
                    relationship = _event(
                        seed, year, month, sequence, EventKind.RELATIONSHIP,
                        (source_person.person_id, target_person.person_id),
                        (civilization.capital_site_id,),
                        (Consequence(ConsequenceKind.GENEALOGY_RELATION_ADD,
                                     source_person.person_id, target=target_person.person_id,
                                     value=relation_type,
                                     details=(("house_id", source_person.house_id),)),),
                        f"A consequential {relation_type} relationship was publicly recorded.",
                        (previous_by_civ[civilization.civilization_id],),
                    )
                    state = apply_event(state, relationship)
                    ledger.append(relationship); batch.append(relationship)
                    previous_by_civ[civilization.civilization_id] = relationship.event_id
            active = sorted((c for c in state.civilizations if c.active), key=lambda item: item.civilization_id)
            if month == 12 and len(active) > 1:
                seller, buyer = max(active, key=lambda c: (c.economy.grain, c.civilization_id)), \
                                min(active, key=lambda c: (c.economy.grain, c.civilization_id))
                desired_amount = min(100, div_round_half_up(seller.economy.grain, 20))
                seller_region = site_by_id[seller.capital_site_id].region_id
                buyer_region = site_by_id[buyer.capital_site_id].region_id
                plan = _route_transport_plan(routes, seller_region, buyer_region, 3)
                amount = min(desired_amount, plan[1]) if plan else 0
                if seller.civilization_id != buyer.civilization_id and amount and plan:
                    route_ids, transport_capacity, maintenance = plan
                    seller_settlement = settlement_by_civ[seller.civilization_id]
                    buyer_settlement = settlement_by_civ[buyer.civilization_id]
                    sequence += 1
                    trade = _event(seed, year, month, sequence, EventKind.TRADE,
                                   (seller.civilization_id, buyer.civilization_id),
                                   (seller.capital_site_id, buyer.capital_site_id),
                                   (Consequence(ConsequenceKind.GRAIN_DELTA, seller.civilization_id, -amount),
                                    Consequence(ConsequenceKind.GRAIN_DELTA, buyer.civilization_id, amount),
                                    Consequence(ConsequenceKind.CURRENCY_DELTA, seller.civilization_id, amount),
                                    Consequence(ConsequenceKind.CURRENCY_DELTA, buyer.civilization_id, -amount),
                                    Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                                seller_settlement, -amount, target="grain"),
                                    Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                                buyer_settlement, amount, target="grain"),
                                    Consequence(ConsequenceKind.ECONOMY_LEDGER_APPEND,
                                                seller_settlement, amount, target="grain", value="trade",
                                                details=(("route_ids", ",".join(route_ids)),
                                                         ("transport_capacity", str(transport_capacity)),
                                                         ("maintenance", str(maintenance))))),
                                   "A capacity-bounded route grain exchange completed.",
                                   tuple(sorted({previous_by_civ[seller.civilization_id],
                                                 previous_by_civ[buyer.civilization_id]})))
                    state = apply_event(state, trade); ledger.append(trade); batch.append(trade)
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(bytes.fromhex(prior_prefix) + canonical_json(tuple(batch))).hexdigest()
            batch_artifact = WorldArtifact.build(f"history_{year:04d}_{month:02d}", {
                "events": tuple(batch), "previous_prefix": prior_prefix, "prefix_sha256": prefix_digest,
            }, depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                                                 producer_fingerprint=history_producer)
            repository.put(batch_artifact)
            previous_batch_id = batch_artifact.artifact_id
        annual_batch: list[HistoryEvent] = []
        if year % 5 == 0 and len(state.civilizations) > 1:
            ordered = sorted(state.civilizations, key=lambda c: (c.population, c.civilization_id))
            source_civ, target_civ = ordered[-1], ordered[0]
            migrants = min(25, div_round_half_up(source_civ.population, 100))
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
            diplomatic_details = (("prior_status", relation.status),
                                  ("new_status", new_status))
            consequences = [Consequence(ConsequenceKind.RELATION_SET, left.civilization_id,
                                        100_000 if new_status == "war" else
                                        700_000 if new_status == "alliance" else 500_000,
                                        right.civilization_id, new_status,
                                        details=diplomatic_details)]
            if new_status == "war" and right.territory:
                consequences.extend((
                    Consequence(ConsequenceKind.MATERIAL_DELTA, left.civilization_id,
                                -min(100, left.economy.materials),
                                details=diplomatic_details),
                    Consequence(ConsequenceKind.MATERIAL_DELTA, right.civilization_id,
                                -min(100, right.economy.materials),
                                details=diplomatic_details),
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
            if new_status == "war" and right.territory:
                conquered = right.territory[-1]
                sequence += 1
                conquest = _event(
                    seed, year, 12, sequence, EventKind.CONQUEST,
                    (left.civilization_id, right.civilization_id),
                    (left.capital_site_id, right.capital_site_id),
                    (Consequence(ConsequenceKind.TERRITORY_TRANSFER,
                                 right.civilization_id, -1, value=conquered),
                     Consequence(ConsequenceKind.TERRITORY_TRANSFER,
                                 left.civilization_id, 1, value=conquered)),
                    "A victorious polity seized territory after the war.",
                    (diplomacy.event_id,),
                )
                state = apply_event(state, conquest); ledger.append(conquest)
                annual_batch.append(conquest)
                previous_by_civ[left.civilization_id] = conquest.event_id
                previous_by_civ[right.civilization_id] = conquest.event_id
            else:
                previous_by_civ[left.civilization_id] = diplomacy.event_id
                previous_by_civ[right.civilization_id] = diplomacy.event_id
        if year % 200 == 0:
            actor = min((c for c in state.civilizations if c.active), key=lambda c: c.civilization_id)
            settlement_id = settlement_by_civ[actor.civilization_id]
            lifecycle_details: tuple[tuple[str, str], ...] = (
                ("prior_polity_state", "active"),
                ("new_polity_state", "inactive"),
                ("prior_settlement_status", SettlementStatus.INHABITED.value),
                ("new_settlement_status", SettlementStatus.ABANDONED.value),
                ("settlement_id", settlement_id),
            )
            sequence += 1
            collapse = _event(seed, year, 12, sequence, EventKind.COLLAPSE,
                              (actor.civilization_id,), (actor.capital_site_id,),
                              (Consequence(ConsequenceKind.ACTIVE_SET, actor.civilization_id,
                                           value="inactive", details=lifecycle_details),
                               Consequence(ConsequenceKind.SETTLEMENT_STATUS_SET,
                                           settlement_id,
                                           value=SettlementStatus.ABANDONED.value,
                                           details=lifecycle_details)),
                              "Scarcity and institutional failure caused a polity collapse.",
                              (previous_by_civ[actor.civilization_id],))
            state = apply_event(state, collapse); ledger.append(collapse); annual_batch.append(collapse)
            previous_by_civ[actor.civilization_id] = collapse.event_id
            last_collapse_by_civ[actor.civilization_id] = collapse.event_id
        if year % 200 == 10:
            inactive = sorted((c for c in state.civilizations if not c.active), key=lambda c: c.civilization_id)
            if inactive:
                actor = inactive[0]
                settlement_id = settlement_by_civ[actor.civilization_id]
                collapse_event_id = last_collapse_by_civ[actor.civilization_id]
                lifecycle_details = (("prior_polity_state", "inactive"),
                                     ("new_polity_state", "active"),
                                     ("prior_settlement_status",
                                      SettlementStatus.ABANDONED.value),
                                     ("new_settlement_status", SettlementStatus.INHABITED.value),
                                     ("settlement_id", settlement_id),
                                     ("collapse_event_id", collapse_event_id))
                sequence += 1
                recovery = _event(seed, year, 12, sequence, EventKind.RECOVERY,
                                  (actor.civilization_id,), (actor.capital_site_id,),
                                  (Consequence(ConsequenceKind.ACTIVE_SET, actor.civilization_id,
                                               value="active", details=lifecycle_details),
                                   Consequence(ConsequenceKind.SETTLEMENT_STATUS_SET,
                                               settlement_id,
                                               value=SettlementStatus.INHABITED.value,
                                               details=lifecycle_details)),
                                  "Local institutions restored the collapsed polity.",
                                  (collapse_event_id,))
                state = apply_event(state, recovery); ledger.append(recovery); annual_batch.append(recovery)
                previous_by_civ[actor.civilization_id] = recovery.event_id
        if year % 30 == 0:
            actor = min((c for c in state.civilizations if c.active),
                        key=lambda c: c.civilization_id)
            social_people = people_by_civ[actor.civilization_id]
            relation_index = div_floor_exact(year, 5) - 1
            outgoing = social_people[relation_index % len(social_people)]
            incoming = social_people[(relation_index + 1) % len(social_people)]
            claim = next(
                event for event in reversed(ledger)
                if event.kind is EventKind.RELATIONSHIP
                and any(item.kind is ConsequenceKind.GENEALOGY_RELATION_ADD
                        and item.subject == outgoing.person_id
                        and item.target == incoming.person_id for item in event.consequences)
            )
            claim_consequence = next(item for item in claim.consequences
                                     if item.kind is ConsequenceKind.GENEALOGY_RELATION_ADD)
            sequence += 1
            succession = _event(
                seed, year, 12, sequence, EventKind.SUCCESSION,
                (outgoing.person_id, incoming.person_id), (actor.capital_site_id,),
                (Consequence(ConsequenceKind.CURRENCY_DELTA,
                             actor.civilization_id, -5),
                 Consequence(ConsequenceKind.OFFICEHOLDER_SET,
                             actor.civilization_id, target=incoming.person_id,
                             value=outgoing.person_id,
                             details=(("house_id", outgoing.house_id),
                                      ("claim_event_id", claim.event_id),
                                      ("claim_type", claim_consequence.value)))),
                "A named officeholder succeeded through a recorded social claim.",
                (claim.event_id,),
            )
            state = apply_event(state, succession); ledger.append(succession)
            annual_batch.append(succession)
            previous_by_civ[actor.civilization_id] = succession.event_id
        proposal_schedule = ((20, EventKind.EXPLORATION, ConsequenceKind.CURRENCY_DELTA, -10),
                             (40, EventKind.CONSTRUCTION, ConsequenceKind.MATERIAL_DELTA, -20),
                             (50, EventKind.TECHNOLOGY, ConsequenceKind.MATERIAL_DELTA, -15),
                             (25, EventKind.REFORM, ConsequenceKind.CURRENCY_DELTA, -5))
        for interval, proposal_kind, consequence_kind, amount in proposal_schedule:
            if year % interval:
                continue
            actor = min((c for c in state.civilizations if c.active), key=lambda c: c.civilization_id)
            sequence += 1
            consequences = [Consequence(consequence_kind, actor.civilization_id, amount)]
            if proposal_kind is EventKind.REFORM:
                government_entries = simulation_registry_entries("governments")
                alternatives = sorted(
                    (item for item in government_entries
                     if str(item["id"]) != actor.government),
                    key=lambda item: (-int(cast(int, item["stability_ppm"])), str(item["id"])),
                )
                if not alternatives or actor.economy.currency < 5:
                    continue
                next_government = str(alternatives[0]["id"])
                capacity = capacity_by_civ[actor.civilization_id]
                scarcity_ppm = max(0, min(1_000_000, div_round_half_up(
                    max(0, actor.population - capacity) * 1_000_000, max(1, capacity),
                )))
                stability_ppm = government_stability[actor.government]
                pressure_kind, pressure_ppm = (
                    ("scarcity", scarcity_ppm) if scarcity_ppm
                    else ("instability", 1_000_000 - stability_ppm)
                )
                reform_details = (("pressure_kind", pressure_kind),
                                  ("pressure_ppm", str(pressure_ppm)),
                                  ("prior_government", actor.government),
                                  ("new_government", next_government))
                consequences = [
                    Consequence(ConsequenceKind.CURRENCY_DELTA,
                                actor.civilization_id, -5, details=reform_details),
                    Consequence(ConsequenceKind.GOVERNMENT_SET,
                                actor.civilization_id, target=next_government,
                                value=actor.government, details=reform_details),
                ]
            if proposal_kind is EventKind.EXPLORATION:
                previously_discovered = {
                    item.target for event in ledger for item in event.consequences
                    if item.kind is ConsequenceKind.REGION_DISCOVERY_ADD
                }
                owned_regions = {region for civilization in state.civilizations
                                 for region in civilization.territory}
                origin_region = site_by_id[actor.capital_site_id].region_id
                destinations = sorted(
                    str(region["region_id"]) for region in physical["regions"]["regions"]
                    if str(region["region_id"]) not in owned_regions
                    and str(region["region_id"]) not in previously_discovered
                )
                plans = tuple((destination, _route_transport_plan(
                    routes, origin_region, destination, 3,
                )) for destination in destinations)
                reachable = next(((destination, plan) for destination, plan in plans if plan), None)
                if reachable is None or actor.economy.currency < 10:
                    continue
                destination, plan = reachable
                assert plan is not None
                settlement_id = settlement_by_civ[actor.civilization_id]
                route_ids = plan[0]
                exploration_details = (("origin_region_id", origin_region),
                                       ("route_ids", ",".join(route_ids)),
                                       ("currency_cost", "10"))
                consequences = [
                    Consequence(ConsequenceKind.CURRENCY_DELTA,
                                actor.civilization_id, -10, details=exploration_details),
                    Consequence(ConsequenceKind.REGION_DISCOVERY_ADD,
                                actor.civilization_id, target=destination,
                                value=settlement_id, details=exploration_details),
                ]
            if proposal_kind is EventKind.TECHNOLOGY:
                technologies = sorted(simulation_registry_entries("technologies"),
                                      key=lambda item: str(item["id"]))
                known = set(actor.capabilities)
                technology = next((item for item in technologies
                                   if str(item["id"]) not in known
                                   and set(str(required) for required in
                                           cast(tuple[object, ...], item["requires"])) <= known),
                                  None)
                if technology is None or actor.economy.materials < 15:
                    continue
                settlement_id = settlement_by_civ[actor.civilization_id]
                settlement = next(item for item in state.settlements
                                  if item.settlement_id == settlement_id)
                workshop_id = min(item.workshop_id for item in settlement.workshops)
                prerequisites = tuple(str(item) for item in
                                      cast(tuple[object, ...], technology["requires"]))
                technology_details = (("settlement_id", settlement_id),
                                      ("workshop_id", workshop_id),
                                      ("prerequisites", ",".join(prerequisites)),
                                      ("material_cost", "15"))
                consequences = [
                    Consequence(ConsequenceKind.MATERIAL_DELTA,
                                actor.civilization_id, -15, details=technology_details),
                    Consequence(ConsequenceKind.CAPABILITY_ADD,
                                actor.civilization_id, target=str(technology["id"]),
                                value=workshop_id, details=technology_details),
                ]
            if proposal_kind is EventKind.CONSTRUCTION:
                settlement_id = settlement_by_civ[actor.civilization_id]
                settlement = next(item for item in state.settlements
                                  if item.settlement_id == settlement_id)
                inventory = {item.material_id: item.quantity for item in settlement.inventory}
                if actor.economy.materials < 20 or inventory.get("materials", 0) < 20:
                    continue
                addressed_need = min(
                    actor.needs,
                    key=lambda need: (div_floor_exact(inventory.get(need, 0) * 1_000_000,
                                                      max(1, settlement.population)), need),
                )
                building, workshop_kind = {
                    "grain": ("grain exchange", "milling kitchen"),
                    "materials": ("masonry storehouse", "masonry kitchen"),
                    "shelter": ("communal hall", "hall kitchen"),
                }.get(addressed_need, ("communal storehouse", "communal kitchen"))
                project_id = stable_id(
                    "construction_project", seed,
                    identity("settlement_id", settlement_id),
                    identity("construction_year", year),
                    identity("addressed_need", addressed_need),
                )
                workshop_id = stable_id(
                    "workshop", seed, identity("settlement_id", settlement_id),
                    identity("recipe_id", "food"), identity("construction_year", year),
                )
                project_details = (("project_id", project_id),
                                   ("addressed_need", addressed_need),
                                   ("material_cost", "20"),
                                   ("workshop_id", workshop_id))
                consequences[0] = Consequence(
                    consequence_kind, actor.civilization_id, amount,
                    details=project_details,
                )
                consequences.extend((
                    Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA, settlement_id,
                                -20, target="materials", details=project_details),
                    Consequence(ConsequenceKind.SETTLEMENT_BUILDING_ADD, settlement_id,
                                value=building, details=project_details),
                    Consequence(ConsequenceKind.SETTLEMENT_WORKSHOP_ADD, settlement_id,
                                value=f"{workshop_id}|{workshop_kind}|food|grain|food|800000",
                                details=project_details),
                ))
            proposal = _event(seed, year, 12, sequence, proposal_kind,
                              (actor.civilization_id,), (actor.capital_site_id,),
                              tuple(consequences),
                              f"A deterministic {proposal_kind.value} proposal was supplied and resolved.",
                              (previous_by_civ[actor.civilization_id],))
            state = apply_event(state, proposal); ledger.append(proposal); annual_batch.append(proposal)
        if year % 50 == 0:
            actor = min((c for c in state.civilizations if c.active), key=lambda c: c.civilization_id)
            settlement_id = settlement_by_civ[actor.civilization_id]
            settlement = next(item for item in state.settlements
                              if item.settlement_id == settlement_id)
            material_stack = next((stack for stack in settlement.inventory
                                   if stack.material_id == "materials"), None)
            if material_stack is not None and material_stack.quantity >= 5:
                workshop_id = min(workshop.workshop_id for workshop in settlement.workshops)
                sequence += 1
                commission = _event(
                    seed, year, 12, sequence, EventKind.COMMISSION,
                    (actor.civilization_id,), (actor.capital_site_id,),
                    (Consequence(ConsequenceKind.MATERIAL_DELTA, actor.civilization_id, -5),
                     Consequence(ConsequenceKind.SETTLEMENT_INVENTORY_DELTA, settlement_id, -5,
                                 target="materials", details=(("artifact_class", "legendary"),
                                                               ("material_id", "stone"),
                                                               ("workshop_id", workshop_id)))),
                    "A rare masterwork commission consumed material and succeeded.",
                    (previous_by_civ[actor.civilization_id],),
                )
                state = apply_event(state, commission); ledger.append(commission)
                annual_batch.append(commission)
                previous_by_civ[actor.civilization_id] = commission.event_id
        if year % 15 == 0:
            actor = min((c for c in state.civilizations if c.active),
                        key=lambda c: c.civilization_id)
            religions = cast(tuple[Religion, ...], identities["religions"])
            institutions = cast(tuple[ReligiousInstitution, ...],
                                identities["religious_institutions"])
            religion = sorted(religions, key=lambda item: item.religion_id)[
                (div_floor_exact(year, 15) - 1) % len(religions)
            ]
            institution = next(item for item in institutions
                               if item.religion_id == religion.religion_id)
            sequence += 1
            patronage = _event(
                seed, year, 12, sequence, EventKind.RELIGION,
                (actor.civilization_id,), (religion.holy_site_id,),
                (Consequence(ConsequenceKind.CURRENCY_DELTA,
                             actor.civilization_id, -5),
                 Consequence(ConsequenceKind.RELIGIOUS_PATRONAGE_ADD,
                             actor.civilization_id, target=religion.religion_id,
                             value=institution.institution_id,
                             details=(("holy_site_id", religion.holy_site_id),))),
                "A polity granted material patronage to a religious institution.",
                (previous_by_civ[actor.civilization_id],),
            )
            state = apply_event(state, patronage); ledger.append(patronage)
            annual_batch.append(patronage)
            previous_by_civ[actor.civilization_id] = patronage.event_id
        if year % 35 == 0:
            actor = min((c for c in state.civilizations if c.active),
                        key=lambda c: c.civilization_id)
            religions = cast(tuple[Religion, ...], identities["religions"])
            institutions = cast(tuple[ReligiousInstitution, ...],
                                identities["religious_institutions"])
            parent_religion = min(religions, key=lambda item: item.religion_id)
            parent_institution = next(
                item for item in institutions
                if item.religion_id == parent_religion.religion_id
            )
            child_institution_id = stable_id(
                "religious_institution", seed,
                identity("parent_institution_id", parent_institution.institution_id),
                identity("schism_year", year),
            )
            disputed_claim = f"whether {parent_religion.belief_claim}"
            details = (("holy_site_id", parent_religion.holy_site_id),
                       ("registry_id", parent_institution.registry_id),
                       ("rite", parent_institution.rite),
                       ("disputed_claim", disputed_claim))
            sequence += 1
            schism = _event(
                seed, year, 12, sequence, EventKind.SCHISM,
                (actor.civilization_id, parent_institution.institution_id,
                 child_institution_id),
                (parent_religion.holy_site_id,),
                (Consequence(ConsequenceKind.CURRENCY_DELTA,
                             actor.civilization_id, -5, details=details),
                 Consequence(ConsequenceKind.RELIGIOUS_SCHISM_ADD,
                             parent_religion.religion_id,
                             target=child_institution_id,
                             value=parent_institution.institution_id,
                             details=details)),
                "A doctrinal dispute formed a child institution without altering its parent.",
                (previous_by_civ[actor.civilization_id],),
            )
            state = apply_event(state, schism)
            ledger.append(schism)
            annual_batch.append(schism)
            previous_by_civ[actor.civilization_id] = schism.event_id
        if annual_batch:
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(bytes.fromhex(prior_prefix) + canonical_json(tuple(annual_batch))).hexdigest()
            annual_artifact = WorldArtifact.build(f"history_{year:04d}_12_final", {
                "events": tuple(annual_batch), "previous_prefix": prior_prefix,
                "prefix_sha256": prefix_digest,
            }, depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                                                   producer_fingerprint=history_producer)
            repository.put(annual_artifact)
            previous_batch_id = annual_artifact.artifact_id
        if year % 10 == 0 or year == history_years:
            snapshots.append(make_snapshot(state))
    # Avoid duplicate final snapshots by construction.
    validate_settlements(state.settlements)
    validate_site_lifecycle(seed, genesis_sites, state.sites, state.settlements)
    validate_economy_ledger(state.economy_ledger)
    conservation_ledger = build_conservation_ledger(tuple(ledger))
    validate_conservation_ledger(tuple(ledger), conservation_ledger)
    households, people, personal_relationships = generate_relationships(
        seed, state.cohorts, state.settlements, history_years,
    )
    legendary_artifacts = generate_legendary_artifacts(
        seed, tuple(ledger), people, state.civilizations, state.settlements,
    )
    history_clock = build_history_clock(history_years, tuple(ledger))
    genealogy_relations = project_genealogy(
        seed, tuple(ledger), dynasty_houses, consequential_people,
    )
    religious_patronage = project_religious_patronage(
        seed, tuple(ledger), state.civilizations,
        cast(tuple[Religion, ...], identities["religions"]),
        cast(tuple[ReligiousInstitution, ...], identities["religious_institutions"]),
    )
    religious_schisms = project_religious_schisms(
        seed, tuple(ledger), state.civilizations,
        cast(tuple[Religion, ...], identities["religions"]),
        cast(tuple[ReligiousInstitution, ...], identities["religious_institutions"]),
    )
    successions = project_successions(
        seed, tuple(ledger), state.civilizations, dynasty_houses, consequential_people,
    )
    construction_projects = project_construction(
        tuple(ledger), state.civilizations, state.settlements,
    )
    technology_discoveries = project_technology_discoveries(
        seed, tuple(ledger), state.civilizations, state.settlements,
        simulation_registry_entries("technologies"),
    )
    exploration_discoveries = project_exploration_discoveries(
        seed, tuple(ledger), state.civilizations, state.settlements,
        tuple(str(region["region_id"]) for region in physical["regions"]["regions"]),
        tuple(routes),
    )
    government_reforms = project_government_reforms(
        seed, tuple(ledger), state.civilizations,
        simulation_registry_entries("governments"),
    )
    diplomatic_transitions = project_diplomatic_transitions(
        seed, tuple(ledger), state.civilizations, genesis_relations, state.relations,
    )
    polity_lifecycle = project_polity_lifecycle(
        seed, tuple(ledger), genesis_civilizations, genesis_settlements,
        state.civilizations, state.settlements,
    )
    languages = cast(tuple[LanguageIdentity, ...], identities["languages"])
    identities["language_history"] = tuple(
        stage for language in languages
        for stage in evolve_language(language.language_id, language.morphemes, history_years)
    )
    snapshot_by_year = {snapshot.year: snapshot for snapshot in snapshots}
    snapshots = [snapshot_by_year[year] for year in sorted(snapshot_by_year)]
    dependencies = tuple(sorted(physical_ids.values()))
    refs = []
    for artifact_kind, payload in (("sites", state.sites), ("settlements", state.settlements),
                          ("civilizations", state.civilizations),
                          ("economy", {
                              "algorithm_version": 2,
                              "price_equation": {"version": PRICE_EQUATION_VERSION,
                                                 "minimum_ppm": PRICE_MIN_PPM,
                                                 "maximum_ppm": PRICE_MAX_PPM},
                              "activity": state.economy_ledger,
                              "conservation": conservation_ledger,
                          }),
                          ("peoples", {"households": households, "people": people,
                                       "relationships": personal_relationships}),
                          ("legendary_artifacts", legendary_artifacts),
                          ("history_clock", history_clock),
                          ("genealogy", {"houses": dynasty_houses,
                                         "people": consequential_people,
                                         "relationships": genealogy_relations}),
                          ("religious_patronage", religious_patronage),
                          ("religious_schisms", religious_schisms),
                          ("successions", successions),
                          ("construction_projects", construction_projects),
                          ("technology_discoveries", technology_discoveries),
                          ("exploration_discoveries", exploration_discoveries),
                          ("government_reforms", government_reforms),
                          ("diplomatic_transitions", diplomatic_transitions),
                          ("polity_lifecycle", polity_lifecycle),
                          ("history", tuple(ledger)), ("snapshots", tuple(snapshots)),
                          ("registries", registry_hashes), ("identities", identities)):
        fingerprint_kind = "history" if artifact_kind == "history" else artifact_kind
        artifact = WorldArtifact.build(
            artifact_kind, payload, depends_on=dependencies,
            producer_fingerprint=simulation_stage_fingerprint(
                fingerprint_kind, history_years, registry_hashes),
        )
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
    }, depends_on=tuple(ref.artifact_id for ref in refs),
        producer_fingerprint=simulation_stage_fingerprint(
            "simulation_index", history_years, registry_hashes))
    repository.put(index)
    return {"simulation_index": index.artifact_id, "present_year": history_years,
            "events": len(ledger), "snapshots": len(snapshots), "civilizations": len(state.civilizations)}
