from src.worldgen.validation import validate_physical_world


def test_region_ownership_adjacency_and_routes(physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    validate_physical_world(terrain, hydrology, climate, biomes, resources, regions, routes)
    land = {i for i, value in enumerate(terrain.land.values) if value}
    assert land == {cell for region in regions.regions for cell in region.cells}
    neighbors = {region.region_id: set(region.neighbors) for region in regions.regions}
    assert all(region.region_id in neighbors[other] for region in regions.regions for other in region.neighbors)
