from __future__ import annotations

import pytest

from src.domain.run_spec import WorldSpec
from src.worldgen.physical_pipeline import generate_physical_world
from src.worldgen.simulation.scheduler import simulate_world


@pytest.fixture(scope="session")
def simulated_world(tmp_path_factory):
    root = tmp_path_factory.mktemp("phase3")
    physical, historical = root / "physical", root / "historical"
    spec = WorldSpec(
        width=32,
        height=32,
        continent_count=1,
        plate_count=4,
        minimum_continent_cells=1,
        civilization_count=4,
        erosion_passes=2,
        climate_relaxation_passes=8,
    )
    generate_physical_world(spec, 42, physical)
    result = simulate_world(physical, 55, historical)
    return physical, historical, result
