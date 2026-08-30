"""Deterministic twelve-tick scheduler and Phase 3 artifact publisher."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from ...domain.run_spec import derive_seed
from ...storage.fs import atomic_write_bytes
from ..artifacts import WorldArtifact, WorldArtifactRepository, canonical_json, freeze_canonical
from ..biome_reader import VerifiedBiomeReader
from ..climate_reader import VerifiedClimateReader
from ..hydrology_reader import VerifiedHydrologyReader
from ..numeric import div_floor_exact, div_round_half_up, identity, stable_id
from ..region_reader import VerifiedRegionReader
from ..resource_reader import VerifiedResourceReader
from ..terrain_reader import VerifiedTerrainReader
from .artifact_history import ARTIFACT_TRANSITIONS, project_artifact_histories
from .conservation import build_conservation_ledger, validate_conservation_ledger
from .construction import project_construction
from .cosmology import generate_cosmology
from .diplomacy import project_diplomatic_transitions
from .economy import (
    PRICE_EQUATION_VERSION,
    PRICE_MAX_PPM,
    PRICE_MIN_PPM,
    grain_price_ppm,
    validate_economy_ledger,
)
from .events import Consequence, ConsequenceKind, EventKind, HistoryEvent, apply_event, seal_event
from .exploration import project_exploration_discoveries
from .genealogy import (
    genesis_genealogy,
    project_genealogy,
    project_inheritances,
    project_person_statuses,
)
from .heraldry import VectorHeraldry
from .history_clock import build_history_clock
from .language_evolution import evolve_language
from .legendary_artifacts import generate_legendary_artifacts
from .magic import Religion, ReligiousInstitution, generate_supernatural
from .megabeasts import generate_megabeasts, project_megabeast_history
from .names import CulturePressure, LanguageIdentity, generate_identity
from .polity_lifecycle import project_polity_lifecycle
from .proposals import HistoryProposal, ProposalDecision, resolve_proposals
from .reforms import project_government_reforms
from .registries import (
    simulation_registry_entries,
    simulation_stage_fingerprint,
    validate_and_hash_registries,
)
from .relationships import generate_relationships
from .religious_patronage import project_religious_patronage
from .religious_schisms import project_religious_schisms
from .retention import build_retention_inventory, collect_identity_ids
from .settlements import validate_settlements
from .sites import found_sites, validate_site_lifecycle
from .snapshots import StateSnapshot, make_snapshot
from .state import (
    CivilizationState,
    Cohort,
    DiplomaticRelation,
    EconomyState,
    InventoryStack,
    ResourceStock,
    SettlementState,
    SettlementStatus,
    SimulationState,
    WorkshopState,
)
from .succession import project_successions
from .technology import project_technology_discoveries
from .temporal_integrity import validate_temporal_integrity

PHYSICAL_KINDS = (
    "world_index",
    "plates",
    "terrain",
    "terrain_grid_catalog",
    "geology",
    "geology_grid_catalog",
    "hydrology",
    "hydrology_grid_catalog",
    "climate",
    "climate_grid_catalog",
    "soil",
    "soil_grid_catalog",
    "biomes",
    "biome_grid_catalog",
    "resources",
    "resource_grid_catalog",
    "species",
    "ecology",
    "regions",
    "region_grid_catalog",
    "routes",
    "spatial_index",
    "reference_index",
    "map_layers",
    "maps",
    "validation_report",
)


def _demographic_change(
    population: int,
    capacity: int,
    *,
    outbreak: bool,
) -> tuple[int, int, int]:
    """Return births, deaths, and bounded population delta for one month."""
    births = div_round_half_up(population * 2, 1_000)
    deaths = div_round_half_up(population, 1_000)
    if outbreak:
        deaths += div_round_half_up(population, 200)
    delta = min(max(0, capacity - population), births) - deaths
    return births, deaths, delta


def _monthly_economy(
    population: int,
    grain: int,
) -> tuple[int, int, int, int, int]:
    """Return production, consumption, next grain, materials, and price."""
    production = max(1, div_round_half_up(population, 8))
    consumption = max(1, div_round_half_up(population, 10))
    next_grain = max(0, grain + production - consumption)
    materials = max(1, div_round_half_up(population, 100))
    price = grain_price_ppm(population, next_grain)
    return production, consumption, next_grain, materials, price


def _disaster_occurs(
    seed: int, civilization_id: str, year: int, month: int, hazard_ppm: int
) -> bool:
    """Return a stable bounded hazard draw; even maximum hazard stays rare."""
    if not 0 <= hazard_ppm <= 1_000_000:
        raise ValueError("WG-DISASTER-HAZARD: hazard must be bounded ppm")
    threshold = min(100_000, max(0, div_round_half_up(hazard_ppm, 10)))
    roll = (
        derive_seed(seed, "history.disaster", civilization_id, f"{year:04d}:{month:02d}")
        % 1_000_000
    )
    return roll < threshold


def _disaster_losses(population: int, materials: int, hazard_ppm: int) -> tuple[int, int]:
    if population < 0 or materials < 0 or not 0 <= hazard_ppm <= 1_000_000:
        raise ValueError("WG-DISASTER-LOSS: invalid population, materials, or hazard")
    casualties = min(population, div_round_half_up(population * hazard_ppm, 100_000_000))
    material_loss = min(materials, div_round_half_up(materials * hazard_ppm, 50_000_000))
    return casualties, material_loss


def _crime_occurs(
    seed: int, civilization_id: str, year: int, month: int, scarcity_ppm: int, stability_ppm: int
) -> bool:
    if not 0 <= scarcity_ppm <= 1_000_000 or not 0 <= stability_ppm <= 1_000_000:
        raise ValueError("WG-CRIME-PRESSURE: scarcity and stability must be bounded ppm")
    institutional_pressure = 1_000_000 - stability_ppm
    combined = div_round_half_up(scarcity_ppm + institutional_pressure, 2)
    threshold = min(50_000, div_round_half_up(combined, 20))
    roll = (
        derive_seed(seed, "history.crime", civilization_id, f"{year:04d}:{month:02d}") % 1_000_000
    )
    return roll < threshold


def _crime_currency_loss(currency: int, scarcity_ppm: int) -> int:
    if currency < 0 or not 0 <= scarcity_ppm <= 1_000_000:
        raise ValueError("WG-CRIME-LOSS: invalid currency or scarcity")
    return (
        min(currency, max(1, div_round_half_up(currency * scarcity_ppm, 200_000_000)))
        if currency and scarcity_ppm
        else 0
    )


def _route_transport_plan(
    routes: Any,
    start_region: str,
    end_region: str,
    season: int,
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
    seed: int,
    physical: dict[str, Any],
    sites: tuple[Any, ...],
) -> tuple[ResourceStock, ...]:
    regions = physical["regions"]["regions"]
    region_by_cell = {
        int(cell): str(region["region_id"]) for region in regions for cell in region["cells"]
    }
    stocks: list[ResourceStock] = []
    for deposit in physical["resources"]["deposits"]:
        region_id = region_by_cell[int(deposit["cells"][0])]
        quantity = int(deposit["quantity_kg"])
        stocks.append(
            ResourceStock(
                stable_id("stock", seed, identity("deposit_id", deposit["deposit_id"])),
                str(deposit["resource"]),
                region_id,
                False,
                quantity,
                quantity,
                0,
            )
        )
    renewable = physical["resources"]["renewable_yield"]["values"]
    for site in sites:
        annual_yield = max(1, int(renewable[site.cell]))
        capacity = annual_yield * 12
        stocks.append(
            ResourceStock(
                stable_id(
                    "stock",
                    seed,
                    identity("site_id", site.site_id),
                    identity("resource", "biomass"),
                ),
                "biomass",
                site.region_id,
                True,
                capacity,
                capacity,
                annual_yield,
            )
        )
    return tuple(sorted(stocks, key=lambda stock: stock.stock_id))


def _stock_extraction(
    stocks: tuple[ResourceStock, ...],
    regions: tuple[str, ...],
    requested_kg: int,
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
    payloads["hydrology"] = freeze_canonical(asdict(VerifiedHydrologyReader(root).load().hydrology))
    payloads["biomes"] = freeze_canonical(asdict(VerifiedBiomeReader(root).load().biomes))
    payloads["climate"] = freeze_canonical(asdict(VerifiedClimateReader(root).load().climate))
    payloads["climate_typed"] = VerifiedClimateReader(root).load().climate
    payloads["resources"] = freeze_canonical(asdict(VerifiedResourceReader(root).load().resources))
    payloads["regions"] = freeze_canonical(asdict(VerifiedRegionReader(root).load().regions))
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
        resources = tuple(
            sorted(
                {
                    str(deposit["resource"])
                    for deposit in physical["resources"]["deposits"]
                    if site.cell in deposit["cells"]
                }
            )
        )
        route_degree = sum(
            site.region_id in (route["start_region"], route["end_region"])
            for route in physical["routes"]["routes"]
        )
        identity_design = generate_identity(
            seed,
            site.site_id,
            used,
            CulturePressure(
                int(physical["biomes"]["biome_id"]["values"][site.cell]),
                int(physical["climate"]["weather_regime"]["values"][site.cell]),
                site.water_access,
                route_degree,
                resources,
            ),
        )
        name, language = identity_design.name, identity_design.language
        civilization_id = stable_id(
            "civilization",
            seed,
            identity("founding_site_id", site.site_id),
        )
        raw_capacity = int(physical["biomes"]["carrying_capacity"]["values"][site.cell])
        population = max(100, min(5_000, raw_capacity * 10 + 100))
        civilizations.append(
            CivilizationState(
                civilization_id,
                name,
                "; ".join(identity_design.culture_traits),
                governments[index % len(governments)],
                language.language_id,
                site.site_id,
                ("agriculture", "masonry"),
                ("grain", "materials"),
                (site.region_id,),
                population,
                EconomyState(population * 18, population * 4, population * 3, 1_000_000),
            )
        )
        child_population = div_round_half_up(population * 200_000, 1_000_000)
        elder_population = div_round_half_up(population * 150_000, 1_000_000)
        cohort_populations = {
            "child": child_population,
            "adult": population - child_population - elder_population,
            "elder": elder_population,
        }
        cohorts.extend(
            Cohort(
                stable_id(
                    "cohort",
                    seed,
                    identity("civilization_id", civilization_id),
                    identity("life_stage", age_band),
                ),
                civilization_id,
                site.site_id,
                age_band,
                cohort_population,
            )
            for age_band, cohort_population in cohort_populations.items()
        )
        settlement_id = stable_id(
            "settlement",
            seed,
            identity("site_id", site.site_id),
            identity("founder_civilization_id", civilization_id),
        )
        workshop = WorkshopState(
            stable_id(
                "workshop",
                seed,
                identity("settlement_id", settlement_id),
                identity("recipe_id", str(recipe["id"])),
            ),
            "communal kitchen",
            str(recipe["id"]),
            str(recipe["input"]),
            str(recipe["output"]),
            recipe_ratio,
        )
        settlements.append(
            SettlementState(
                settlement_id,
                site.site_id,
                civilization_id,
                f"{name} Hold",
                0,
                max(population, raw_capacity * 20 + 500),
                population,
                SettlementStatus.INHABITED,
                None,
                ("irrigated fields" if site.water_access else "dry fields", "managed commons"),
                ("granary", "housing"),
                (workshop,),
                (
                    InventoryStack("grain", population * 18),
                    InventoryStack("materials", population * 4),
                    InventoryStack("food", population * 14),
                ),
            )
        )
        languages.append(language)
        heraldry[civilization_id] = identity_design.heraldry
        flags[civilization_id] = identity_design.flag
    relations = tuple(
        DiplomaticRelation(
            min(left.civilization_id, right.civilization_id),
            max(left.civilization_id, right.civilization_id),
            "rivalry",
            350_000,
        )
        for left, right in combinations(civilizations, 2)
    )
    (
        laws,
        magic_sources,
        magic_effects,
        religions,
        religious_institutions,
        schisms,
        cultural_interpretations,
    ) = generate_supernatural(
        seed,
        tuple(site.site_id for site in sites),
    )
    cosmology = generate_cosmology(
        seed, laws, magic_sources, religions, tuple(site.site_id for site in sites)
    )
    stocks = _initial_resource_stocks(seed, physical, sites)
    state = SimulationState(
        0, 0, sites, tuple(settlements), tuple(civilizations), tuple(cohorts), relations, stocks
    )
    validate_settlements(state.settlements)
    identities: dict[str, object] = {
        "languages": tuple(languages),
        "heraldry": heraldry,
        "flags": flags,
        "magic_laws": laws,
        "magic_sources": magic_sources,
        "magic_effects": magic_effects,
        "religions": religions,
        "religious_institutions": religious_institutions,
        "schisms": schisms,
        "cultural_interpretations": cultural_interpretations,
        "cosmological_layers": cosmology.layers,
        "celestial_cycles": cosmology.cycles,
        "cosmological_entities": cosmology.entities,
        "afterlife_claims": cosmology.afterlife_claims,
        "supernatural_places": cosmology.places,
        "cults": cosmology.cults,
        "sacred_relics": cosmology.relics,
    }
    return state, identities


def _event(
    state: SimulationState,
    seed: int,
    year: int,
    month: int,
    sequence: int,
    kind: EventKind,
    participants: tuple[str, ...],
    locations: tuple[str, ...],
    consequences: tuple[Consequence, ...],
    summary: str,
    causes: tuple[str, ...] = (),
) -> HistoryEvent:
    event_id = stable_id(
        "event",
        seed,
        identity("year", year),
        identity("month", month),
        identity("kind", kind.value),
        identity("participants", "|".join(sorted(participants)) or "none"),
        identity("locations", "|".join(sorted(locations)) or "none"),
        identity("causes", "|".join(sorted(causes)) or "none"),
    )
    return seal_event(
        state,
        HistoryEvent(
            event_id,
            year,
            month,
            sequence,
            kind,
            causes,
            participants,
            locations,
            consequences,
            summary,
        ),
    )


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
        seed,
        state.civilizations,
        state.cohorts,
        state.settlements,
    )
    megabeasts = generate_megabeasts(seed, physical, state)
    people_by_civ = {
        civilization.civilization_id: tuple(
            person
            for person in consequential_people
            if person.civilization_id == civilization.civilization_id
        )
        for civilization in state.civilizations
    }
    living_person_ids = {person.person_id for person in consequential_people}
    genesis_state = state
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
    for interrupted_batch in repository.root.glob("history_[0-9][0-9][0-9][0-9]_*.tmp"):
        interrupted_batch.unlink()
    snapshots: list[StateSnapshot] = [make_snapshot(state)]
    ledger: list[HistoryEvent] = []
    previous_by_civ: dict[str, str] = {}
    last_collapse_by_civ: dict[str, str] = {}
    proposal_decisions: list[ProposalDecision] = []
    sequence = 0
    site_by_id = {site.site_id: site for site in state.sites}
    settlement_by_civ = {
        settlement.civilization_id: settlement.settlement_id for settlement in state.settlements
    }
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
        civilization.civilization_id: max(
            500,
            int(
                physical["biomes"]["carrying_capacity"]["values"][
                    site_by_id[civilization.capital_site_id].cell
                ]
            )
            * 20
            + 500,
        )
        for civilization in state.civilizations
    }
    routes = physical["routes"]["routes"]
    batch_dependency = tuple(physical_ids.values())
    history_producer = simulation_stage_fingerprint("history", history_years, registry_hashes)
    prefix_digest = hashlib.sha256(b"storyteller.history.prefix.v1").hexdigest()
    previous_batch_id = ""
    artifact_heads: dict[str, tuple[str, str, str, str]] = {}
    artifact_transition_counts: dict[str, int] = {}
    megabeast_heads = {
        item.megabeast_id: (item.origin_region_id, item.initial_condition, "")
        for item in megabeasts
    }
    for year in range(1, history_years + 1):
        for month in range(1, 13):
            batch: list[HistoryEvent] = []
            month_start_state = state
            month_start_previous = dict(previous_by_civ)
            ordered_civilizations = sorted(
                (item for item in month_start_state.civilizations if item.active),
                key=lambda item: item.civilization_id,
            )
            regeneration = tuple(
                (stock.stock_id, min(stock.regeneration_kg, stock.capacity_kg - stock.quantity_kg))
                for stock in month_start_state.resource_stocks
                if stock.renewable and stock.quantity_kg < stock.capacity_kg
            )
            effective_stocks = tuple(
                stock
                if not any(stock.stock_id == stock_id for stock_id, _ in regeneration)
                else stock.__class__(
                    stock.stock_id,
                    stock.resource,
                    stock.region_id,
                    stock.renewable,
                    stock.capacity_kg,
                    min(
                        stock.capacity_kg,
                        stock.quantity_kg
                        + next(
                            amount
                            for stock_id, amount in regeneration
                            if stock_id == stock.stock_id
                        ),
                    ),
                    stock.regeneration_kg,
                )
                for stock in month_start_state.resource_stocks
            )
            regeneration_consequences: tuple[Consequence, ...] = ()
            if regeneration:
                recovery_settlement = min(
                    month_start_state.settlements,
                    key=lambda item: item.settlement_id,
                )
                recovery_details = (
                    ("snapshot", f"{year:04d}:{month:02d}"),
                    ("source", "renewable_regeneration"),
                )
                regeneration_consequences = tuple(
                    Consequence(
                        ConsequenceKind.RESOURCE_STOCK_DELTA,
                        stock_id,
                        amount,
                        details=recovery_details,
                    )
                    for stock_id, amount in regeneration
                ) + (
                    Consequence(
                        ConsequenceKind.ECONOMY_LEDGER_APPEND,
                        recovery_settlement.settlement_id,
                        sum(item[1] for item in regeneration),
                        target="resources",
                        value="resource_recovery",
                        details=recovery_details,
                    ),
                )
            resource_candidates: list[HistoryProposal] = []
            for civilization in ordered_civilizations:
                _, _, _, requested_materials, _ = _monthly_economy(
                    civilization.population,
                    civilization.economy.grain,
                )
                extraction = _stock_extraction(
                    effective_stocks,
                    civilization.territory,
                    requested_materials,
                )
                extracted_materials = sum(amount for _, amount in extraction)
                if extracted_materials <= 0:
                    continue
                settlement_id = settlement_by_civ[civilization.civilization_id]
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("resource_tick", f"{year:04d}:{month:02d}"),
                    identity("civilization_id", civilization.civilization_id),
                )
                conflict_keys = tuple(
                    sorted(
                        f"resource-stock:{stock_id}:{year:04d}:{month:02d}"
                        for stock_id, _ in extraction
                    )
                )
                extraction_details = (
                    ("snapshot", f"{year:04d}:{month:02d}"),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                )
                resource_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        month,
                        EventKind.PRODUCTION,
                        civilization.civilization_id,
                        (civilization.civilization_id,),
                        (civilization.capital_site_id,),
                        tuple(
                            Consequence(
                                ConsequenceKind.RESOURCE_STOCK_DELTA,
                                stock_id,
                                -amount,
                                details=extraction_details,
                            )
                            for stock_id, amount in extraction
                        )
                        + (
                            Consequence(
                                ConsequenceKind.MATERIAL_DELTA,
                                civilization.civilization_id,
                                extracted_materials,
                                details=extraction_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                settlement_id,
                                extracted_materials,
                                target="materials",
                                details=extraction_details,
                            ),
                            Consequence(
                                ConsequenceKind.ECONOMY_LEDGER_APPEND,
                                settlement_id,
                                extracted_materials,
                                target="resources",
                                value="resource_depletion",
                                details=extraction_details,
                            ),
                        ),
                        "A capacity-resolved territorial resource extraction completed.",
                        (month_start_previous[civilization.civilization_id],)
                        if civilization.civilization_id in month_start_previous
                        else (),
                        conflict_keys,
                        max(0, 2_147_483_647 - requested_materials),
                    )
                )
            accepted_resources, resource_decisions = resolve_proposals(tuple(resource_candidates))
            proposal_decisions.extend(resource_decisions)
            accepted_resource_by_civ = {item.actor_id: item for item in accepted_resources}
            demographic_candidates: list[HistoryProposal] = []
            demographic_metadata: dict[str, tuple[str, int]] = {}
            for civilization_index, civilization in enumerate(ordered_civilizations):
                capacity = capacity_by_civ[civilization.civilization_id]
                outbreak = (
                    derive_seed(
                        seed,
                        "history.disease",
                        f"{civilization.civilization_id}:{year:04d}:{month:02d}",
                        "outbreak",
                    )
                    % 97
                    == 0
                )
                _, _, population_delta = _demographic_change(
                    civilization.population,
                    capacity,
                    outbreak=outbreak,
                )
                production, consumption, _, _, price = _monthly_economy(
                    civilization.population,
                    civilization.economy.grain,
                )
                settlement_id = settlement_by_civ[civilization.civilization_id]
                processed_food = div_round_half_up(
                    production * recipe_ratio_by_settlement[settlement_id],
                    1_000_000,
                )
                scarcity_ppm = min(
                    1_000_000,
                    div_round_half_up(
                        civilization.population * 1_000_000,
                        max(1, civilization.economy.grain),
                    ),
                )
                ledger_consequences: tuple[Consequence, ...] = ()
                if month == 12:
                    adjacent = tuple(
                        route
                        for route in routes
                        if site_by_id[civilization.capital_site_id].region_id
                        in (route["start_region"], route["end_region"])
                    )
                    maintenance = sum(int(route["annual_maintenance"]) for route in adjacent)
                    tax = div_round_half_up(civilization.economy.currency, 100)
                    ledger_consequences += (
                        Consequence(
                            ConsequenceKind.ECONOMY_LEDGER_APPEND,
                            settlement_id,
                            tax,
                            target="currency",
                            value="tax_assessment",
                        ),
                        Consequence(
                            ConsequenceKind.ECONOMY_LEDGER_APPEND,
                            settlement_id,
                            maintenance,
                            target="currency",
                            value="route_maintenance",
                        ),
                    )
                accepted_resource = accepted_resource_by_civ.get(civilization.civilization_id)
                resource_consequences = (
                    accepted_resource.consequences
                    if accepted_resource is not None
                    else (
                        Consequence(
                            ConsequenceKind.MATERIAL_DELTA, civilization.civilization_id, 0
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                            settlement_id,
                            0,
                            target="materials",
                        ),
                    )
                )
                if civilization_index == 0:
                    resource_consequences = regeneration_consequences + resource_consequences
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("demographic_tick", f"{year:04d}:{month:02d}"),
                    identity("civilization_id", civilization.civilization_id),
                )
                conflict_key = f"demography:{civilization.civilization_id}:{year:04d}:{month:02d}"
                demographic_details = (
                    ("proposal_id", proposal_id),
                    ("conflict_key", conflict_key),
                    ("snapshot", f"{year:04d}:{month:02d}"),
                )
                demographic_consequences = (
                    (
                        Consequence(
                            ConsequenceKind.POPULATION_DELTA,
                            civilization.civilization_id,
                            population_delta,
                            target=next(
                                cohort.cohort_id
                                for cohort in month_start_state.cohorts
                                if cohort.civilization_id == civilization.civilization_id
                                and cohort.age_band
                                == ("child" if population_delta >= 0 else "elder")
                            ),
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.GRAIN_DELTA,
                            civilization.civilization_id,
                            production - consumption,
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.PRICE_SET,
                            civilization.civilization_id,
                            price,
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                            settlement_id,
                            production,
                            target="grain",
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                            settlement_id,
                            -production,
                            target="grain",
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                            settlement_id,
                            processed_food - consumption,
                            target="food",
                            details=demographic_details,
                        ),
                        Consequence(
                            ConsequenceKind.ECONOMY_LEDGER_APPEND,
                            settlement_id,
                            scarcity_ppm,
                            target="grain",
                            value="scarcity_price",
                            details=demographic_details + (("price_ppm", str(price)),),
                        ),
                    )
                    + ledger_consequences
                    + resource_consequences
                )
                demographic_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        month,
                        EventKind.MONTHLY_DEMOGRAPHY,
                        civilization.civilization_id,
                        (civilization.civilization_id,),
                        (civilization.capital_site_id,),
                        demographic_consequences,
                        "Births, deaths, disease, harvest, production, spoilage, and "
                        "consumption resolved.",
                        (month_start_previous[civilization.civilization_id],)
                        if civilization.civilization_id in month_start_previous
                        else (),
                        (conflict_key,),
                        0,
                    )
                )
                demographic_metadata[civilization.civilization_id] = (
                    settlement_id,
                    scarcity_ppm,
                )
            accepted_demographics, demographic_decisions = resolve_proposals(
                tuple(demographic_candidates)
            )
            proposal_decisions.extend(demographic_decisions)
            civilization_by_id = {item.civilization_id: item for item in ordered_civilizations}
            for demographic_proposal in accepted_demographics:
                civilization = civilization_by_id[demographic_proposal.actor_id]
                settlement_id, scarcity_ppm = demographic_metadata[civilization.civilization_id]
                sequence += 1
                event = _event(
                    state,
                    seed,
                    year,
                    month,
                    sequence,
                    demographic_proposal.kind,
                    demographic_proposal.participants,
                    demographic_proposal.locations,
                    demographic_proposal.consequences,
                    demographic_proposal.summary,
                    demographic_proposal.causes,
                )
                state = apply_event(state, event)
                ledger.append(event)
                batch.append(event)
                previous_by_civ[civilization.civilization_id] = event.event_id
            social_start_state = state
            social_previous_by_civ = dict(previous_by_civ)
            social_candidates: list[HistoryProposal] = []
            if month == 12:
                for civilization in sorted(
                    (item for item in social_start_state.civilizations if item.active),
                    key=lambda item: item.civilization_id,
                ):
                    current_cohorts = {
                        cohort.age_band: cohort
                        for cohort in social_start_state.cohorts
                        if cohort.civilization_id == civilization.civilization_id
                    }
                    child_to_adult = min(
                        current_cohorts["child"].population,
                        max(1, div_round_half_up(current_cohorts["child"].population, 20)),
                    )
                    adult_to_elder = min(
                        current_cohorts["adult"].population,
                        max(1, div_round_half_up(current_cohorts["adult"].population, 50)),
                    )
                    ageing_id = stable_id(
                        "history_proposal",
                        seed,
                        identity("ageing_year", year),
                        identity("civilization_id", civilization.civilization_id),
                    )
                    ageing_keys = tuple(
                        sorted(
                            f"social-cohort:{cohort.cohort_id}:{year:04d}"
                            for cohort in current_cohorts.values()
                        )
                    )
                    ageing_details = (
                        ("proposal_id", ageing_id),
                        ("conflict_keys", ",".join(ageing_keys)),
                        ("snapshot", f"{year:04d}:{month:02d}"),
                    )
                    ageing_consequences = tuple(
                        consequence
                        for consequence in (
                            Consequence(
                                ConsequenceKind.COHORT_TRANSFER,
                                current_cohorts["child"].cohort_id,
                                child_to_adult,
                                target=current_cohorts["adult"].cohort_id,
                                details=ageing_details,
                            ),
                            Consequence(
                                ConsequenceKind.COHORT_TRANSFER,
                                current_cohorts["adult"].cohort_id,
                                adult_to_elder,
                                target=current_cohorts["elder"].cohort_id,
                                details=ageing_details,
                            ),
                        )
                        if consequence.amount > 0
                    )
                    if ageing_consequences:
                        social_candidates.append(
                            HistoryProposal(
                                ageing_id,
                                year,
                                month,
                                EventKind.AGEING,
                                civilization.civilization_id,
                                (civilization.civilization_id,),
                                (civilization.capital_site_id,),
                                ageing_consequences,
                                "A conserved annual cohort aged from childhood to adulthood "
                                "and elderhood.",
                                (social_previous_by_civ[civilization.civilization_id],),
                                ageing_keys,
                                0,
                            )
                        )
                    if year % 5 == 0:
                        social_people = tuple(
                            person
                            for person in people_by_civ[civilization.civilization_id]
                            if person.person_id in living_person_ids
                        )
                        if year == 40:
                            deceased = min(social_people, key=lambda item: item.person_id)
                            death_id = stable_id(
                                "history_proposal",
                                seed,
                                identity("person_death_year", year),
                                identity("person_id", deceased.person_id),
                            )
                            death_keys = (f"social-person:{deceased.person_id}:{year:04d}",)
                            death_details = (
                                ("prior_status", "living"),
                                ("proposal_id", death_id),
                                ("conflict_keys", death_keys[0]),
                                ("snapshot", f"{year:04d}:{month:02d}"),
                            )
                            social_candidates.append(
                                HistoryProposal(
                                    death_id,
                                    year,
                                    month,
                                    EventKind.PERSON_STATUS,
                                    civilization.civilization_id,
                                    (deceased.person_id,),
                                    (civilization.capital_site_id,),
                                    (
                                        Consequence(
                                            ConsequenceKind.PERSON_STATUS_SET,
                                            deceased.person_id,
                                            value="dead",
                                            details=death_details,
                                        ),
                                    ),
                                    "A consequential person's death entered the public record.",
                                    (social_previous_by_civ[civilization.civilization_id],),
                                    death_keys,
                                    0,
                                )
                            )
                        relation_types = (
                            "spouse",
                            "parent_of",
                            "adopted_parent_of",
                            "disputed_parent_of",
                            "house_member",
                        )
                        relation_index = div_floor_exact(year, 5) - 1
                        source_person = social_people[relation_index % len(social_people)]
                        target_person = social_people[(relation_index + 1) % len(social_people)]
                        relation_type = relation_types[relation_index % len(relation_types)]
                        if (
                            relation_type in {"parent_of", "adopted_parent_of"}
                            and source_person.ordinal > target_person.ordinal
                        ):
                            source_person, target_person = target_person, source_person
                        relationship_id = stable_id(
                            "history_proposal",
                            seed,
                            identity("relationship_year", year),
                            identity("civilization_id", civilization.civilization_id),
                            identity("source_person_id", source_person.person_id),
                            identity("target_person_id", target_person.person_id),
                        )
                        relationship_keys = tuple(
                            sorted(
                                (
                                    f"social-house:{source_person.house_id}:{year:04d}",
                                    f"social-person:{source_person.person_id}:{year:04d}",
                                    f"social-person:{target_person.person_id}:{year:04d}",
                                )
                            )
                        )
                        relationship_details = (
                            ("house_id", source_person.house_id),
                            ("proposal_id", relationship_id),
                            ("conflict_keys", ",".join(relationship_keys)),
                            ("snapshot", f"{year:04d}:{month:02d}"),
                        )
                        social_candidates.append(
                            HistoryProposal(
                                relationship_id,
                                year,
                                month,
                                EventKind.RELATIONSHIP,
                                civilization.civilization_id,
                                (source_person.person_id, target_person.person_id),
                                (civilization.capital_site_id,),
                                (
                                    Consequence(
                                        ConsequenceKind.GENEALOGY_RELATION_ADD,
                                        source_person.person_id,
                                        target=target_person.person_id,
                                        value=relation_type,
                                        details=relationship_details,
                                    ),
                                ),
                                f"A consequential {relation_type} relationship was "
                                "publicly recorded.",
                                (social_previous_by_civ[civilization.civilization_id],),
                                relationship_keys,
                                1,
                            )
                        )
            accepted_social, social_decisions = resolve_proposals(tuple(social_candidates))
            proposal_decisions.extend(social_decisions)
            for accepted_social_proposal in accepted_social:
                sequence += 1
                social_event = _event(
                    state,
                    seed,
                    year,
                    month,
                    sequence,
                    accepted_social_proposal.kind,
                    accepted_social_proposal.participants,
                    accepted_social_proposal.locations,
                    accepted_social_proposal.consequences,
                    accepted_social_proposal.summary,
                    (previous_by_civ[accepted_social_proposal.actor_id],),
                )
                state = apply_event(state, social_event)
                ledger.append(social_event)
                batch.append(social_event)
                for consequence in social_event.consequences:
                    if (
                        consequence.kind is ConsequenceKind.PERSON_STATUS_SET
                        and consequence.value == "dead"
                    ):
                        living_person_ids.discard(consequence.subject)
                previous_by_civ[accepted_social_proposal.actor_id] = social_event.event_id
            risk_start_state = state
            risk_previous_by_civ = dict(previous_by_civ)
            risk_candidates: list[HistoryProposal] = []
            season_count = len(physical["climate_typed"].seasons)
            season_index = min(
                season_count - 1,
                div_floor_exact((month - 1) * season_count, 12),
            )
            risk_settlement_by_civ = {
                item.civilization_id: item for item in risk_start_state.settlements
            }
            for civilization in sorted(
                (item for item in risk_start_state.civilizations if item.active),
                key=lambda item: item.civilization_id,
            ):
                settlement = risk_settlement_by_civ[civilization.civilization_id]
                scarcity_ppm = min(
                    1_000_000,
                    div_round_half_up(
                        civilization.population * 1_000_000,
                        max(1, civilization.economy.grain),
                    ),
                )
                hazard_ppm = int(
                    physical["climate_typed"]
                    .seasons[season_index]
                    .hazard_ppm.values[site_by_id[civilization.capital_site_id].cell]
                )
                if _disaster_occurs(seed, civilization.civilization_id, year, month, hazard_ppm):
                    target_cohort = max(
                        (
                            cohort
                            for cohort in risk_start_state.cohorts
                            if cohort.civilization_id == civilization.civilization_id
                        ),
                        key=lambda cohort: (cohort.population, cohort.cohort_id),
                    )
                    available_materials = min(
                        civilization.economy.materials,
                        next(
                            (
                                stack.quantity
                                for stack in settlement.inventory
                                if stack.material_id == "materials"
                            ),
                            0,
                        ),
                    )
                    casualties, material_loss = _disaster_losses(
                        target_cohort.population,
                        available_materials,
                        hazard_ppm,
                    )
                    disaster_id = stable_id(
                        "history_proposal",
                        seed,
                        identity("risk_tick", f"{year:04d}:{month:02d}"),
                        identity("kind", EventKind.DISASTER.value),
                        identity("civilization_id", civilization.civilization_id),
                    )
                    disaster_keys = tuple(
                        sorted(
                            (
                                f"risk-material:{civilization.civilization_id}:{year:04d}:{month:02d}",
                                f"risk-population:{civilization.civilization_id}:{year:04d}:{month:02d}",
                            )
                        )
                    )
                    disaster_details = (
                        ("hazard_ppm", str(hazard_ppm)),
                        ("source_id", physical_ids["climate"]),
                        ("proposal_id", disaster_id),
                        ("conflict_keys", ",".join(disaster_keys)),
                    )
                    disaster_consequences = tuple(
                        item
                        for item in (
                            Consequence(
                                ConsequenceKind.POPULATION_DELTA,
                                civilization.civilization_id,
                                -casualties,
                                target=target_cohort.cohort_id,
                                details=disaster_details,
                            ),
                            Consequence(
                                ConsequenceKind.MATERIAL_DELTA,
                                civilization.civilization_id,
                                -material_loss,
                                details=disaster_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                settlement.settlement_id,
                                -material_loss,
                                target="materials",
                                details=disaster_details,
                            ),
                        )
                        if item.amount != 0
                    )
                    if disaster_consequences:
                        risk_candidates.append(
                            HistoryProposal(
                                disaster_id,
                                year,
                                month,
                                EventKind.DISASTER,
                                civilization.civilization_id,
                                (civilization.civilization_id,),
                                (civilization.capital_site_id,),
                                disaster_consequences,
                                "A climate-derived disaster caused bounded casualties and "
                                "material damage.",
                                (risk_previous_by_civ[civilization.civilization_id],),
                                disaster_keys,
                                0,
                            )
                        )
                stability_ppm = government_stability[civilization.government]
                if _crime_occurs(
                    seed, civilization.civilization_id, year, month, scarcity_ppm, stability_ppm
                ):
                    cohort_actors = sorted(
                        (
                            cohort
                            for cohort in risk_start_state.cohorts
                            if cohort.civilization_id == civilization.civilization_id
                            and cohort.population > 0
                        ),
                        key=lambda cohort: (cohort.age_band, cohort.cohort_id),
                    )
                    currency_loss = _crime_currency_loss(
                        civilization.economy.currency,
                        scarcity_ppm,
                    )
                    if len(cohort_actors) >= 2 and currency_loss:
                        actor_cohort, victim_cohort = cohort_actors[0], cohort_actors[-1]
                        crime_id = stable_id(
                            "history_proposal",
                            seed,
                            identity("risk_tick", f"{year:04d}:{month:02d}"),
                            identity("kind", EventKind.CRIME.value),
                            identity("civilization_id", civilization.civilization_id),
                        )
                        crime_keys = (
                            f"risk-currency:{civilization.civilization_id}:{year:04d}:{month:02d}",
                        )
                        crime_details = (
                            ("actor_cohort_id", actor_cohort.cohort_id),
                            ("victim_cohort_id", victim_cohort.cohort_id),
                            ("scarcity_ppm", str(scarcity_ppm)),
                            ("stability_ppm", str(stability_ppm)),
                            ("government_registry_id", civilization.government),
                            ("resolution", "restitution_and_public_censure"),
                            ("proposal_id", crime_id),
                            ("conflict_keys", ",".join(crime_keys)),
                        )
                        risk_candidates.append(
                            HistoryProposal(
                                crime_id,
                                year,
                                month,
                                EventKind.CRIME,
                                civilization.civilization_id,
                                (actor_cohort.cohort_id, victim_cohort.cohort_id),
                                (civilization.capital_site_id,),
                                (
                                    Consequence(
                                        ConsequenceKind.CURRENCY_DELTA,
                                        civilization.civilization_id,
                                        -currency_loss,
                                        target=victim_cohort.cohort_id,
                                        value="institutional_resolution_cost",
                                        details=crime_details,
                                    ),
                                ),
                                "Scarcity-driven theft incurred a bounded institutional "
                                "resolution cost.",
                                (risk_previous_by_civ[civilization.civilization_id],),
                                crime_keys,
                                1,
                            )
                        )
            accepted_risks, risk_decisions = resolve_proposals(tuple(risk_candidates))
            proposal_decisions.extend(risk_decisions)
            for accepted_risk in accepted_risks:
                sequence += 1
                risk_event = _event(
                    state,
                    seed,
                    year,
                    month,
                    sequence,
                    accepted_risk.kind,
                    accepted_risk.participants,
                    accepted_risk.locations,
                    accepted_risk.consequences,
                    accepted_risk.summary,
                    accepted_risk.causes,
                )
                state = apply_event(state, risk_event)
                ledger.append(risk_event)
                batch.append(risk_event)
                previous_by_civ[accepted_risk.actor_id] = risk_event.event_id
            trade_start_state = state
            active = sorted(
                (item for item in trade_start_state.civilizations if item.active),
                key=lambda item: item.civilization_id,
            )
            if month == 12 and len(active) > 1:
                trade_previous_by_civ = dict(previous_by_civ)
                settlement_state_by_civ = {
                    item.civilization_id: item for item in trade_start_state.settlements
                }
                trade_candidates: list[HistoryProposal] = []
                for seller in active:
                    for buyer in active:
                        surplus = seller.economy.grain - buyer.economy.grain
                        if seller.civilization_id == buyer.civilization_id or surplus <= 0:
                            continue
                        seller_region = site_by_id[seller.capital_site_id].region_id
                        buyer_region = site_by_id[buyer.capital_site_id].region_id
                        plan = _route_transport_plan(routes, seller_region, buyer_region, 3)
                        if plan is None:
                            continue
                        route_ids, transport_capacity, maintenance = plan
                        seller_settlement = settlement_state_by_civ[seller.civilization_id]
                        buyer_settlement = settlement_state_by_civ[buyer.civilization_id]
                        seller_grain = next(
                            (
                                item.quantity
                                for item in seller_settlement.inventory
                                if item.material_id == "grain"
                            ),
                            0,
                        )
                        desired_amount = min(100, div_round_half_up(seller.economy.grain, 20))
                        amount = min(
                            desired_amount, transport_capacity, seller_grain, buyer.economy.currency
                        )
                        if amount <= 0:
                            continue
                        proposal_id = stable_id(
                            "history_proposal",
                            seed,
                            identity("trade_tick", f"{year:04d}:{month:02d}"),
                            identity("seller_id", seller.civilization_id),
                            identity("buyer_id", buyer.civilization_id),
                        )
                        conflict_keys = tuple(
                            sorted(
                                (
                                    f"trade-buyer:{buyer.civilization_id}:{year:04d}:{month:02d}",
                                    f"trade-seller:{seller.civilization_id}:{year:04d}:{month:02d}",
                                )
                                + tuple(
                                    f"trade-route:{route_id}:{year:04d}:{month:02d}"
                                    for route_id in route_ids
                                )
                            )
                        )
                        trade_details = (
                            ("route_ids", ",".join(route_ids)),
                            ("transport_capacity", str(transport_capacity)),
                            ("maintenance", str(maintenance)),
                            ("proposal_id", proposal_id),
                            ("conflict_keys", ",".join(conflict_keys)),
                        )
                        trade_consequences = (
                            Consequence(
                                ConsequenceKind.GRAIN_DELTA,
                                seller.civilization_id,
                                -amount,
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.GRAIN_DELTA,
                                buyer.civilization_id,
                                amount,
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.CURRENCY_DELTA,
                                seller.civilization_id,
                                amount,
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.CURRENCY_DELTA,
                                buyer.civilization_id,
                                -amount,
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                seller_settlement.settlement_id,
                                -amount,
                                target="grain",
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                buyer_settlement.settlement_id,
                                amount,
                                target="grain",
                                details=trade_details,
                            ),
                            Consequence(
                                ConsequenceKind.ECONOMY_LEDGER_APPEND,
                                seller_settlement.settlement_id,
                                amount,
                                target="grain",
                                value="trade",
                                details=trade_details,
                            ),
                        )
                        priority = max(0, 2_147_483_647 - surplus)
                        trade_candidates.append(
                            HistoryProposal(
                                proposal_id,
                                year,
                                month,
                                EventKind.TRADE,
                                seller.civilization_id,
                                (seller.civilization_id, buyer.civilization_id),
                                (seller.capital_site_id, buyer.capital_site_id),
                                trade_consequences,
                                "A capacity-bounded route grain exchange completed.",
                                tuple(
                                    sorted(
                                        {
                                            trade_previous_by_civ[seller.civilization_id],
                                            trade_previous_by_civ[buyer.civilization_id],
                                        }
                                    )
                                ),
                                conflict_keys,
                                priority,
                            )
                        )
                accepted_trades, trade_decisions = resolve_proposals(tuple(trade_candidates))
                proposal_decisions.extend(trade_decisions)
                for accepted_trade in accepted_trades:
                    sequence += 1
                    trade = _event(
                        state,
                        seed,
                        year,
                        month,
                        sequence,
                        accepted_trade.kind,
                        accepted_trade.participants,
                        accepted_trade.locations,
                        accepted_trade.consequences,
                        accepted_trade.summary,
                        accepted_trade.causes,
                    )
                    state = apply_event(state, trade)
                    ledger.append(trade)
                    batch.append(trade)
                    for participant in accepted_trade.participants:
                        previous_by_civ[participant] = trade.event_id
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(
                bytes.fromhex(prior_prefix) + canonical_json(tuple(batch))
            ).hexdigest()
            batch_artifact = WorldArtifact.build(
                f"history_{year:04d}_{month:02d}",
                {
                    "events": tuple(batch),
                    "previous_prefix": prior_prefix,
                    "prefix_sha256": prefix_digest,
                },
                depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                producer_fingerprint=history_producer,
            )
            repository.put(batch_artifact)
            previous_batch_id = batch_artifact.artifact_id
        annual_batch: list[HistoryEvent] = []
        annual_start_state = state
        annual_previous_by_civ = dict(previous_by_civ)
        annual_candidates: list[HistoryProposal] = []
        if year % 5 == 0 and len(state.civilizations) > 1:
            ordered = sorted(
                annual_start_state.civilizations, key=lambda c: (c.population, c.civilization_id)
            )
            source_civ, target_civ = ordered[-1], ordered[0]
            migrants = min(25, div_round_half_up(source_civ.population, 100))
            if migrants:
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("annual_tick", f"{year:04d}:12"),
                    identity("kind", EventKind.MIGRATION.value),
                    identity("source_id", source_civ.civilization_id),
                    identity("target_id", target_civ.civilization_id),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"annual-population:{source_civ.civilization_id}:{year:04d}",
                            f"annual-population:{target_civ.civilization_id}:{year:04d}",
                        )
                    )
                )
                migration_details = (
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                annual_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.MIGRATION,
                        source_civ.civilization_id,
                        (source_civ.civilization_id, target_civ.civilization_id),
                        (source_civ.capital_site_id, target_civ.capital_site_id),
                        (
                            Consequence(
                                ConsequenceKind.POPULATION_DELTA,
                                source_civ.civilization_id,
                                -migrants,
                                details=migration_details,
                            ),
                            Consequence(
                                ConsequenceKind.POPULATION_DELTA,
                                target_civ.civilization_id,
                                migrants,
                                details=migration_details,
                            ),
                        ),
                        "A conserved cohort migrated between settlements.",
                        tuple(
                            sorted(
                                {
                                    annual_previous_by_civ[source_civ.civilization_id],
                                    annual_previous_by_civ[target_civ.civilization_id],
                                }
                            )
                        ),
                        conflict_keys,
                        0,
                    )
                )
        if year % 25 == 0 and len(state.civilizations) > 1:
            left, right = sorted(annual_start_state.civilizations, key=lambda c: c.civilization_id)[
                :2
            ]
            relation = next(
                r
                for r in annual_start_state.relations
                if r.left == left.civilization_id and r.right == right.civilization_id
            )
            transitions = {
                "neutral": ("rivalry", EventKind.DIPLOMACY),
                "rivalry": ("alliance", EventKind.DIPLOMACY),
                "alliance": ("war", EventKind.WAR),
                "war": ("peace", EventKind.PEACE),
                "peace": ("alliance", EventKind.DIPLOMACY),
            }
            new_status, diplomatic_kind = transitions[relation.status]
            proposal_id = stable_id(
                "history_proposal",
                seed,
                identity("annual_tick", f"{year:04d}:12"),
                identity("kind", diplomatic_kind.value),
                identity("left_id", left.civilization_id),
                identity("right_id", right.civilization_id),
            )
            conflict_key_items = [
                f"annual-relation:{left.civilization_id}:{right.civilization_id}:{year:04d}",
            ]
            if new_status == "war":
                conflict_key_items.extend(
                    (
                        f"annual-material:{left.civilization_id}:{year:04d}",
                        f"annual-material:{right.civilization_id}:{year:04d}",
                    )
                )
                if right.territory:
                    conflict_key_items.append(f"annual-territory:{right.territory[-1]}:{year:04d}")
            conflict_keys = tuple(sorted(conflict_key_items))
            diplomatic_details = (
                ("prior_status", relation.status),
                ("new_status", new_status),
                ("proposal_id", proposal_id),
                ("conflict_keys", ",".join(conflict_keys)),
                ("snapshot", f"{year:04d}:12"),
            )
            consequences = [
                Consequence(
                    ConsequenceKind.RELATION_SET,
                    left.civilization_id,
                    100_000
                    if new_status == "war"
                    else 700_000
                    if new_status == "alliance"
                    else 500_000,
                    right.civilization_id,
                    new_status,
                    details=diplomatic_details,
                )
            ]
            if new_status == "war":
                consequences.extend(
                    (
                        Consequence(
                            ConsequenceKind.MATERIAL_DELTA,
                            left.civilization_id,
                            -min(100, left.economy.materials),
                            details=diplomatic_details,
                        ),
                        Consequence(
                            ConsequenceKind.MATERIAL_DELTA,
                            right.civilization_id,
                            -min(100, right.economy.materials),
                            details=diplomatic_details,
                        ),
                    )
                )
            annual_candidates.append(
                HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    diplomatic_kind,
                    left.civilization_id,
                    (left.civilization_id, right.civilization_id),
                    (left.capital_site_id, right.capital_site_id),
                    tuple(consequences),
                    f"The polities entered {new_status}.",
                    tuple(
                        sorted(
                            {
                                annual_previous_by_civ[left.civilization_id],
                                annual_previous_by_civ[right.civilization_id],
                            }
                        )
                    ),
                    conflict_keys,
                    0,
                )
            )
        accepted_annual, annual_decisions = resolve_proposals(tuple(annual_candidates))
        proposal_decisions.extend(annual_decisions)
        for accepted_proposal in accepted_annual:
            sequence += 1
            annual_event = _event(
                state,
                seed,
                year,
                12,
                sequence,
                accepted_proposal.kind,
                accepted_proposal.participants,
                accepted_proposal.locations,
                accepted_proposal.consequences,
                accepted_proposal.summary,
                accepted_proposal.causes,
            )
            state = apply_event(state, annual_event)
            ledger.append(annual_event)
            annual_batch.append(annual_event)
            for participant in accepted_proposal.participants:
                previous_by_civ[participant] = annual_event.event_id
            event_details = dict(accepted_proposal.consequences[0].details)
            if accepted_proposal.kind is EventKind.WAR and event_details["new_status"] == "war":
                defender = accepted_proposal.participants[1]
                defender_snapshot = next(
                    civilization
                    for civilization in annual_start_state.civilizations
                    if civilization.civilization_id == defender
                )
                if not defender_snapshot.territory:
                    continue
                conquered = defender_snapshot.territory[-1]
                sequence += 1
                conquest = _event(
                    state,
                    seed,
                    year,
                    12,
                    sequence,
                    EventKind.CONQUEST,
                    accepted_proposal.participants,
                    accepted_proposal.locations,
                    (
                        Consequence(
                            ConsequenceKind.TERRITORY_TRANSFER,
                            defender,
                            -1,
                            value=conquered,
                            details=accepted_proposal.consequences[0].details,
                        ),
                        Consequence(
                            ConsequenceKind.TERRITORY_TRANSFER,
                            accepted_proposal.actor_id,
                            1,
                            value=conquered,
                            details=accepted_proposal.consequences[0].details,
                        ),
                    ),
                    "A victorious polity seized territory after the war.",
                    (annual_event.event_id,),
                )
                state = apply_event(state, conquest)
                ledger.append(conquest)
                annual_batch.append(conquest)
                for participant in accepted_proposal.participants:
                    previous_by_civ[participant] = conquest.event_id
        institutional_start_state = state
        institutional_previous_by_civ = dict(previous_by_civ)
        institutional_candidates: list[HistoryProposal] = []
        if year % 200 == 0:
            actor = min(
                (c for c in institutional_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            settlement_id = settlement_by_civ[actor.civilization_id]
            proposal_id = stable_id(
                "history_proposal",
                seed,
                identity("institutional_year", year),
                identity("kind", EventKind.COLLAPSE.value),
                identity("civilization_id", actor.civilization_id),
            )
            conflict_keys = tuple(
                sorted(
                    (
                        f"institution-polity:{actor.civilization_id}:{year:04d}",
                        f"institution-settlement:{settlement_id}:{year:04d}",
                    )
                )
            )
            lifecycle_details: tuple[tuple[str, str], ...] = (
                ("prior_polity_state", "active"),
                ("new_polity_state", "inactive"),
                ("prior_settlement_status", SettlementStatus.INHABITED.value),
                ("new_settlement_status", SettlementStatus.ABANDONED.value),
                ("settlement_id", settlement_id),
                ("proposal_id", proposal_id),
                ("conflict_keys", ",".join(conflict_keys)),
                ("snapshot", f"{year:04d}:12"),
            )
            institutional_candidates.append(
                HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.COLLAPSE,
                    actor.civilization_id,
                    (actor.civilization_id,),
                    (actor.capital_site_id,),
                    (
                        Consequence(
                            ConsequenceKind.ACTIVE_SET,
                            actor.civilization_id,
                            value="inactive",
                            details=lifecycle_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_STATUS_SET,
                            settlement_id,
                            value=SettlementStatus.ABANDONED.value,
                            details=lifecycle_details,
                        ),
                    ),
                    "Scarcity and institutional failure caused a polity collapse.",
                    (institutional_previous_by_civ[actor.civilization_id],),
                    conflict_keys,
                    0,
                )
            )
        if year % 200 == 10:
            inactive = sorted(
                (c for c in institutional_start_state.civilizations if not c.active),
                key=lambda c: c.civilization_id,
            )
            if inactive:
                actor = inactive[0]
                settlement_id = settlement_by_civ[actor.civilization_id]
                collapse_event_id = last_collapse_by_civ[actor.civilization_id]
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("institutional_year", year),
                    identity("kind", EventKind.RECOVERY.value),
                    identity("civilization_id", actor.civilization_id),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"institution-polity:{actor.civilization_id}:{year:04d}",
                            f"institution-settlement:{settlement_id}:{year:04d}",
                        )
                    )
                )
                lifecycle_details = (
                    ("prior_polity_state", "inactive"),
                    ("new_polity_state", "active"),
                    ("prior_settlement_status", SettlementStatus.ABANDONED.value),
                    ("new_settlement_status", SettlementStatus.INHABITED.value),
                    ("settlement_id", settlement_id),
                    ("collapse_event_id", collapse_event_id),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                institutional_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.RECOVERY,
                        actor.civilization_id,
                        (actor.civilization_id,),
                        (actor.capital_site_id,),
                        (
                            Consequence(
                                ConsequenceKind.ACTIVE_SET,
                                actor.civilization_id,
                                value="active",
                                details=lifecycle_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_STATUS_SET,
                                settlement_id,
                                value=SettlementStatus.INHABITED.value,
                                details=lifecycle_details,
                            ),
                        ),
                        "Local institutions restored the collapsed polity.",
                        (collapse_event_id,),
                        conflict_keys,
                        0,
                    )
                )
        if year % 30 == 0:
            actor = min(
                (c for c in institutional_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            social_people = people_by_civ[actor.civilization_id]
            claim = next(
                event
                for event in reversed(ledger)
                if event.kind is EventKind.RELATIONSHIP
                and all(
                    person_id in {item.person_id for item in social_people}
                    for person_id in event.participants
                )
            )
            claim_consequence = next(
                item
                for item in claim.consequences
                if item.kind is ConsequenceKind.GENEALOGY_RELATION_ADD
            )
            outgoing = next(
                item for item in social_people if item.person_id == claim_consequence.subject
            )
            incoming = next(
                item for item in social_people if item.person_id == claim_consequence.target
            )
            proposal_id = stable_id(
                "history_proposal",
                seed,
                identity("institutional_year", year),
                identity("kind", EventKind.SUCCESSION.value),
                identity("civilization_id", actor.civilization_id),
            )
            conflict_keys = tuple(
                sorted(
                    (
                        f"institution-currency:{actor.civilization_id}:{year:04d}",
                        f"institution-office:{actor.civilization_id}:{year:04d}",
                        f"institution-person:{incoming.person_id}:{year:04d}",
                        f"institution-person:{outgoing.person_id}:{year:04d}",
                        f"institution-polity:{actor.civilization_id}:{year:04d}",
                    )
                )
            )
            succession_details = (
                ("house_id", outgoing.house_id),
                ("claim_event_id", claim.event_id),
                ("claim_type", claim_consequence.value),
                ("proposal_id", proposal_id),
                ("conflict_keys", ",".join(conflict_keys)),
                ("snapshot", f"{year:04d}:12"),
            )
            institutional_candidates.append(
                HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.SUCCESSION,
                    actor.civilization_id,
                    (outgoing.person_id, incoming.person_id),
                    (actor.capital_site_id,),
                    (
                        Consequence(
                            ConsequenceKind.CURRENCY_DELTA,
                            actor.civilization_id,
                            -5,
                            details=succession_details,
                        ),
                        Consequence(
                            ConsequenceKind.OFFICEHOLDER_SET,
                            actor.civilization_id,
                            target=incoming.person_id,
                            value=outgoing.person_id,
                            details=succession_details,
                        ),
                        Consequence(
                            ConsequenceKind.INHERITANCE_TRANSFER,
                            outgoing.person_id,
                            target=incoming.person_id,
                            value=outgoing.house_id,
                            details=succession_details,
                        ),
                    ),
                    "A named officeholder succeeded through a recorded social claim.",
                    (claim.event_id,),
                    conflict_keys,
                    0,
                )
            )
        if year % 25 == 0:
            eligible_reformers = sorted(
                (
                    c
                    for c in institutional_start_state.civilizations
                    if c.active and c.economy.currency >= 5
                ),
                key=lambda c: c.civilization_id,
            )
            government_entries = simulation_registry_entries("governments")
            if eligible_reformers:
                actor = eligible_reformers[0]
                alternatives = sorted(
                    (item for item in government_entries if str(item["id"]) != actor.government),
                    key=lambda item: (
                        -int(cast(int, item["stability_ppm"])),
                        str(item["id"]),
                    ),
                )
            else:
                alternatives = []
            if alternatives:
                next_government = str(alternatives[0]["id"])
                capacity = capacity_by_civ[actor.civilization_id]
                scarcity_ppm = max(
                    0,
                    min(
                        1_000_000,
                        div_round_half_up(
                            max(0, actor.population - capacity) * 1_000_000,
                            max(1, capacity),
                        ),
                    ),
                )
                stability_ppm = government_stability[actor.government]
                pressure_kind, pressure_ppm = (
                    ("scarcity", scarcity_ppm)
                    if scarcity_ppm
                    else ("instability", 1_000_000 - stability_ppm)
                )
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("institutional_year", year),
                    identity("kind", EventKind.REFORM.value),
                    identity("civilization_id", actor.civilization_id),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"institution-currency:{actor.civilization_id}:{year:04d}",
                            f"institution-government:{actor.civilization_id}:{year:04d}",
                            f"institution-polity:{actor.civilization_id}:{year:04d}",
                        )
                    )
                )
                reform_details = (
                    ("pressure_kind", pressure_kind),
                    ("pressure_ppm", str(pressure_ppm)),
                    ("prior_government", actor.government),
                    ("new_government", next_government),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                institutional_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.REFORM,
                        actor.civilization_id,
                        (actor.civilization_id,),
                        (actor.capital_site_id,),
                        (
                            Consequence(
                                ConsequenceKind.CURRENCY_DELTA,
                                actor.civilization_id,
                                -5,
                                details=reform_details,
                            ),
                            Consequence(
                                ConsequenceKind.GOVERNMENT_SET,
                                actor.civilization_id,
                                target=next_government,
                                value=actor.government,
                                details=reform_details,
                            ),
                        ),
                        "A deterministic reform proposal was supplied and resolved.",
                        (institutional_previous_by_civ[actor.civilization_id],),
                        conflict_keys,
                        0,
                    )
                )
        accepted_institutional, institutional_decisions = resolve_proposals(
            tuple(institutional_candidates)
        )
        proposal_decisions.extend(institutional_decisions)
        for accepted_proposal in accepted_institutional:
            sequence += 1
            institutional_event = _event(
                state,
                seed,
                year,
                12,
                sequence,
                accepted_proposal.kind,
                accepted_proposal.participants,
                accepted_proposal.locations,
                accepted_proposal.consequences,
                accepted_proposal.summary,
                accepted_proposal.causes,
            )
            state = apply_event(state, institutional_event)
            ledger.append(institutional_event)
            annual_batch.append(institutional_event)
            previous_by_civ[accepted_proposal.actor_id] = institutional_event.event_id
            if accepted_proposal.kind is EventKind.COLLAPSE:
                last_collapse_by_civ[accepted_proposal.actor_id] = institutional_event.event_id
        knowledge_start_state = state
        knowledge_previous_by_civ = dict(previous_by_civ)
        knowledge_candidates: list[HistoryProposal] = []
        if year % 20 == 0:
            previously_discovered = {
                item.target
                for event in ledger
                for item in event.consequences
                if item.kind is ConsequenceKind.REGION_DISCOVERY_ADD
            }
            owned_regions = {
                region
                for civilization in knowledge_start_state.civilizations
                for region in civilization.territory
            }
            destinations = sorted(
                str(region["region_id"])
                for region in physical["regions"]["regions"]
                if str(region["region_id"]) not in owned_regions
                and str(region["region_id"]) not in previously_discovered
            )
            exploration_choice = None
            for candidate_actor in sorted(
                (
                    c
                    for c in knowledge_start_state.civilizations
                    if c.active and c.economy.currency >= 10
                ),
                key=lambda c: c.civilization_id,
            ):
                candidate_origin = site_by_id[candidate_actor.capital_site_id].region_id
                reachable = next(
                    (
                        (destination, plan)
                        for destination in destinations
                        if (
                            plan := _route_transport_plan(
                                routes,
                                candidate_origin,
                                destination,
                                3,
                            )
                        )
                        is not None
                    ),
                    None,
                )
                if reachable is not None:
                    exploration_choice = (candidate_actor, candidate_origin, reachable)
                    break
            if exploration_choice is not None:
                actor, origin_region, reachable = exploration_choice
                destination, plan = reachable
                route_ids = plan[0]
                settlement_id = settlement_by_civ[actor.civilization_id]
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("knowledge_year", year),
                    identity("kind", EventKind.EXPLORATION.value),
                    identity("civilization_id", actor.civilization_id),
                    identity("destination_id", destination),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"knowledge-currency:{actor.civilization_id}:{year:04d}",
                            f"knowledge-destination:{destination}:{year:04d}",
                        )
                        + tuple(f"knowledge-route:{route_id}:{year:04d}" for route_id in route_ids)
                    )
                )
                exploration_details = (
                    ("origin_region_id", origin_region),
                    ("route_ids", ",".join(route_ids)),
                    ("currency_cost", "10"),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                knowledge_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.EXPLORATION,
                        actor.civilization_id,
                        (actor.civilization_id,),
                        (actor.capital_site_id,),
                        (
                            Consequence(
                                ConsequenceKind.CURRENCY_DELTA,
                                actor.civilization_id,
                                -10,
                                details=exploration_details,
                            ),
                            Consequence(
                                ConsequenceKind.REGION_DISCOVERY_ADD,
                                actor.civilization_id,
                                target=destination,
                                value=settlement_id,
                                details=exploration_details,
                            ),
                        ),
                        "A deterministic exploration proposal was supplied and resolved.",
                        (knowledge_previous_by_civ[actor.civilization_id],),
                        conflict_keys,
                        0,
                    )
                )
        if year % 50 == 0:
            actor = min(
                (c for c in knowledge_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            technologies = sorted(
                simulation_registry_entries("technologies"), key=lambda item: str(item["id"])
            )
            known = set(actor.capabilities)
            technology = next(
                (
                    item
                    for item in technologies
                    if str(item["id"]) not in known
                    and set(
                        str(required) for required in cast(tuple[object, ...], item["requires"])
                    )
                    <= known
                ),
                None,
            )
            if technology is not None and actor.economy.materials >= 15:
                settlement_id = settlement_by_civ[actor.civilization_id]
                settlement = next(
                    item
                    for item in knowledge_start_state.settlements
                    if item.settlement_id == settlement_id
                )
                workshop_id = min(item.workshop_id for item in settlement.workshops)
                prerequisites = tuple(
                    str(item) for item in cast(tuple[object, ...], technology["requires"])
                )
                technology_id = str(technology["id"])
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("knowledge_year", year),
                    identity("kind", EventKind.TECHNOLOGY.value),
                    identity("civilization_id", actor.civilization_id),
                    identity("technology_id", technology_id),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"knowledge-capability:{actor.civilization_id}:{technology_id}:{year:04d}",
                            f"knowledge-material:{actor.civilization_id}:{year:04d}",
                            f"knowledge-workshop:{workshop_id}:{year:04d}",
                        )
                    )
                )
                technology_details = (
                    ("settlement_id", settlement_id),
                    ("workshop_id", workshop_id),
                    ("prerequisites", ",".join(prerequisites)),
                    ("material_cost", "15"),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                knowledge_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.TECHNOLOGY,
                        actor.civilization_id,
                        (actor.civilization_id,),
                        (actor.capital_site_id,),
                        (
                            Consequence(
                                ConsequenceKind.MATERIAL_DELTA,
                                actor.civilization_id,
                                -15,
                                details=technology_details,
                            ),
                            Consequence(
                                ConsequenceKind.CAPABILITY_ADD,
                                actor.civilization_id,
                                target=technology_id,
                                value=workshop_id,
                                details=technology_details,
                            ),
                        ),
                        "A deterministic technology proposal was supplied and resolved.",
                        (knowledge_previous_by_civ[actor.civilization_id],),
                        conflict_keys,
                        0,
                    )
                )
        accepted_knowledge, knowledge_decisions = resolve_proposals(tuple(knowledge_candidates))
        proposal_decisions.extend(knowledge_decisions)
        for accepted_proposal in accepted_knowledge:
            sequence += 1
            knowledge_event = _event(
                state,
                seed,
                year,
                12,
                sequence,
                accepted_proposal.kind,
                accepted_proposal.participants,
                accepted_proposal.locations,
                accepted_proposal.consequences,
                accepted_proposal.summary,
                accepted_proposal.causes,
            )
            state = apply_event(state, knowledge_event)
            ledger.append(knowledge_event)
            annual_batch.append(knowledge_event)
            previous_by_civ[accepted_proposal.actor_id] = knowledge_event.event_id
        proposal_schedule = ((40, EventKind.CONSTRUCTION, ConsequenceKind.MATERIAL_DELTA, -20),)
        for interval, proposal_kind, consequence_kind, amount in proposal_schedule:
            if year % interval:
                continue
            actor = min(
                (c for c in state.civilizations if c.active), key=lambda c: c.civilization_id
            )
            sequence += 1
            consequences = [Consequence(consequence_kind, actor.civilization_id, amount)]
            proposal_participants: tuple[str, ...] = (actor.civilization_id,)
            proposal_locations: tuple[str, ...] = (actor.capital_site_id,)
            proposal_summary = (
                f"A deterministic {proposal_kind.value} proposal was supplied and resolved."
            )
            proposal_causes: tuple[str, ...] = (previous_by_civ[actor.civilization_id],)
            if proposal_kind is EventKind.CONSTRUCTION:
                actor = min(
                    (item for item in annual_start_state.civilizations if item.active),
                    key=lambda item: item.civilization_id,
                )
                settlement_id = settlement_by_civ[actor.civilization_id]
                settlement = next(
                    item
                    for item in annual_start_state.settlements
                    if item.settlement_id == settlement_id
                )
                inventory = {item.material_id: item.quantity for item in settlement.inventory}
                if actor.economy.materials < 20 or inventory.get("materials", 0) < 20:
                    continue
                candidates: list[HistoryProposal] = []
                for addressed_need in actor.needs:
                    building, workshop_kind = {
                        "grain": ("grain exchange", "milling kitchen"),
                        "materials": ("masonry storehouse", "masonry kitchen"),
                        "shelter": ("communal hall", "hall kitchen"),
                    }.get(addressed_need, ("communal storehouse", "communal kitchen"))
                    proposal_id = stable_id(
                        "history_proposal",
                        seed,
                        identity("settlement_id", settlement_id),
                        identity("construction_year", year),
                        identity("addressed_need", addressed_need),
                    )
                    project_id = stable_id(
                        "construction_project",
                        seed,
                        identity("settlement_id", settlement_id),
                        identity("construction_year", year),
                        identity("addressed_need", addressed_need),
                    )
                    workshop_id = stable_id(
                        "workshop",
                        seed,
                        identity("settlement_id", settlement_id),
                        identity("recipe_id", "food"),
                        identity("construction_year", year),
                    )
                    conflict_key = f"construction-slot:{settlement_id}:{year}"
                    project_details = (
                        ("project_id", project_id),
                        ("addressed_need", addressed_need),
                        ("material_cost", "20"),
                        ("workshop_id", workshop_id),
                        ("proposal_id", proposal_id),
                        ("conflict_key", conflict_key),
                    )
                    priority = div_floor_exact(
                        inventory.get(addressed_need, 0) * 1_000_000,
                        max(1, settlement.population),
                    )
                    candidate_consequences = (
                        Consequence(
                            consequence_kind, actor.civilization_id, amount, details=project_details
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                            settlement_id,
                            -20,
                            target="materials",
                            details=project_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_BUILDING_ADD,
                            settlement_id,
                            value=building,
                            details=project_details,
                        ),
                        Consequence(
                            ConsequenceKind.SETTLEMENT_WORKSHOP_ADD,
                            settlement_id,
                            value=(f"{workshop_id}|{workshop_kind}|food|grain|food|800000"),
                            details=project_details,
                        ),
                    )
                    candidates.append(
                        HistoryProposal(
                            proposal_id,
                            year,
                            12,
                            EventKind.CONSTRUCTION,
                            actor.civilization_id,
                            (actor.civilization_id,),
                            (actor.capital_site_id,),
                            candidate_consequences,
                            "A need-driven construction proposal was accepted.",
                            (annual_previous_by_civ[actor.civilization_id],),
                            (conflict_key,),
                            priority,
                        )
                    )
                accepted, decisions = resolve_proposals(tuple(candidates))
                proposal_decisions.extend(decisions)
                if len(accepted) != 1:
                    raise ValueError("WG-PROPOSAL-CONSTRUCTION: expected one accepted proposal")
                selected = accepted[0]
                consequences = list(selected.consequences)
                proposal_participants = selected.participants
                proposal_locations = selected.locations
                proposal_summary = selected.summary
                proposal_causes = selected.causes
            proposal = _event(
                state,
                seed,
                year,
                12,
                sequence,
                proposal_kind,
                proposal_participants,
                proposal_locations,
                tuple(consequences),
                proposal_summary,
                proposal_causes,
            )
            state = apply_event(state, proposal)
            ledger.append(proposal)
            annual_batch.append(proposal)
        content_start_state = state
        content_previous_by_civ = dict(previous_by_civ)
        content_candidates: list[HistoryProposal] = []
        if year % 50 == 0:
            actor = min(
                (c for c in content_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            settlement_id = settlement_by_civ[actor.civilization_id]
            settlement = next(
                item
                for item in content_start_state.settlements
                if item.settlement_id == settlement_id
            )
            material_stack = next(
                (stack for stack in settlement.inventory if stack.material_id == "materials"), None
            )
            if material_stack is not None and material_stack.quantity >= 5:
                workshop_id = min(workshop.workshop_id for workshop in settlement.workshops)
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("content_year", year),
                    identity("kind", EventKind.COMMISSION.value),
                    identity("civilization_id", actor.civilization_id),
                )
                conflict_keys = tuple(
                    sorted(
                        (
                            f"content-material:{actor.civilization_id}:{year:04d}",
                            f"content-inventory:{settlement_id}:materials:{year:04d}",
                            f"content-workshop:{workshop_id}:{year:04d}",
                        )
                    )
                )
                commission_details = (
                    ("artifact_class", "legendary"),
                    ("material_id", "stone"),
                    ("workshop_id", workshop_id),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", ",".join(conflict_keys)),
                    ("snapshot", f"{year:04d}:12"),
                )
                artifact_id = stable_id(
                    "legendary_artifact",
                    seed,
                    identity("proposal_id", proposal_id),
                )
                creator = min(
                    people_by_civ[actor.civilization_id],
                    key=lambda item: item.person_id,
                )
                content_candidates.append(
                    HistoryProposal(
                        proposal_id,
                        year,
                        12,
                        EventKind.COMMISSION,
                        actor.civilization_id,
                        (actor.civilization_id,),
                        (actor.capital_site_id,),
                        (
                            Consequence(
                                ConsequenceKind.MATERIAL_DELTA,
                                actor.civilization_id,
                                -5,
                                details=commission_details,
                            ),
                            Consequence(
                                ConsequenceKind.SETTLEMENT_INVENTORY_DELTA,
                                settlement_id,
                                -5,
                                target="materials",
                                details=commission_details,
                            ),
                            Consequence(
                                ConsequenceKind.ARTIFACT_CREATE,
                                artifact_id,
                                target=creator.person_id,
                                value=actor.capital_site_id,
                                details=commission_details,
                            ),
                        ),
                        "A rare masterwork commission consumed material and succeeded.",
                        (content_previous_by_civ[actor.civilization_id],),
                        conflict_keys,
                        0,
                    )
                )
        if year % 15 == 0:
            actor = min(
                (c for c in content_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            religions = cast(tuple[Religion, ...], identities["religions"])
            institutions = cast(
                tuple[ReligiousInstitution, ...], identities["religious_institutions"]
            )
            religion = sorted(religions, key=lambda item: item.religion_id)[
                (div_floor_exact(year, 15) - 1) % len(religions)
            ]
            institution = next(
                item for item in institutions if item.religion_id == religion.religion_id
            )
            proposal_id = stable_id(
                "history_proposal",
                seed,
                identity("content_year", year),
                identity("kind", EventKind.RELIGION.value),
                identity("institution_id", institution.institution_id),
            )
            conflict_keys = tuple(
                sorted(
                    (
                        f"content-currency:{actor.civilization_id}:{year:04d}",
                        f"content-institution:{institution.institution_id}:{year:04d}",
                    )
                )
            )
            patronage_details = (
                ("holy_site_id", religion.holy_site_id),
                ("proposal_id", proposal_id),
                ("conflict_keys", ",".join(conflict_keys)),
                ("snapshot", f"{year:04d}:12"),
            )
            content_candidates.append(
                HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.RELIGION,
                    actor.civilization_id,
                    (actor.civilization_id,),
                    (religion.holy_site_id,),
                    (
                        Consequence(
                            ConsequenceKind.CURRENCY_DELTA,
                            actor.civilization_id,
                            -5,
                            details=patronage_details,
                        ),
                        Consequence(
                            ConsequenceKind.RELIGIOUS_PATRONAGE_ADD,
                            actor.civilization_id,
                            target=religion.religion_id,
                            value=institution.institution_id,
                            details=patronage_details,
                        ),
                    ),
                    "A polity granted material patronage to a religious institution.",
                    (content_previous_by_civ[actor.civilization_id],),
                    conflict_keys,
                    0,
                )
            )
        if year % 35 == 0:
            actor = min(
                (c for c in content_start_state.civilizations if c.active),
                key=lambda c: c.civilization_id,
            )
            religions = cast(tuple[Religion, ...], identities["religions"])
            institutions = cast(
                tuple[ReligiousInstitution, ...], identities["religious_institutions"]
            )
            parent_religion = min(religions, key=lambda item: item.religion_id)
            parent_institution = next(
                item for item in institutions if item.religion_id == parent_religion.religion_id
            )
            child_institution_id = stable_id(
                "religious_institution",
                seed,
                identity("parent_institution_id", parent_institution.institution_id),
                identity("schism_year", year),
            )
            disputed_claim = f"whether {parent_religion.belief_claim}"
            proposal_id = stable_id(
                "history_proposal",
                seed,
                identity("content_year", year),
                identity("kind", EventKind.SCHISM.value),
                identity("institution_id", parent_institution.institution_id),
            )
            conflict_keys = tuple(
                sorted(
                    (
                        f"content-currency:{actor.civilization_id}:{year:04d}",
                        f"content-institution:{parent_institution.institution_id}:{year:04d}",
                        f"content-institution:{child_institution_id}:{year:04d}",
                    )
                )
            )
            schism_details = (
                ("holy_site_id", parent_religion.holy_site_id),
                ("registry_id", parent_institution.registry_id),
                ("rite", parent_institution.rite),
                ("disputed_claim", disputed_claim),
                ("proposal_id", proposal_id),
                ("conflict_keys", ",".join(conflict_keys)),
                ("snapshot", f"{year:04d}:12"),
            )
            content_candidates.append(
                HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.SCHISM,
                    actor.civilization_id,
                    (
                        actor.civilization_id,
                        parent_institution.institution_id,
                        child_institution_id,
                    ),
                    (parent_religion.holy_site_id,),
                    (
                        Consequence(
                            ConsequenceKind.CURRENCY_DELTA,
                            actor.civilization_id,
                            -5,
                            details=schism_details,
                        ),
                        Consequence(
                            ConsequenceKind.RELIGIOUS_SCHISM_ADD,
                            parent_religion.religion_id,
                            target=child_institution_id,
                            value=parent_institution.institution_id,
                            details=schism_details,
                        ),
                    ),
                    "A doctrinal dispute formed a child institution without altering its parent.",
                    (content_previous_by_civ[actor.civilization_id],),
                    conflict_keys,
                    0,
                )
            )
        accepted_content, content_decisions = resolve_proposals(tuple(content_candidates))
        proposal_decisions.extend(content_decisions)
        for accepted_proposal in accepted_content:
            sequence += 1
            content_event = _event(
                state,
                seed,
                year,
                12,
                sequence,
                accepted_proposal.kind,
                accepted_proposal.participants,
                accepted_proposal.locations,
                accepted_proposal.consequences,
                accepted_proposal.summary,
                accepted_proposal.causes,
            )
            state = apply_event(state, content_event)
            ledger.append(content_event)
            annual_batch.append(content_event)
            previous_by_civ[accepted_proposal.actor_id] = content_event.event_id
            for consequence in content_event.consequences:
                if consequence.kind is ConsequenceKind.ARTIFACT_CREATE:
                    artifact_heads[consequence.subject] = (
                        consequence.target,
                        consequence.value,
                        "intact",
                        content_event.event_id,
                    )
                    artifact_transition_counts[consequence.subject] = 0
        if year > 50 and year % 10 == 0:
            viable = sorted(
                [
                    (artifact_id, head)
                    for artifact_id, head in artifact_heads.items()
                    if head[2] != "destroyed"
                ],
                key=lambda item: (-artifact_transition_counts[item[0]], item[0]),
            )
            if viable:
                artifact_id, artifact_prior = viable[0]
                transition = ARTIFACT_TRANSITIONS[(div_floor_exact(year - 60, 10)) % 7]
                owner_people = tuple(sorted(consequential_people, key=lambda item: item.person_id))
                owner_index = (div_floor_exact(year - 60, 10) + 1) % len(owner_people)
                new_person = owner_people[owner_index]
                owner_civilization = next(
                    item
                    for item in state.civilizations
                    if item.civilization_id == new_person.civilization_id
                )
                new_owner = new_person.person_id
                new_site = owner_civilization.capital_site_id
                new_status = "intact"
                if transition == "loss":
                    new_owner = ""
                    new_site = artifact_prior[1]
                    new_status = "lost"
                elif transition == "destruction":
                    new_owner = artifact_prior[0]
                    new_site = artifact_prior[1]
                    new_status = "destroyed"
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("artifact_id", artifact_id),
                    identity("artifact_transition", transition),
                    identity("year", year),
                )
                conflict_keys = (f"artifact:{artifact_id}:{year:04d}",)
                artifact_details: tuple[tuple[str, str], ...] = (
                    ("transition", transition),
                    ("prior_owner_id", artifact_prior[0]),
                    ("prior_site_id", artifact_prior[1]),
                    ("prior_status", artifact_prior[2]),
                    ("prior_event_id", artifact_prior[3]),
                    ("new_site_id", new_site),
                    ("new_status", new_status),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", conflict_keys[0]),
                    ("snapshot", f"{year:04d}:12"),
                )
                lifecycle_causes = [artifact_prior[3]]
                if transition == "inheritance":
                    succession_claim = next(
                        event for event in reversed(ledger) if event.kind is EventKind.SUCCESSION
                    )
                    lifecycle_causes.append(succession_claim.event_id)
                    artifact_details += (("inheritance_event_id", succession_claim.event_id),)
                lifecycle_proposal = HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.ARTIFACT_HISTORY,
                    artifact_id,
                    tuple(
                        item
                        for item in (
                            artifact_id,
                            artifact_prior[0],
                            new_owner,
                        )
                        if item
                    ),
                    (new_site,),
                    (
                        Consequence(
                            ConsequenceKind.ARTIFACT_TRANSITION,
                            artifact_id,
                            target=new_owner,
                            details=artifact_details,
                        ),
                    ),
                    f"A legendary artifact underwent a recorded {transition} transition.",
                    tuple(sorted(lifecycle_causes)),
                    conflict_keys,
                    0,
                )
                accepted_lifecycle, lifecycle_decisions = resolve_proposals((lifecycle_proposal,))
                proposal_decisions.extend(lifecycle_decisions)
                if accepted_lifecycle:
                    sequence += 1
                    lifecycle_event = _event(
                        state,
                        seed,
                        year,
                        12,
                        sequence,
                        EventKind.ARTIFACT_HISTORY,
                        lifecycle_proposal.participants,
                        lifecycle_proposal.locations,
                        lifecycle_proposal.consequences,
                        lifecycle_proposal.summary,
                        lifecycle_proposal.causes,
                    )
                    state = apply_event(state, lifecycle_event)
                    ledger.append(lifecycle_event)
                    annual_batch.append(lifecycle_event)
                    artifact_heads[artifact_id] = (
                        new_owner,
                        new_site,
                        new_status,
                        lifecycle_event.event_id,
                    )
                    artifact_transition_counts[artifact_id] += 1
        if year == 1:
            for beast in megabeasts:
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("megabeast_origin", beast.megabeast_id),
                )
                conflict_keys = (f"megabeast:{beast.megabeast_id}:0001",)
                origin_details = (
                    ("transition", "origin"),
                    ("prior_region_id", beast.origin_region_id),
                    ("prior_condition", beast.initial_condition),
                    ("prior_event_id", ""),
                    ("lair_site_id", beast.lair_site_id),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", conflict_keys[0]),
                    ("snapshot", "0001:12"),
                )
                origin_proposal = HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    EventKind.MEGABEAST_ORIGIN,
                    beast.megabeast_id,
                    (beast.megabeast_id,),
                    (beast.lair_site_id, beast.origin_region_id),
                    (
                        Consequence(
                            ConsequenceKind.MEGABEAST_TRANSITION,
                            beast.megabeast_id,
                            target=beast.origin_region_id,
                            value=beast.initial_condition,
                            details=origin_details,
                        ),
                    ),
                    "A megabeast established its recorded origin and lair.",
                    (),
                    conflict_keys,
                    0,
                )
                accepted_origin, origin_decisions = resolve_proposals((origin_proposal,))
                proposal_decisions.extend(origin_decisions)
                if accepted_origin:
                    sequence += 1
                    origin_event = _event(
                        state,
                        seed,
                        year,
                        12,
                        sequence,
                        EventKind.MEGABEAST_ORIGIN,
                        origin_proposal.participants,
                        origin_proposal.locations,
                        origin_proposal.consequences,
                        origin_proposal.summary,
                        (),
                    )
                    state = apply_event(state, origin_event)
                    ledger.append(origin_event)
                    annual_batch.append(origin_event)
                    megabeast_heads[beast.megabeast_id] = (
                        beast.origin_region_id,
                        beast.initial_condition,
                        origin_event.event_id,
                    )
        if year % 12 == 0:
            viable_beasts = sorted(
                (beast_id, head) for beast_id, head in megabeast_heads.items() if head[1] != "dead"
            )
            if viable_beasts:
                beast_id, beast_prior = viable_beasts[0]
                beast = next(item for item in megabeasts if item.megabeast_id == beast_id)
                transition_index = (div_floor_exact(year, 12) - 1) % 4
                kind = (
                    EventKind.MEGABEAST_MOVEMENT,
                    EventKind.MEGABEAST_ENCOUNTER,
                    EventKind.MEGABEAST_HUNT,
                    EventKind.MEGABEAST_DEATH,
                )[transition_index]
                transition = kind.value.removeprefix("megabeast_")
                new_region = beast_prior[0]
                new_condition = beast_prior[1]
                if kind is EventKind.MEGABEAST_MOVEMENT:
                    new_region = next(
                        region_id
                        for region_id in beast.territory_region_ids
                        if region_id != beast_prior[0]
                    )
                elif kind in {EventKind.MEGABEAST_ENCOUNTER, EventKind.MEGABEAST_HUNT}:
                    new_condition = "wounded"
                else:
                    new_condition = "dead"
                actor = min(
                    (item for item in state.civilizations if item.active),
                    key=lambda item: item.civilization_id,
                )
                proposal_id = stable_id(
                    "history_proposal",
                    seed,
                    identity("megabeast_id", beast_id),
                    identity("megabeast_transition", transition),
                    identity("year", year),
                )
                conflict_keys = (f"megabeast:{beast_id}:{year:04d}",)
                beast_details = (
                    ("transition", transition),
                    ("prior_region_id", beast_prior[0]),
                    ("prior_condition", beast_prior[1]),
                    ("prior_event_id", beast_prior[2]),
                    ("proposal_id", proposal_id),
                    ("conflict_keys", conflict_keys[0]),
                    ("snapshot", f"{year:04d}:12"),
                )
                beast_proposal = HistoryProposal(
                    proposal_id,
                    year,
                    12,
                    kind,
                    actor.civilization_id,
                    (beast_id, actor.civilization_id),
                    (new_region,),
                    (
                        Consequence(
                            ConsequenceKind.MEGABEAST_TRANSITION,
                            beast_id,
                            target=new_region,
                            value=new_condition,
                            details=beast_details,
                        ),
                    ),
                    f"A megabeast {transition} became part of recorded history.",
                    tuple(
                        item
                        for item in (
                            beast_prior[2],
                            previous_by_civ[actor.civilization_id],
                        )
                        if item
                    ),
                    conflict_keys,
                    0,
                )
                accepted_beast, beast_decisions = resolve_proposals((beast_proposal,))
                proposal_decisions.extend(beast_decisions)
                if accepted_beast:
                    sequence += 1
                    beast_event = _event(
                        state,
                        seed,
                        year,
                        12,
                        sequence,
                        kind,
                        beast_proposal.participants,
                        beast_proposal.locations,
                        beast_proposal.consequences,
                        beast_proposal.summary,
                        beast_proposal.causes,
                    )
                    state = apply_event(state, beast_event)
                    ledger.append(beast_event)
                    annual_batch.append(beast_event)
                    megabeast_heads[beast_id] = (
                        new_region,
                        new_condition,
                        beast_event.event_id,
                    )
                    previous_by_civ[actor.civilization_id] = beast_event.event_id
        if annual_batch:
            prior_prefix = prefix_digest
            prefix_digest = hashlib.sha256(
                bytes.fromhex(prior_prefix) + canonical_json(tuple(annual_batch))
            ).hexdigest()
            annual_artifact = WorldArtifact.build(
                f"history_{year:04d}_12_final",
                {
                    "events": tuple(annual_batch),
                    "previous_prefix": prior_prefix,
                    "prefix_sha256": prefix_digest,
                },
                depends_on=batch_dependency + ((previous_batch_id,) if previous_batch_id else ()),
                producer_fingerprint=history_producer,
            )
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
    religions_for_integrity = cast(tuple[Religion, ...], identities["religions"])
    institutions_for_integrity = cast(
        tuple[ReligiousInstitution, ...], identities["religious_institutions"]
    )
    genesis_entity_ids = tuple(
        sorted(
            {
                *(site.site_id for site in genesis_state.sites),
                *(site.region_id for site in genesis_state.sites),
                *(settlement.settlement_id for settlement in genesis_state.settlements),
                *(
                    workshop.workshop_id
                    for settlement in genesis_state.settlements
                    for workshop in settlement.workshops
                ),
                *(civilization.civilization_id for civilization in genesis_state.civilizations),
                *(civilization.language_id for civilization in genesis_state.civilizations),
                *(civilization.government for civilization in genesis_state.civilizations),
                *(
                    capability
                    for civilization in genesis_state.civilizations
                    for capability in civilization.capabilities
                ),
                *(cohort.cohort_id for cohort in genesis_state.cohorts),
                *(stock.stock_id for stock in genesis_state.resource_stocks),
                *(person.person_id for person in consequential_people),
                *(house.house_id for house in dynasty_houses),
                *(beast.megabeast_id for beast in megabeasts),
                *(religion.religion_id for religion in religions_for_integrity),
                *(institution.institution_id for institution in institutions_for_integrity),
                *(str(region["region_id"]) for region in physical["regions"]["regions"]),
                *(
                    str(item["id"])
                    for registry in ("governments", "technologies")
                    for item in simulation_registry_entries(registry)
                ),
            }
        )
    )
    temporal_integrity = validate_temporal_integrity(
        tuple(ledger),
        genesis_state,
        state,
        genesis_entity_ids,
        conservation_ledger,
    )
    households, people, personal_relationships = generate_relationships(
        seed,
        state.cohorts,
        state.settlements,
        history_years,
    )
    legendary_artifacts = generate_legendary_artifacts(
        seed,
        tuple(ledger),
        people,
        state.civilizations,
        state.settlements,
    )
    history_clock = build_history_clock(history_years, tuple(ledger))
    genealogy_relations = project_genealogy(
        seed,
        tuple(ledger),
        dynasty_houses,
        consequential_people,
    )
    inheritances = project_inheritances(
        seed,
        tuple(ledger),
        dynasty_houses,
        consequential_people,
    )
    artifact_histories = project_artifact_histories(seed, tuple(ledger))
    megabeast_history = project_megabeast_history(seed, tuple(ledger), megabeasts)
    person_statuses = project_person_statuses(seed, tuple(ledger), consequential_people)
    religious_patronage = project_religious_patronage(
        seed,
        tuple(ledger),
        state.civilizations,
        cast(tuple[Religion, ...], identities["religions"]),
        cast(tuple[ReligiousInstitution, ...], identities["religious_institutions"]),
    )
    religious_schisms = project_religious_schisms(
        seed,
        tuple(ledger),
        state.civilizations,
        cast(tuple[Religion, ...], identities["religions"]),
        cast(tuple[ReligiousInstitution, ...], identities["religious_institutions"]),
    )
    successions = project_successions(
        seed,
        tuple(ledger),
        state.civilizations,
        dynasty_houses,
        consequential_people,
    )
    construction_projects = project_construction(
        tuple(ledger),
        state.civilizations,
        state.settlements,
    )
    technology_discoveries = project_technology_discoveries(
        seed,
        tuple(ledger),
        state.civilizations,
        state.settlements,
        simulation_registry_entries("technologies"),
    )
    exploration_discoveries = project_exploration_discoveries(
        seed,
        tuple(ledger),
        state.civilizations,
        state.settlements,
        tuple(str(region["region_id"]) for region in physical["regions"]["regions"]),
        tuple(routes),
    )
    government_reforms = project_government_reforms(
        seed,
        tuple(ledger),
        state.civilizations,
        simulation_registry_entries("governments"),
    )
    diplomatic_transitions = project_diplomatic_transitions(
        seed,
        tuple(ledger),
        state.civilizations,
        genesis_relations,
        state.relations,
    )
    polity_lifecycle = project_polity_lifecycle(
        seed,
        tuple(ledger),
        genesis_civilizations,
        genesis_settlements,
        state.civilizations,
        state.settlements,
    )
    languages = cast(tuple[LanguageIdentity, ...], identities["languages"])
    identities["language_history"] = tuple(
        stage
        for language in languages
        for stage in evolve_language(language.language_id, language.morphemes, history_years)
    )
    snapshot_by_year = {snapshot.year: snapshot for snapshot in snapshots}
    snapshots = [snapshot_by_year[year] for year in sorted(snapshot_by_year)]
    final_artifact_entry = {entry.artifact_id: entry for entry in artifact_histories}
    final_beast_entry = {entry.megabeast_id: entry for entry in megabeast_history}
    retention_inventory = build_retention_inventory(
        tuple(ledger),
        tuple(snapshots),
        registry_hashes,
        tuple(
            sorted(
                set(genesis_entity_ids)
                | set(collect_identity_ids(identities))
                | {source_id for event in ledger for source_id in event.source_ids}
            )
        ),
        genesis_state,
        state,
        tuple(
            item_id for item_id, entry in final_beast_entry.items() if entry.new_condition == "dead"
        ),
        tuple(
            item_id for item_id, entry in final_artifact_entry.items() if entry.new_status == "lost"
        ),
        tuple(
            item_id
            for item_id, entry in final_artifact_entry.items()
            if entry.new_status == "destroyed"
        ),
    )
    dependencies = tuple(sorted(physical_ids.values()))
    refs = []
    for artifact_kind, payload in (
        ("sites", state.sites),
        ("settlements", state.settlements),
        ("civilizations", state.civilizations),
        (
            "economy",
            {
                "algorithm_version": 2,
                "price_equation": {
                    "version": PRICE_EQUATION_VERSION,
                    "minimum_ppm": PRICE_MIN_PPM,
                    "maximum_ppm": PRICE_MAX_PPM,
                },
                "activity": state.economy_ledger,
                "conservation": conservation_ledger,
            },
        ),
        (
            "peoples",
            {"households": households, "people": people, "relationships": personal_relationships},
        ),
        ("legendary_artifacts", legendary_artifacts),
        ("legendary_artifact_histories", artifact_histories),
        ("megabeasts", {"entities": megabeasts, "history": megabeast_history}),
        ("history_clock", history_clock),
        (
            "genealogy",
            {
                "houses": dynasty_houses,
                "people": consequential_people,
                "relationships": genealogy_relations,
                "inheritances": inheritances,
                "person_statuses": person_statuses,
            },
        ),
        ("religious_patronage", religious_patronage),
        ("religious_schisms", religious_schisms),
        ("successions", successions),
        ("construction_projects", construction_projects),
        ("technology_discoveries", technology_discoveries),
        ("exploration_discoveries", exploration_discoveries),
        ("government_reforms", government_reforms),
        ("diplomatic_transitions", diplomatic_transitions),
        ("polity_lifecycle", polity_lifecycle),
        ("temporal_integrity", temporal_integrity),
        ("retention_inventory", retention_inventory),
        ("proposal_resolutions", tuple(proposal_decisions)),
        ("history", tuple(ledger)),
        ("snapshots", tuple(snapshots)),
        ("registries", registry_hashes),
        ("identities", identities),
    ):
        fingerprint_kind = (
            "history"
            if artifact_kind
            in {
                "history",
                "retention_inventory",
                "temporal_integrity",
            }
            else "legendary_artifacts"
            if artifact_kind in {"legendary_artifact_histories", "megabeasts"}
            else artifact_kind
        )
        artifact = WorldArtifact.build(
            artifact_kind,
            payload,
            depends_on=dependencies,
            producer_fingerprint=simulation_stage_fingerprint(
                fingerprint_kind, history_years, registry_hashes
            ),
        )
        repository.put(artifact)
        refs.append(artifact)
    physical_after = {
        kind: hashlib.sha256((world_root / "artifacts" / f"{kind}.json").read_bytes()).hexdigest()
        for kind in PHYSICAL_KINDS
    }
    if physical_after != physical_hashes_before:
        raise ValueError("WG-PHYSICAL-MUTATION: Phase 2 input changed during simulation")
    index = WorldArtifact.build(
        "simulation_index",
        {
            "algorithm_version": 1,
            "seed": seed,
            "present_year": history_years,
            "physical_artifacts": physical_ids,
            "physical_file_hashes": physical_after,
            "registry_hashes": registry_hashes,
            "ledger_prefix_sha256": prefix_digest,
            "artifacts": {
                ref.kind: {"artifact_id": ref.artifact_id, "sha256": ref.sha256} for ref in refs
            },
            "event_count": len(ledger),
            "snapshot_years": [snapshot.year for snapshot in snapshots],
        },
        depends_on=tuple(ref.artifact_id for ref in refs),
        producer_fingerprint=simulation_stage_fingerprint(
            "simulation_index", history_years, registry_hashes
        ),
    )
    repository.put(index)
    return {
        "simulation_index": index.artifact_id,
        "present_year": history_years,
        "events": len(ledger),
        "snapshots": len(snapshots),
        "civilizations": len(state.civilizations),
    }
