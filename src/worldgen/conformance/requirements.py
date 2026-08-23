"""P8.C05A step 1 — Every normative requirement from the three absorbed docs.

This module is the single checked source for the coverage ledger. The
generator script reads it and produces ``docs/worldgen-coverage.generated.md``.

Each requirement has a stable ID, target symbol, artifact kind, validator,
associated test, and status. The generator fails on duplicate IDs, missing
columns, unknown statuses, or a completed row without a real test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Literal

Status = Literal["complete", "partial", "missing", "obsolete"]

DOMAIN_OWNER = {
    "KERNEL": "P8.C05B", "PHYS": "P8.C05C", "ECO": "P8.C05C",
    "ROUTE": "P8.C05D", "SOC": "P8.C05E", "HIST": "P8.C05F",
    "LOCAL": "P8.C05G", "INTEGRATION": "P8.C05H",
}


def requirement_owner(requirement_id: str) -> str:
    """Return the roadmap phase that owns implementation closure for a row."""
    domain = requirement_id.split("-", 2)[1]
    if domain not in DOMAIN_OWNER:
        raise ValueError(f"unknown requirement domain: {requirement_id}")
    return DOMAIN_OWNER[domain]


@dataclass(frozen=True)
class Requirement:
    """One normative worldgen obligation."""

    id: str
    """Stable requirement ID (WG-KERNEL-*, WG-PHYS-*, WG-ECO-*, WG-ROUTE-*,
    WG-SOC-*, WG-HIST-*, WG-LOCAL-*, WG-INTEGRATION-*)."""

    description: str
    """Short summary of the normative statement."""

    source_doc: Literal["generation.md", "worldgen-rewrite.md", "worldgen-legacy.generated.md",
                          "worldgen-coverage.generated.md"]
    """Which document this requirement comes from."""

    target_symbol: str
    """The production symbol that implements this (module.Name)."""

    artifact_kind: str
    """The canonical artifact kind this requirement produces."""

    validator: str
    """The validator responsible for this invariant."""

    test: str
    """The test function or module that proves this requirement."""

    status: Status = "missing"
    """Current implementation status."""


REQUIREMENTS: list[Requirement] = []


def _r(
    rid: str, desc: str, source: Literal["generation.md", "worldgen-rewrite.md",
                                       "worldgen-legacy.generated.md",
                                       "worldgen-coverage.generated.md"],
    symbol: str = "",
    kind: str = "", validator: str = "", test: str = "",
    status: Status = "missing",
) -> Requirement:
    req = Requirement(rid, desc, source, symbol, kind, validator, test, status)
    REQUIREMENTS.append(req)
    return req


# ═══════════════════════════════════════════════════════════════════════
# WG-KERNEL — Deterministic foundation
# ═══════════════════════════════════════════════════════════════════════

_r("WG-KERNEL-001", "Fixed-point unit types must cover distance, elevation, temperature, rainfall, moisture, mass, energy, population, time, probability, price, and capacity",
  "generation.md", "worldgen.numeric.FIXED_UNIT_TYPES", "kernel", "numeric-validator", "tests/test_numeric_kernel_p8c05b.py::test_fixed_unit_contract_covers_every_required_dimension", status="complete")
_r("WG-KERNEL-002", "Every division must route through documented round_div rule; checked/saturating only where explicitly named",
  "generation.md", "worldgen.numeric.div_round_half_up", "kernel", "numeric-validator", "tests/test_numeric_kernel_p8c05b.py::test_worldgen_division_inventory_is_explicit", status="complete")
_r("WG-KERNEL-003", "SHA-256 domain seed derivation: (master seed, algorithm version, domain, stable entity ID, decision label)",
  "generation.md", "domain.run_spec.derive_seed", "seed_plan", "seed-validator", "tests/test_seed_plan.py::test_seed_derivation_contract_golden_and_separation", status="complete")
_r("WG-KERNEL-004", "SplitMix64 PRNG stream with frozen constants; decisions never use loop position alone",
  "generation.md", "worldgen.numeric.SplitMix64", "kernel", "prng-validator", "tests/test_numeric_kernel_p8c05b.py::test_prng_decision_contract_and_cross_platform_fixture", status="complete")
_r("WG-KERNEL-005", "WorldSpec, stage inputs/outputs, coordinates, chunks, artifact envelopes, producer fingerprints, diagnostics, validation results must be immutable typed contracts",
  "generation.md", "worldgen.artifacts.WorldArtifact", "world_spec", "spec-validator", "tests/test_worldgen_phase1.py::test_wg_kernel_005_contracts_are_immutable_and_typed", status="complete")
_r("WG-KERNEL-006", "Stable IDs derive from canonical identity inputs, never names or unordered enumeration",
  "generation.md", "worldgen.numeric.stable_id", "kernel", "id-validator", "tests/test_numeric_kernel_p8c05b.py::test_stable_id_contract_and_cross_platform_fixture", status="complete")
_r("WG-KERNEL-007", "Flat/chunked integer arrays for dense grids; no per-cell object graphs in production",
  "generation.md", "worldgen.artifact_shape_audit.audit_physical_artifacts", "kernel", "grid-validator", "tests/worldgen/test_artifacts.py::test_physical_artifact_shape_audit_proves_dense_grids_are_not_in_json", status="complete")
_r("WG-KERNEL-008", "Canonical big-endian grid headers/payloads; hash canonical internal bytes, never ZIP bytes",
  "generation.md", "worldgen.grid_catalog_audit.verify_catalog_chunk_bytes", "kernel", "grid-validator", "tests/worldgen/test_artifacts.py::test_all_physical_catalog_chunks_have_deterministic_canonical_bytes", status="complete")
_r("WG-KERNEL-009", "WorldArtifactRepository must be confined and atomic: verify ID, content hash, fingerprint, dependency IDs on reuse; crash-safe temp writes; fsync/rename publication",
  "generation.md", "worldgen.artifacts.WorldArtifactRepository", "kernel", "repository-tests", "tests/worldgen/test_artifact_repository_v2.py::test_exact_reuse_is_idempotent_but_conflicting_reuse_is_rejected", status="complete")
_r("WG-KERNEL-010", "Declarative world stage DAG; independent chunks may run in parallel but aggregation uses stable order; worker 1 = worker N bytes",
  "generation.md", "worldgen.physical_dag.PHYSICAL_STAGE_DAG", "kernel", "parallelism-tests", "tests/worldgen/test_artifacts.py::test_physical_stage_dag_and_worker_counts_produce_identical_bytes", status="complete")
_r("WG-KERNEL-011", "Canonical JSON: RFC 8785 JCS, Unicode NFC, no NaN/Infinity, sorted keys (UTF-16-BE), scaled integers not floats",
  "generation.md", "worldgen.artifacts.canonical_json", "kernel", "canonical-validator", "tests/test_numeric_kernel_p8c05b.py::test_canonical_json_cross_platform_diagnostics_fixture", status="complete")
_r("WG-KERNEL-012", "Stable artifact ID: <kind>_<first 32 hex of SHA-256(depends_on sorted, kind, producer_fingerprint, sha256)>",
  "generation.md", "worldgen.artifacts.artifact_identity_digest", "kernel", "id-validator", "tests/test_worldgen_phase1.py::test_artifact_identity_cross_platform_vectors_and_domain_separation", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-PHYS — Physical world, climate, geology, soils, resources, ecology
# ═══════════════════════════════════════════════════════════════════════

_r("WG-PHYS-001", "Spaced plate centres, deterministic Voronoi ownership, plate motion, boundary classes",
  "generation.md", "worldgen.physical_terrain.generate_physical_terrain", "plates", "plates-validator", "tests/worldgen/test_terrain.py::test_plate_centres_voronoi_motion_and_boundary_contract", status="complete")
_r("WG-PHYS-002", "Configurable exact continent count; fixed-point multi-octave texture for detail",
  "generation.md", "worldgen.physical_terrain.generate_physical_terrain", "terrain", "terrain-validator", "tests/worldgen/test_terrain.py::test_textured_continents_are_exact_connected_and_keep_border_ocean", status="complete")
_r("WG-PHYS-003", "Uplift/rift/transform relief; geological strata, faults, volcanic areas, soil parent material",
  "generation.md", "worldgen.geology.generate_geology", "geology", "geology-validator", "tests/worldgen/test_artifacts.py::test_geology_catalog_reconstructs_typed_tectonic_model", status="complete")
_r("WG-PHYS-004", "Synchronous thermal and hydraulic erosion with explicit mass ledger",
  "generation.md", "worldgen.physical_terrain.generate_physical_terrain", "terrain", "terrain-validator", "tests/worldgen/test_terrain.py::test_exact_continent_count_and_mass_conserving_erosion", status="complete")
_r("WG-PHYS-005", "Priority-flood depression handling; deterministic D8 flow with frozen tie order",
  "generation.md", "worldgen.hydrology.priority_flood", "hydrology", "hydrology-validator", "tests/worldgen/test_hydrology.py::test_priority_flood_d8_ties_are_frozen_and_acyclic", status="complete")
_r("WG-PHYS-006", "Accumulation, river thresholds, lakes, spillways, watersheds, aquifers, coastlines, deltas",
  "generation.md", "worldgen.hydrology.connected_lakes", "hydrology", "hydrology-validator", "tests/worldgen/test_hydrology.py::test_connected_lakes_spillways_accumulation_and_deltas", status="complete")
_r("WG-PHYS-007", "Every non-ocean surface cell must drain to ocean or declared closed basin",
  "generation.md", "worldgen.hydrology.generate_hydrology", "hydrology", "hydrology-validator", "tests/worldgen/test_hydrology.py::test_every_land_cell_drains_to_ocean_or_closed_basin", status="complete")
_r("WG-PHYS-008", "Four-season solar temperature from latitude/elevation/axial tilt",
  "generation.md", "worldgen.weather.solar_temperature_millic", "climate", "climate-validator", "tests/worldgen/test_climate.py::test_solar_temperature_is_symmetric_and_responds_to_tilt_and_elevation", status="complete")
_r("WG-PHYS-009", "Stable prevailing winds, orographic lift/rain shadow, bounded moisture relaxation",
  "generation.md", "worldgen.weather.directional_moisture_pass", "climate", "climate-validator", "tests/worldgen/test_climate.py::test_prevailing_wind_cells_and_orographic_rain_shadow_are_deterministic", status="complete")
_r("WG-PHYS-010", "Precipitation, evaporation, snow/ice, storms, weather regimes; convergence bounded by pass count",
  "generation.md", "worldgen.weather.generate_weather", "climate", "climate-validator", "tests/worldgen/test_climate.py::test_seasonal_water_ledgers_snow_ice_and_storms_are_exact", status="complete")
_r("WG-PHYS-011", "Soil depth/fertility/drainage/erosion classes; total ordered biome table, no later mutation",
  "generation.md", "worldgen.soil.generate_soil", "soil", "biome-validator", "tests/worldgen/test_biomes_resources.py::test_biome_table_is_total_ordered_and_no_mutation", status="complete")
_r("WG-PHYS-012", "Mineral/deposit geometry, depth, grade, quantity, geology compatibility",
  "generation.md", "worldgen.resources.generate_resources", "resources", "resources-validator", "tests/worldgen/test_biomes_resources.py::test_deposits_are_geology_compatible", status="complete")
_r("WG-PHYS-013", "Renewable yields and depletion rules for all resource types",
  "generation.md", "worldgen.simulation.scheduler._stock_extraction", "resource_stocks", "resources-validator", "tests/worldgen/simulation/test_economy_population.py::test_material_creation_is_backed_by_stock_depletion", status="complete")
_r("WG-PHYS-014", "Habitats, species, food-web bounds, carrying capacity, migration corridors, extinction pressure, recovery",
  "generation.md", "worldgen.ecology.generate_ecology", "ecology", "ecology-validator", "tests/worldgen/test_biomes_resources.py::test_regional_population_dynamics_are_bounded_and_conservative", status="complete")
_r("WG-PHYS-015", "Versioned material, species, biome, and recipe registries hash into producer fingerprints",
  "generation.md", "worldgen.physical_pipeline.physical_stage_fingerprint", "world_index", "registry-validator", "tests/worldgen/test_registries.py::test_registry_changes_invalidate_only_the_direct_physical_producer", status="complete")
_r("WG-PHYS-016", "Separate immutable artifacts for plates, terrain, geology, hydrology, climate/weather, soils, biomes, resources, species, ecology",
  "generation.md", "worldgen.physical_validation_report.build_physical_validation_report", "validation_report", "artifact-validator", "tests/worldgen/test_artifacts.py::test_validation_report_binds_the_complete_physical_contract", status="complete")
_r("WG-PHYS-017", "Elevation bounded, land/ocean fraction satisfies spec, continent count exact",
  "worldgen-rewrite.md", "worldgen.validation.validate_terrain_contract", "validation_report", "terrain-validator", "tests/worldgen/test_terrain.py::test_requested_land_fraction_is_satisfied", status="complete")
_r("WG-PHYS-018", "Erosion mass conservation; river monotonicity; seasonal/climate invariants",
  "generation.md", "worldgen.physical_validation_report.measure_physical_invariants", "validation_report", "domain-validators", "tests/worldgen/test_artifacts.py::test_invariant_evidence_rejects_adversarial_ledger_and_river_mutations", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-ECO — Regions, routes, maps, spatial/reference indexes
# ═══════════════════════════════════════════════════════════════════════

_r("WG-ROUTE-001", "Segment regions with deterministic multi-source Dijkstra over biome, basin, elevation, climate, travel costs",
  "generation.md", "worldgen.physical_regions.generate_regions", "regions", "regions-validator", "tests/worldgen/test_regions_routes.py::test_multisource_dijkstra_regions_use_all_physical_cost_fields", status="complete")
_r("WG-ROUTE-002", "Deterministic split/merge; min/max sizes; canonical centres/boundaries; symmetric adjacency; one-region-per-land-cell coverage",
  "generation.md", "worldgen.validation.validate_regions", "regions", "regions-validator", "tests/worldgen/test_regions_routes.py::test_region_validator_rejects_duplicate_ownership_and_noncanonical_center", status="complete")
_r("WG-ROUTE-003", "Seasonal A* routes for roads, trails, navigable rivers, sea lanes, mountain passes, settlement links",
  "generation.md", "worldgen.routes.generate_routes", "routes", "routes-validator", "tests/worldgen/test_regions_routes.py::test_typed_routes_have_four_valid_seasonal_ast_paths", status="complete")
_r("WG-ROUTE-004", "Frozen neighbour/tie ordering, cost units, legal endpoints, traversability seasons, hazards, capacity",
  "generation.md", "worldgen.routes.ROUTE_CLASS_RULES", "routes", "routes-validator", "tests/worldgen/test_regions_routes.py::test_route_class_rules_costs_maintenance_and_sources_are_frozen", status="complete")
_r("WG-ROUTE-005", "Reject disconnected jumps and routes whose endpoint regions do not contain path endpoints",
  "generation.md", "worldgen.validation.validate_physical_world, narrative.story_graph.validate_route_transition", "routes", "routes-validator", "tests/worldgen/test_regions_routes.py::test_route_validator_rejects_disconnected_pair_and_wrong_endpoint_cell", status="complete")
_r("WG-ROUTE-006", "Canonical scalar/vector layers and deterministic raster maps for every layer",
  "generation.md", "worldgen.maps.MapLayerCatalog", "map_layers", "maps-validator", "tests/worldgen/test_artifacts.py::test_all_domains_are_independent_verified_artifacts", status="complete")
_r("WG-ROUTE-007", "Frozen colour tables, resampling, label placement, dimensions, provenance; maps never replace facts",
  "generation.md", "worldgen.maps.validate_map_manifest", "map_layers", "maps-validator", "tests/worldgen/test_maps.py::test_corrupt_raster_is_rejected_without_changing_authoritative_layers", status="complete")
_r("WG-ROUTE-008", "Spatial, containment, route, temporal, entity, and reverse-reference indexes from authoritative artifacts",
  "generation.md", "worldgen.index_reader.VerifiedSpatialIndexReader, worldgen.index_reader.VerifiedReferenceIndexReader", "spatial_index", "index-validator", "tests/worldgen/test_regions_routes.py::test_published_indexes_are_compact_verified_and_bounded", status="complete")
_r("WG-ROUTE-009", "Index corruption invalidates only derived indexes; rebuild produces canonical equality",
  "generation.md", "worldgen.index_rebuild.rebuild_physical_indexes", "reference_index", "index-validator", "tests/worldgen/test_artifacts.py::test_indexes_delete_and_rebuild_to_exact_bytes_without_touching_sources", status="complete")
_r("WG-ROUTE-010", "Publish bounded lazy lookup APIs by fact/source ID, point, bounding box, region, route, cell, and time range",
  "generation.md", "worldgen.index_reader.VerifiedWorldIndex", "reference_index", "index-validator", "tests/world/test_views.py::test_world_index_facade_covers_all_bounded_query_forms", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-SOC — Peoples, identities, magic, settlement growth, economy
# ═══════════════════════════════════════════════════════════════════════

_r("WG-SOC-001", "Freeze and hash registries for technologies, occupations, materials, recipes, institutions, governments, beliefs, magic vocabulary, language phonemes/morphology",
  "generation.md", "worldgen.simulation.registries.simulation_stage_fingerprint", "registries", "registry-validator", "tests/worldgen/simulation/test_registries_identity.py::test_society_registries_are_complete_versioned_unique_and_stable", status="complete")
_r("WG-SOC-002", "Generate languages, morphemes, names, scripts, flags, heraldry, culture traits from stable IDs + environmental/historical pressures — not race rules",
  "generation.md", "worldgen.simulation.names.generate_identity", "identities", "culture-validator", "tests/worldgen/simulation/test_registries_identity.py::test_environment_changes_expression_but_not_founder_language_identity", status="complete")
_r("WG-SOC-003", "Separate objective magic laws from attributed belief claims; every objective effect cites law/source",
  "generation.md", "worldgen.simulation.magic.validate_supernatural", "identities", "magic-validator", "tests/worldgen/simulation/test_registries_identity.py::test_magic_validator_rejects_uncited_or_law_inconsistent_effect", status="complete")
_r("WG-SOC-004", "Magic sources, costs, limits, side effects, religions, schisms, institutions, cultural interpretations",
  "generation.md", "worldgen.simulation.magic.validate_supernatural", "identities", "magic-validator", "tests/worldgen/simulation/test_registries_identity.py::test_magic_sources_institutions_schisms_and_interpretations_are_place_bound", status="complete")
_r("WG-SOC-005", "Score initial sites using fresh water, food/capacity, defense, hazards, routes, resources, climate, neighbours",
  "generation.md", "worldgen.simulation.sites.score_site", "sites", "sites-validator", "tests/worldgen/simulation/test_sites_state.py::test_site_score_is_explainable_pressure_sensitive_and_recomputed", status="complete")
_r("WG-SOC-006", "Exact configured civilization count; abort with stable capacity diagnostic when infeasible",
  "generation.md", "worldgen.simulation.sites.CivilizationCapacityError", "civilizations", "civ-validator", "tests/worldgen/simulation/test_sites_state.py::test_infeasible_civilization_count_has_stable_capacity_diagnostic", status="complete")
_r("WG-SOC-007", "Settlement founding/growth/abandonment, land use, construction, workshops, production chains, inventories",
  "generation.md", "worldgen.simulation.settlements.validate_settlements", "settlements", "settlement-validator", "tests/worldgen/simulation/test_economy_population.py::test_settlement_lifecycle_land_use_workshops_and_inventory_are_retained", status="complete")
_r("WG-SOC-008", "Transport capacity, trade, scarcity, prices, taxes, maintenance, depletion, recovery",
  "generation.md", "worldgen.simulation.economy.validate_economy_ledger", "economy", "economy-validator", "tests/worldgen/simulation/test_economy_population.py::test_economy_ledger_covers_capacity_scarcity_tax_maintenance_and_resources", status="complete")
_r("WG-SOC-009", "Bounded integer-only price equation; conservation ledgers for people, goods, currency",
  "generation.md", "worldgen.simulation.conservation.validate_conservation_ledger", "economy", "economy-validator", "tests/worldgen/simulation/test_economy_population.py::test_conservation_ledger_covers_every_quantity_change_and_balances_transfers", status="complete")
_r("WG-SOC-010", "Explicit site-count budget and preflight formula covering required local-map RAM/disk/time",
  "generation.md", "domain.run_spec.WorldSpec.budget_estimate", "world_spec", "spec-validator", "tests/test_run_spec.py::test_world_preflight_has_stable_resource_diagnostics", status="complete")
_r("WG-SOC-011", "Sites are immutable identities; abandonment changes state, not identity",
  "generation.md", "worldgen.simulation.sites.validate_site_lifecycle", "sites", "sites-validator", "tests/worldgen/simulation/test_sites_state.py::test_site_lifecycle_rejects_mutation_deletion_forgery_and_dangling_settlement", status="complete")
_r("WG-SOC-012", "Language sound evolution, syllable-pattern realization, and profanity/duplicate/confusable/reserved-name safety",
  "generation.md", "worldgen.simulation.language_evolution.evolve_language", "identities", "language-validator", "tests/worldgen/simulation/test_registries_identity.py::test_language_sound_changes_are_historical_stable_and_keep_language_id", status="complete")
_r("WG-SOC-013", "Contrast-safe vector heraldry whose divisions, motifs, and meanings cite culture/history",
  "generation.md", "worldgen.simulation.heraldry.validate_heraldry", "identities", "heraldry-validator", "tests/worldgen/simulation/test_registries_identity.py::test_vector_heraldry_is_deterministic_contrasting_and_culturally_cited", status="complete")
_r("WG-SOC-014", "Cosmological layers/cycles and attributed entities, cults, relics, rites, hazards, and place-bound resources",
  "generation.md", "worldgen.simulation.cosmology.validate_cosmology", "identities", "cosmology-validator", "tests/worldgen/simulation/test_registries_identity.py::test_cosmology_is_layered_attributed_cyclical_and_place_bound", status="complete")
_r("WG-SOC-015", "Households and typed interpersonal/lineage relationships tied to cohorts and settlements without race rules",
  "generation.md", "worldgen.simulation.relationships.validate_relationships", "peoples", "relationship-validator", "tests/worldgen/simulation/test_sites_state.py::test_households_conserve_cohorts_and_relationships_are_typed_and_retained", status="complete")
_r("WG-SOC-016", "Rare legendary artifacts arise only from successful craft/commission events with complete provenance and attributed meanings",
  "generation.md", "worldgen.simulation.legendary_artifacts.validate_legendary_artifacts", "legendary_artifacts", "artifact-validator", "tests/worldgen/simulation/test_economy_population.py::test_legendary_artifacts_only_follow_successful_commissions_with_full_provenance", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-HIST — Monthly causal history, events, snapshots, replay, retention
# ═══════════════════════════════════════════════════════════════════════

_r("WG-HIST-001", "Run all configured years and exactly 12 ticks per year",
  "generation.md", "worldgen.simulation.history_clock.validate_history_clock", "history_clock", "history-validator", "tests/worldgen/simulation/test_properties.py::test_history_is_deterministic_and_replayable", status="complete")
_r("WG-HIST-002", "Monthly proposals: births, deaths, ageing, migration, disease, harvest, production, consumption, trade, depletion, disasters, crime, relationships",
  "generation.md", "worldgen.simulation.scheduler.simulate_world", "history_events", "history-validator", "tests/worldgen/simulation/test_economy_population.py::test_crime_events_have_actor_victim_pressure_resolution_and_exact_loss", status="complete")
_r("WG-HIST-003", "Yearly proposals: construction, exploration, technology, religion, diplomacy, succession, reform, schism, war, conquest, collapse, recovery",
  "generation.md", "worldgen.simulation.scheduler.simulate_world, worldgen.simulation.polity_lifecycle.project_polity_lifecycle", "history_events, polity_lifecycle", "history-validator", "tests/worldgen/simulation/test_polity_lifecycle.py::test_collapse_recovery_cycle_is_typed_causal_and_identity_preserving", status="complete")
_r("WG-HIST-004", "Collect proposals from immutable start-of-tick state, sort by frozen conflict key, resolve conflicts once",
  "generation.md", "worldgen.simulation.proposals.resolve_proposals, worldgen.simulation.scheduler", "proposal_resolutions, history_events", "proposal-validator", "tests/worldgen/simulation/test_proposals.py::test_all_scheduler_proposals_are_decided_and_traceable", status="complete")
_r("WG-HIST-005", "Every event records stable ID, year/month/sequence, kind, causes, participants, locations, before/after deltas, consequences, summary, source IDs, algorithm version",
  "generation.md", "worldgen.simulation.events.seal_event, worldgen.simulation.events.apply_event", "history_events", "history-validator", "tests/worldgen/simulation/test_events.py::test_every_persisted_event_has_a_verified_versioned_envelope", status="complete")
_r("WG-HIST-006", "Causes precede effects; participants/locations exist at that tick; every material state delta has exactly one event",
  "generation.md", "worldgen.simulation.temporal_integrity.validate_temporal_integrity", "history_events, temporal_integrity", "history-validator", "tests/worldgen/simulation/test_temporal_integrity.py::test_temporal_integrity_rejects_unknown_entities_causes_and_delta_owners", status="complete")
_r("WG-HIST-007", "Commit monthly batches atomically with prefix hashes; write genesis, ten-year, and final-year snapshots",
  "generation.md", "worldgen.simulation.scheduler.simulate_world, worldgen.simulation.replay.validate_history_batch_chain, worldgen.simulation.replay.expected_snapshot_years", "history_snapshots", "snapshot-validator", "tests/worldgen/simulation/test_replay.py::test_every_committed_batch_boundary_is_chained_and_truncation_is_rejected", status="complete")
_r("WG-HIST-008", "Replay from genesis and each snapshot to same final canonical state; detect missing/reordered/duplicated/tampered events at first divergence",
  "generation.md", "worldgen.simulation.replay.replay_snapshot_to_final, worldgen.simulation.replay.ReplayDivergence", "history_snapshots", "replay-validator", "tests/worldgen/simulation/test_replay.py::test_replay_reports_first_missing_reordered_duplicated_and_tampered_event", status="complete")
_r("WG-HIST-009", "Retain complete ledger, identities, registries, state snapshots, and extinct/abandoned entities even when narrative never references them",
  "generation.md", "worldgen.simulation.retention.build_retention_inventory, worldgen.simulation.retention.collect_identity_ids", "history_events, retention_inventory", "retention-validator", "tests/worldgen/simulation/test_retention.py::test_extinct_and_abandoned_entities_are_retained_and_discard_is_rejected", status="complete")
_r("WG-HIST-010", "Checkpoint/resume per committed batch; never repeat an applied change",
  "generation.md", "worldgen.simulation.history_checkpoint.recover_committed_checkpoints, worldgen.simulation.history_checkpoint.resume_committed_history", "kernel", "checkpoint-validator", "tests/worldgen/simulation/test_history_checkpoint.py::test_every_committed_batch_resumes_exactly_once_to_the_next_boundary", status="complete")
_r("WG-HIST-011", "Selective event-sourced genealogy for consequential people, houses, lineage claims, succession, and inheritance without duplicating cohort population",
  "worldgen-coverage.generated.md", "worldgen.simulation.genealogy.project_genealogy, worldgen.simulation.genealogy.project_inheritances, worldgen.simulation.succession.project_successions", "genealogy", "genealogy-validator", "tests/worldgen/simulation/test_genealogy.py::test_genealogy_is_selective_event_sourced_and_does_not_add_population", status="complete")
_r("WG-HIST-012", "Rare persistent megabeasts have bounded movement, encounter, hunt, death, carrying cost, and retained post-death histories",
  "worldgen-coverage.generated.md", "worldgen.simulation.megabeasts.generate_megabeasts, worldgen.simulation.megabeasts.project_megabeast_history", "megabeasts", "megabeast-validator", "tests/worldgen/simulation/test_megabeasts.py::test_megabeasts_are_rare_persistent_and_have_complete_histories", status="complete")
_r("WG-HIST-013", "Legendary artifacts retain causal creation, gift, inheritance, trade, theft, loss, recovery, and destruction histories",
  "worldgen-coverage.generated.md", "worldgen.simulation.artifact_history.project_artifact_histories", "legendary_artifact_histories", "artifact-history-validator", "tests/worldgen/simulation/test_artifact_history.py::test_artifact_history_supports_every_frozen_lifecycle_transition", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-LOCAL — Every-site local 3D worlds and macro/micro reconciliation
# ═══════════════════════════════════════════════════════════════════════

_r("WG-LOCAL-001", "Derive immutable boundary conditions from site, region, terrain, geology, hydrology, climate, resource, route, culture, settlement, present-state artifacts",
  "generation.md", "worldgen.local_boundaries.derive_local_boundaries, worldgen.local_boundaries.validate_local_boundaries, worldgen.local_boundaries.local_boundary_from_mapping", "local_maps", "local-validator", "tests/worldgen/test_local_boundaries_p8c05g.py::test_every_site_has_a_typed_complete_immutable_boundary", status="complete")
_r("WG-LOCAL-002", "Macro coastline, river, road, elevation, climate, resource, ownership constraints authoritative at local boundaries",
  "generation.md", "worldgen.local_boundaries.MacroBoundaryEdge, worldgen.local_boundaries.validate_local_boundaries", "local_maps", "local-validator", "tests/worldgen/test_local_boundaries_p8c05g.py::test_cardinal_edges_equal_authoritative_neighbor_fields", status="complete")
_r("WG-LOCAL-003", "Generate chunked 3D surface, strata, deposits, caves, aquifers, rivers/coasts, vegetation, parcels, streets, walls, bridges, buildings, workshops, ruins, interiors, items",
  "generation.md", "worldgen.local_chunks.generate_material_chunks, worldgen.local_occupancy.generate_occupancy_chunks, worldgen.local_construction.generate_construction_chunks, worldgen.local_society.derive_cultural_layout, worldgen.local_conditionals.synthesize_conditional_features, worldgen.local_maps.generate_local_maps", "local_maps", "local-validator", "tests/worldgen/test_local_conditionals_p8c05g.py::test_forced_plan_synthesizes_exact_hashed_feature_chunks", status="complete")
_r("WG-LOCAL-004", "Local detail may refine empty space but may not contradict a macro fact",
  "generation.md", "worldgen.local_reconciliation.validate_local_reconciliation", "local_maps", "reconciliation-validator", "tests/worldgen/test_local_reconciliation_p8c05g.py::test_every_generated_local_map_reconciles_with_macro_authority", status="complete")
_r("WG-LOCAL-005", "Legal 3D movement edges for walking, stairs, ramps, doors, bridges, climbing; hierarchical A* with stable costs/ties",
  "generation.md", "worldgen.local_navigation.build_movement_graph, worldgen.local_navigation.find_local_path, worldgen.local_navigation.find_world_hierarchical_path, worldgen.local_maps.generate_local_maps", "local_maps", "navigation-validator", "tests/worldgen/test_local_navigation_p8c05g.py::test_hierarchical_path_composes_local_macro_local_segments", status="complete")
_r("WG-LOCAL-006", "Bounded synchronous water/magma flow, heat transfer, structural support/collapse with frozen update order and conservation ledgers",
  "generation.md", "worldgen.local_physics.derive_site_water_simulation, worldgen.local_physics.simulate_water, worldgen.local_physics.validate_water_simulation, worldgen.local_physics.derive_site_magma_simulation, worldgen.local_physics.simulate_magma, worldgen.local_physics.validate_magma_simulation, worldgen.local_physics.validate_fluid_exclusion, worldgen.local_physics.derive_site_heat_simulation, worldgen.local_physics.simulate_heat, worldgen.local_physics.validate_heat_simulation, worldgen.local_physics.derive_site_structural_simulation, worldgen.local_physics.simulate_structure, worldgen.local_physics.validate_structural_simulation", "local_maps", "physics-validator", "tests/worldgen/test_local_physics_p8c05g.py::test_every_site_persists_source_derived_structure", status="complete")
_r("WG-LOCAL-007", "Reconcile micro-to-macro summaries (population, production, storage, resources, routes, damage, ownership) without double counting",
  "generation.md", "worldgen.local_summary.derive_local_macro_summary, worldgen.local_summary.validate_local_macro_summary, worldgen.local_summary.local_macro_summary_from_mapping", "local_maps", "reconciliation-validator", "tests/worldgen/test_local_summary_p8c05g.py::test_every_site_summary_references_exact_macro_accounts", status="complete")
_r("WG-LOCAL-008", "Publish local index and required chunks/maps for every historical/present registered site; retain in .story even if unvisited",
  "generation.md", "worldgen.local_index.build_local_world_index, worldgen.local_index.validate_local_world_index, worldgen.local_reader.LazyLocalWorldReader, worldgen.local_reader.audit_local_storage, storage.project_v2.package_project_v2, storage.package_v2._validate_world_contract", "local_maps", "coverage-validator", "tests/worldgen/test_local_streaming_p8c05g.py::test_local_publication_resumes_and_repairs_corrupt_chunk", status="complete")
_r("WG-LOCAL-009", "Every registered site receives a complete local 3D map whether or not narrative uses it",
  "worldgen-rewrite.md", "worldgen.local_maps.generate_local_maps, worldgen.local_index.validate_narrative_independent_coverage, pipeline.plan.PipelinePlan.production_v2", "local_maps", "coverage-validator", "tests/worldgen/test_local_index_p8c05g.py::test_disjoint_narrative_selections_cannot_filter_or_change_local_bytes", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# WG-INTEGRATION — Story projection, production integration, hardening
# ═══════════════════════════════════════════════════════════════════════

_r("WG-INTEGRATION-001", "Generate deterministic story opportunities from authoritative pressures, routes, people, events, beliefs, sites, local containment",
  "generation.md", "worldgen.simulation.projections.StoryProjection, worldgen.simulation.projections.validate_story_projections, narrative.opportunities.generate_opportunities, narrative.opportunities.validate_opportunities", "story_opportunities", "opportunity-validator", "tests/test_opportunities_p8c05h.py::test_opportunities_bind_every_authoritative_evidence_dimension", status="complete")
_r("WG-INTEGRATION-002", "Build bounded typed World Bible projection chunks with complete source coverage",
  "generation.md", "world.projections.ProjectionSet, world.projections.validate_projections, world.builder.WorldBuilderV2", "bible", "bible-validator", "tests/world/test_projections.py::test_projection_validator_rejects_forged_source_and_incomplete_coverage", status="complete")
_r("WG-INTEGRATION-003", "Projection is intentionally selective; authoritative world artifacts remain immutable and complete",
  "generation.md", "world.views.WorldView.authoritative_inventory, world.views.WorldView.assert_inventory_unchanged, world.projections.ProjectionSet, world.builder.WorldBuilderV2", "bible", "bible-validator", "tests/test_world_builder_v2.py::test_builder_rejects_injected_authoritative_artifact", status="complete")
_r("WG-INTEGRATION-004", "Remove snapshot_to_bible_context and all lossy adapters",
  "worldgen-rewrite.md", "world.builder.WorldBuilderV2", "kernel", "architecture-tests", "test_worldgen_conformance_p8c05a.py::test_legacy_inventory", status="complete")
_r("WG-INTEGRATION-005", "Require strict Bible reconciliation before story generation",
  "generation.md", "world.models.SiteClaim, world.models.PersonClaim, validators.world_reconciler.WorldReconciler", "reconciliation", "reconciliation-validator", "tests/test_world_reconciler.py::test_site_person_temporal_and_projection_contradictions_are_rejected", status="complete")
_r("WG-INTEGRATION-006", "Story scenes, graph nodes, choices, travel, media intents, GM entries carry valid stable world/source IDs",
  "generation.md", "narrative.story_graph.generate_story, narrative.story_graph.validate_graph, narrative.pipeline.write_media_intents, narrative.pipeline.validate_media_intent_authority, narrative.knowledge.build_knowledge_index", "story", "story-validator", "tests/test_game_designer_v2.py::test_choice_and_media_intent_must_retain_node_authority", status="complete")
_r("WG-INTEGRATION-007", "Validate temporal/entity state and both ends of travel at every choice",
  "generation.md", "narrative.models.StoryScene, narrative.models.ChoiceV2, narrative.models.GraphNodeV2, narrative.story_graph.validate_graph", "graph", "graph-validator", "tests/test_game_designer_v2.py::test_choice_time_and_travel_season_bind_both_endpoints", status="complete")
_r("WG-INTEGRATION-008", "The P8.C0 plan must be the only product generation/resume plan",
  "worldgen-rewrite.md", "pipeline.plan.PipelinePlan.production_v2, application.generate_story.GenerateStory, launcher.core.ForgeProcess", "kernel", "plan-validator", "tests/test_production_entrypoint_fence.py::test_runtime_has_only_approved_production_plan_calls", status="complete")
_r("WG-INTEGRATION-009", "Package every procedural envelope, complete history, every local world, all registries/indexes, Bible/reconciliation, narrative, full media per node, GM index, maps, schemas, provenance",
  "generation.md", "storage.project_v2.audit_package_inputs, storage.project_v2.package_project_v2", "packager", "package-validator", "tests/test_package_completeness_p8c05h.py::test_package_audit_covers_every_authoritative_input", status="complete")
_r("WG-INTEGRATION-010", "Verify canonical internal file hashes and dependency DAG; never compute/compare a ZIP hash",
  "generation.md", "storage.package_v2.content_hash, storage.package_v2.validate_v2_package", "packager", "package-validator", "tests/test_package_identity_p8c05h.py::test_zip_container_bytes_never_determine_story_identity", status="complete")
_r("WG-INTEGRATION-011", "P8.C05H: Legacy generator/types/enums/RNG/adapters/config modes/fallbacks removed",
  "worldgen-coverage.generated.md", "worldgen.conformance.legacy_inventory.LEGACY_MODULES", "kernel", "architecture-tests", "test_worldgen_conformance_p8c05a.py::test_legacy_inventory", status="complete")
_r("WG-INTEGRATION-012", "P8.C05H: Python enforces via ModuleNotFoundError — no legacy symbols remain",
  "worldgen-coverage.generated.md", "worldgen.conformance.legacy_inventory.LEGACY_MODULES", "kernel", "architecture-tests", "test_worldgen_conformance_p8c05a.py::test_legacy_inventory", status="complete")
_r("WG-INTEGRATION-013", "Run property, mutation, fuzz, hostile-input, determinism, worker-count, cancellation, crash recovery, security, performance, disk, and memory suites",
  "generation.md", "worldgen.conformance.hardening.HARDENING_MATRIX", "validation_report", "hardening-suites", "tests/test_hardening_matrix_p8c05h.py::test_hardening_matrix_has_one_owned_case_per_required_category", status="complete")
_r("WG-INTEGRATION-014", "Emit first differing artifact/path/JSON pointer/byte offset on determinism failure",
  "generation.md", "worldgen.determinism_diff.DeterminismDifference, worldgen.determinism_diff.first_artifact_repository_difference", "validation_report", "determinism-diff-reporter", "tests/test_determinism_diff_p8c05h.py::test_typed_first_difference_contains_complete_diagnostics", status="complete")

# ═══════════════════════════════════════════════════════════════════════
# Known defects — characterization fixtures, never target golden output
# ═══════════════════════════════════════════════════════════════════════

_r("WG-PHYS-drainage-sink", "Drainage sinks: prototype does not guarantee every cell drains to ocean or closed basin",
  "worldgen-legacy.generated.md", "worldgen.hydrology.generate_hydrology", "hydrology", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_drainage_sink_regression_has_declared_termination", "obsolete")
_r("WG-HIST-skipped-years", "Skipped history years: prototype can skip years near world end",
  "worldgen-legacy.generated.md", "worldgen.simulation.scheduler.simulate_world", "history_events", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_skipped_year_regression_preserves_exact_final_snapshot", "obsolete")
_r("WG-INTEGRATION-order-dependence", "Order dependence: prototype output can differ based on iteration order",
  "worldgen-legacy.generated.md", "worldgen.numeric.deterministic_map", "kernel", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_order_dependence_regression_worker_counts_match", "obsolete")
_r("WG-LOCAL-incomplete-maps", "Incomplete local maps: prototype local maps may be missing for some sites",
  "worldgen-legacy.generated.md", "worldgen.local_maps.generate_local_maps", "local_maps", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_incomplete_local_map_regression_covers_every_site", "obsolete")
_r("WG-KERNEL-mutable-overrides", "Mutable overrides: prototype allows later mutation of already-committed facts",
  "worldgen-rewrite.md", "domain.run_spec.WorldSpec", "kernel", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_mutable_override_regression_rejects_committed_spec_changes", "obsolete")
_r("WG-KERNEL-inconsistent-ids", "Inconsistent IDs: prototype stable IDs can differ between runs",
  "worldgen-rewrite.md", "worldgen.numeric.stable_id", "kernel", "defect-regression", "tests/worldgen/test_defect_regressions_p8c05a.py::test_inconsistent_id_regression_has_literal_stable_vector", "obsolete")


# ── Validation ────────────────────────────────────────────────────────

def validate_requirements(requirements: Iterable[Requirement] = REQUIREMENTS) -> list[str]:
    """Validate the requirement catalog for duplicates and missing fields.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    seen: set[str] = set()
    valid_statuses = {"complete", "partial", "missing", "obsolete"}
    valid_sources = {"generation.md", "worldgen-rewrite.md", "worldgen-legacy.generated.md",
                     "worldgen-coverage.generated.md"}
    id_pattern = re.compile(r"^WG-(KERNEL|PHYS|ECO|ROUTE|SOC|HIST|LOCAL|INTEGRATION)-[A-Za-z0-9][A-Za-z0-9-]*$")
    for req in requirements:
        if req.id in seen:
            errors.append(f"duplicate requirement ID: {req.id}")
        seen.add(req.id)
        if not id_pattern.fullmatch(req.id):
            errors.append(f"invalid requirement ID: {req.id}")
        for field_name in ("description", "target_symbol", "artifact_kind", "validator", "test"):
            if not str(getattr(req, field_name)).strip():
                errors.append(f"empty {field_name}: {req.id}")
        if req.source_doc not in valid_sources:
            errors.append(f"unknown source_doc: {req.id}: {req.source_doc}")
        if req.status not in valid_statuses:
            errors.append(f"unknown status: {req.id}: {req.status}")
        try:
            requirement_owner(req.id)
        except ValueError as error:
            errors.append(str(error))
        if req.status == "complete" and not req.test.strip():
            errors.append(f"completed row without test: {req.id}")
    return errors
