from __future__ import annotations

import pytest

from src.worldgen.geology import generate_geology
from src.worldgen.grid import GridSpec
from src.worldgen.hydrology import generate_hydrology
from src.worldgen.physical_biomes import classify_physical_biomes
from src.worldgen.physical_regions import generate_regions
from src.worldgen.physical_terrain import generate_physical_terrain
from src.worldgen.resources import generate_resources
from src.worldgen.routes import generate_routes
from src.worldgen.soil import generate_soil
from src.worldgen.weather import generate_weather


@pytest.fixture(scope="module")
def physical_world():
    grid = GridSpec(32, 32, 8_000)
    terrain = generate_physical_terrain(
        grid, 42, continent_count=1, plate_count=4, erosion_passes=2
    )
    hydrology = generate_hydrology(terrain)
    climate = generate_weather(
        terrain, hydrology, axial_tilt_millidegrees=23_500, relaxation_passes=8
    )
    soil = generate_soil(terrain, generate_geology(terrain), hydrology, climate)
    biomes = classify_physical_biomes(terrain, hydrology, climate, soil)
    resources = generate_resources(terrain, biomes, 42)
    regions = generate_regions(terrain, hydrology, climate, biomes)
    routes = generate_routes(terrain, hydrology, climate, resources, regions)
    return terrain, hydrology, climate, biomes, resources, regions, routes
