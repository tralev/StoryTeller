"""Shared test fixtures and helpers for all test modules."""

from __future__ import annotations

import json
import os
from typing import Any, cast

import pytest


@pytest.fixture(scope="session")
def phase4_world(tmp_path_factory):
    """Small self-contained physical+historical repository for Phase 4 tests."""
    from src.domain.run_spec import WorldSpec
    from src.worldgen.physical_pipeline import generate_physical_world
    from src.worldgen.simulation.scheduler import simulate_world

    root = tmp_path_factory.mktemp("phase4-world")
    physical, historical = root / "physical", root / "historical"
    spec = WorldSpec(
        width=32,
        height=32,
        continent_count=1,
        plate_count=4,
        minimum_continent_cells=1,
        civilization_count=3,
        erosion_passes=1,
        climate_relaxation_passes=8,
    )
    generate_physical_world(spec, 17, physical)
    simulate_world(physical, 20, historical)
    return historical


@pytest.fixture(scope="session")
def phase5_project(tmp_path_factory, phase4_world):
    from src.narrative.pipeline import generate_narrative
    from src.world.builder import WorldBuilderV2

    root = tmp_path_factory.mktemp("phase5-project")
    phase4, phase5 = root / "phase4", root / "phase5"
    WorldBuilderV2().build(phase4_world, "The Test Continent", phase4)
    generate_narrative(phase4_world, phase4 / "bible.json", phase5, workers=3)
    return phase4_world, phase4, phase5


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename: str) -> dict[str, Any]:
    """Load a JSON fixture file from tests/fixtures/."""
    with open(os.path.join(FIXTURES_DIR, filename)) as f:
        return cast(dict[str, Any], json.load(f))
