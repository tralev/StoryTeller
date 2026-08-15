from src.worldgen.artifacts import WorldArtifactRepository
from dataclasses import replace

from src.worldgen.terrain_reader import VerifiedTerrainReader
from src.worldgen.simulation.scheduler import _load_physical
from src.worldgen.simulation.scheduler import simulate_world
import pytest

from src.worldgen.simulation.sites import (
    SITE_SCORE_WEIGHTS, CivilizationCapacityError, found_sites, score_site,
    validate_site_lifecycle,
)
from src.worldgen.simulation.replay import _state
from src.worldgen.simulation.relationships import (
    Household, PersonalRelationship, SocialAnchor, generate_relationships,
    validate_relationships,
)


def test_sites_are_on_land_and_in_regions(simulated_world):
    physical, historical, _ = simulated_world
    physical_repo = WorldArtifactRepository(physical / "artifacts")
    sim_repo = WorldArtifactRepository(historical / "artifacts")
    terrain = VerifiedTerrainReader(physical).load().terrain
    regions = physical_repo.load_verified("regions").payload
    sites = sim_repo.load_verified("sites").payload
    region_cells = {region["region_id"]: set(region["cells"]) for region in regions["regions"]}
    assert all(terrain.land.values[site["cell"]] for site in sites)
    assert all(site["cell"] in region_cells[site["region_id"]] for site in sites)
    assert all(site["water_access"] or site["resource_access"] for site in sites)
    expected_components = {name for name, _ in SITE_SCORE_WEIGHTS}
    assert all({name for name, _ in site["score_components"]} == expected_components
               for site in sites)
    assert all(0 <= value <= 1_000_000 for site in sites
               for _, value in site["score_components"])


def test_territory_is_nonoverlapping(simulated_world):
    _, historical, _ = simulated_world
    civilizations = WorldArtifactRepository(historical / "artifacts").load_verified("civilizations").payload
    territories = [region for civilization in civilizations for region in civilization["territory"]]
    assert len(territories) == len(set(territories))


def test_configured_civilization_count_is_exact(simulated_world):
    physical, historical, _ = simulated_world
    physical_spec = WorldArtifactRepository(physical / "artifacts").load_verified(
        "world_index"
    ).payload["spec"]
    repository = WorldArtifactRepository(historical / "artifacts")
    requested = int(physical_spec["civilization_count"])
    assert len(repository.load_verified("sites").payload) == requested
    assert len(repository.load_verified("civilizations").payload) == requested


def test_site_score_is_explainable_pressure_sensitive_and_recomputed(simulated_world):
    physical_root, historical, _ = simulated_world
    physical, _, _ = _load_physical(physical_root)
    sites = WorldArtifactRepository(historical / "artifacts").load_verified("sites").payload
    regions = {str(region["region_id"]): region for region in physical["regions"]["regions"]}
    for site in sites:
        score = score_site(physical, regions[str(site["region_id"])], int(site["cell"]))
        assert score.total_ppm == site["suitability_ppm"]
        assert score.components == tuple(tuple(item) for item in site["score_components"])

    site = sites[0]
    cell, region = int(site["cell"]), regions[str(site["region_id"])]
    baseline = score_site(physical, region, cell)
    seasons = tuple(replace(season, hazard_ppm=replace(
        season.hazard_ppm,
        values=tuple(1_000_000 if index == cell else value
                     for index, value in enumerate(season.hazard_ppm.values)),
    )) for season in physical["climate_typed"].seasons)
    hazardous = dict(physical)
    hazardous["climate_typed"] = replace(physical["climate_typed"], seasons=seasons)
    hazardous["climate"] = {
        **physical["climate"],
        "seasons": tuple({**season, "hazard_ppm": {
            **season["hazard_ppm"], "values": tuple(
                1_000_000 if index == cell else value
                for index, value in enumerate(season["hazard_ppm"]["values"]))
        }} for season in physical["climate"]["seasons"]),
    }
    pressured = score_site(hazardous, region, cell)
    assert pressured.safety_ppm < baseline.safety_ppm
    assert pressured.total_ppm < baseline.total_ppm


def test_site_selection_has_stable_cell_and_region_tie_breaking(simulated_world):
    physical_root, _, _ = simulated_world
    physical, _, _ = _load_physical(physical_root)
    assert found_sites(42, physical, 4) == found_sites(42, physical, 4)
    assert tuple(site.suitability_ppm for site in found_sites(42, physical, 4)) == tuple(sorted(
        (site.suitability_ppm for site in found_sites(42, physical, 4)), reverse=True
    ))


