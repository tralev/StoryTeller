import pytest
from dataclasses import replace

from src.domain.run_spec import WorldSpec
from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.physical_pipeline import generate_physical_world
from src.worldgen.simulation.replay import validate_simulation_directory
from src.worldgen.simulation.scheduler import simulate_world
from src.worldgen.simulation.history_clock import build_history_clock, validate_history_clock


@pytest.mark.history_property
@pytest.mark.parametrize("seed,years", [(0, 0), (1, 3), (99, 10)])
def test_history_is_deterministic_and_replayable(tmp_path, seed, years):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, civilization_count=3,
                     erosion_passes=1, climate_relaxation_passes=8)
    physical = tmp_path / "physical"
    generate_physical_world(spec, seed, physical)
    first, second = tmp_path / "first", tmp_path / "second"
    result_a = simulate_world(physical, years, first)
    result_b = simulate_world(physical, years, second)
    assert result_a["simulation_index"] == result_b["simulation_index"]
    assert WorldArtifactRepository(first / "artifacts").load_verified("history").sha256 == \
           WorldArtifactRepository(second / "artifacts").load_verified("history").sha256
    assert validate_simulation_directory(first)["present_year"] == years
    clock = WorldArtifactRepository(first / "artifacts").load_verified("history_clock").payload
    assert len(clock) == years * 12
    assert [(tick["year"], tick["month"]) for tick in clock] == [
        (year, month) for year in range(1, years + 1) for month in range(1, 13)
    ]
    history_ids = [event["event_id"] for event in
                   WorldArtifactRepository(first / "artifacts").load_verified("history").payload]
    assert [event_id for tick in clock for event_id in tick["accepted_event_ids"]] == history_ids


def test_history_clock_rejects_missing_reordered_and_forged_ticks():
    clock = build_history_clock(2, ())
    validate_history_clock(2, clock, ())
    with pytest.raises(ValueError, match="HISTORY-CLOCK"):
        validate_history_clock(2, clock[:-1], ())
    with pytest.raises(ValueError, match="HISTORY-CLOCK"):
        validate_history_clock(2, (clock[1], clock[0], *clock[2:]), ())
    with pytest.raises(ValueError, match="HISTORY-CLOCK"):
        validate_history_clock(2, (replace(clock[0], accepted_event_ids=("forged",)),
                                   *clock[1:]), ())
