from src.worldgen.artifacts import WorldArtifactRepository


def test_sites_are_on_land_and_in_regions(simulated_world):
    physical, historical, _ = simulated_world
    physical_repo = WorldArtifactRepository(physical / "artifacts")
    sim_repo = WorldArtifactRepository(historical / "artifacts")
    terrain = physical_repo.load_verified("terrain").payload
    regions = physical_repo.load_verified("regions").payload
    sites = sim_repo.load_verified("sites").payload
    region_cells = {region["region_id"]: set(region["cells"]) for region in regions["regions"]}
    assert all(terrain["land"]["values"][site["cell"]] for site in sites)
    assert all(site["cell"] in region_cells[site["region_id"]] for site in sites)
    assert all(site["water_access"] or site["resource_access"] for site in sites)


def test_territory_is_nonoverlapping(simulated_world):
    _, historical, _ = simulated_world
    civilizations = WorldArtifactRepository(historical / "artifacts").load_verified("civilizations").payload
    territories = [region for civilization in civilizations for region in civilization["territory"]]
    assert len(territories) == len(set(territories))
