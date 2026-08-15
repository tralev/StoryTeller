import pytest

from src.worldgen.grid import GridSpec
from src.worldgen.geology import generate_geology
from src.worldgen.hydrology import generate_hydrology
from src.worldgen.physical_biomes import classify_physical_biomes
from src.worldgen.physical_regions import generate_regions
from src.worldgen.physical_terrain import generate_physical_terrain
from src.worldgen.resources import generate_resources
from src.worldgen.routes import generate_routes
from src.worldgen.soil import generate_soil
from src.worldgen.validation import validate_physical_world
from src.worldgen.weather import generate_weather


@pytest.mark.worldgen_property
@pytest.mark.parametrize("seed,continents", [(0, 1), (1, 2), (99, 3), (2**31, 1)])
def test_randomized_specs_hold_all_physical_invariants(seed, continents):
    grid = GridSpec(32 + seed % 5, 32 + seed % 7, 4_000)
    terrain = generate_physical_terrain(grid, seed, continent_count=continents,
                                        plate_count=max(4, continents), erosion_passes=3)
    hydrology = generate_hydrology(terrain)
    climate = generate_weather(terrain, hydrology, axial_tilt_millidegrees=23_500, relaxation_passes=8)
    soil = generate_soil(terrain, generate_geology(terrain), hydrology, climate)
    biomes = classify_physical_biomes(terrain, hydrology, climate, soil)
    resources = generate_resources(terrain, biomes, seed)
    regions = generate_regions(terrain, hydrology, climate, biomes)
    routes = generate_routes(terrain, hydrology, climate, resources, regions)
    validate_physical_world(terrain, hydrology, climate, soil, biomes, resources, regions, routes)