def test_infeasible_civilization_count_has_stable_capacity_diagnostic(simulated_world):
    physical_root, _, _ = simulated_world
    physical, _, _ = _load_physical(physical_root)
    requested = len(physical["regions"]["regions"]) + 1
    with pytest.raises(CivilizationCapacityError) as first:
        found_sites(42, physical, requested)
    with pytest.raises(CivilizationCapacityError) as second:
        found_sites(42, physical, requested)
    assert str(first.value) == str(second.value) == (
        f"WG-CIV-CAPACITY: requested={requested}; "
        f"viable_regions={first.value.diagnostic.viable_regions}; "
        f"total_regions={len(physical['regions']['regions'])}"
    )
    assert first.value.diagnostic == second.value.diagnostic
    assert first.value.diagnostic.viable_regions < requested


def test_capacity_failure_precedes_output_publication(simulated_world, tmp_path, monkeypatch):
    physical_root, _, _ = simulated_world
    physical, artifact_ids, file_hashes = _load_physical(physical_root)
    requested = len(physical["regions"]["regions"]) + 1
    impossible = dict(physical)
    impossible["world_index"] = {
        **physical["world_index"],
        "spec": {**physical["world_index"]["spec"], "civilization_count": requested},
    }
    monkeypatch.setattr(
        "src.worldgen.simulation.scheduler._load_physical",
        lambda _root: (impossible, artifact_ids, file_hashes),
    )
    output = tmp_path / "must-not-exist"
    with pytest.raises(CivilizationCapacityError, match="WG-CIV-CAPACITY"):
        simulate_world(physical_root, 0, output)
    assert not output.exists()


def test_site_lifecycle_rejects_mutation_deletion_forgery_and_dangling_settlement(simulated_world):
    _, historical, _ = simulated_world
    snapshot = WorldArtifactRepository(historical / "artifacts").load_verified(
        "snapshots"
    ).payload[0]["state"]
    state = _state(snapshot)
    validate_site_lifecycle(42, state.sites, state.sites, state.settlements)

    with pytest.raises(ValueError, match="SITE-IMMUTABLE"):
        validate_site_lifecycle(42, state.sites,
                                (replace(state.sites[0], cell=state.sites[0].cell + 1),)
                                + state.sites[1:], state.settlements)
    with pytest.raises(ValueError, match="SITE-IMMUTABLE"):
        validate_site_lifecycle(42, state.sites, state.sites[:-1], state.settlements)
    forged = (replace(state.sites[0], site_id="site_00000000000000000000000000000000"),) \
        + state.sites[1:]
    with pytest.raises(ValueError, match="SITE-ID"):
        validate_site_lifecycle(42, forged, forged, state.settlements)
    dangling = (replace(state.settlements[0], site_id="site_missing"),) + state.settlements[1:]
    with pytest.raises(ValueError, match="SITE-REFERENCE"):
        validate_site_lifecycle(42, state.sites, state.sites, dangling)


def test_every_snapshot_and_final_site_artifact_equal_genesis(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    snapshots = repository.load_verified("snapshots").payload
    genesis_sites = snapshots[0]["state"]["sites"]
    assert all(snapshot["state"]["sites"] == genesis_sites for snapshot in snapshots)
    assert repository.load_verified("sites").payload == genesis_sites


def test_households_conserve_cohorts_and_relationships_are_typed_and_retained(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    households, people, relationships = generate_relationships(
        42, state.cohorts, state.settlements, state.year,
    )
    validate_relationships(households, people, relationships,
                           state.cohorts, state.settlements)
    totals = {cohort.cohort_id: 0 for cohort in state.cohorts}
    for household in households:
        totals[household.cohort_id] += household.member_count
    assert totals == {cohort.cohort_id: cohort.population for cohort in state.cohorts}
    assert {relation.relationship_type for relation in relationships} >= {
        "spouse", "parent_of", "mentor",
    }
    assert not ({"race", "ancestry", "ethnicity"} & Household.__dataclass_fields__.keys())
    assert not ({"race", "ancestry", "ethnicity"} & SocialAnchor.__dataclass_fields__.keys())
    payload = repository.load_verified("peoples").payload
    assert len(payload["households"]) == len(households)
    assert len(payload["people"]) == len(people)
    assert len(payload["relationships"]) == len(relationships)


def test_relationship_validator_rejects_population_drift_and_dangling_edges(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    households, people, relationships = generate_relationships(
        42, state.cohorts, state.settlements, state.year,
    )
    with pytest.raises(ValueError, match="HOUSEHOLD-CONSERVATION"):
        validate_relationships(
            (replace(households[0], member_count=households[0].member_count - 1),
             *households[1:]), people, relationships, state.cohorts, state.settlements,
        )
    forged = PersonalRelationship(
        "personal_relationship_00000000000000000000000000000000",
        people[0].person_id, "person_missing", "mentor", 0,
    )
    with pytest.raises(ValueError, match="RELATIONSHIP-EDGE"):
        validate_relationships(households, people, (*relationships, forged),
                               state.cohorts, state.settlements)
