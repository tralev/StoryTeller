import ast
import hashlib
from pathlib import Path

from src.worldgen.artifacts import canonical_json
from src.worldgen.grid import GridSpec
from src.worldgen.weather import (directional_moisture_pass, prevailing_wind_mmps,
                                  solar_temperature_millic)


def test_weather_has_no_raw_division_operators():
    source = Path("src/worldgen/weather.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FloorDiv, ast.Div))
    ]


def test_climate_is_byte_deterministic(physical_world):
    _, _, climate, *_ = physical_world
    assert hashlib.sha256(canonical_json(climate)).hexdigest() == (
        "b83d90d39a384e3c230daeeabe098922e8fd524c6982b66b768146206ab17ab9"
    )


def test_four_seasons_and_integer_ranges(physical_world):
    terrain, _, climate, *_ = physical_world
    assert len(climate.seasons) == 4
    assert all(isinstance(value, int) for season in climate.seasons for value in season.temperature_millic.values)
    assert all(-80_000 <= value <= 60_000 for season in climate.seasons for value in season.temperature_millic.values)
    assert len(climate.annual_precipitation_mm.values) == terrain.grid.cell_count


def test_seasonal_temperature_gradient(physical_world):
    """P8.C05C: At high latitude, summer is warmer than winter."""
    terrain, _, climate, *_ = physical_world
    summer = climate.seasons[2]  # index 2 = summer (seasonal_sign=1)
    winter = climate.seasons[0]  # index 0 = winter (seasonal_sign=-1)
    # Pick a high-latitude land cell (top row or bottom row) where seasonal
    # variation is strongest — global averages can cancel on small grids.
    high_lat = max(
        (i for i in terrain.grid.indices() if terrain.land.values[i]),
        key=lambda i: abs(terrain.grid.coordinate(i).y - terrain.grid.height // 2),
        default=0,
    )
    summer_t = summer.temperature_millic.values[high_lat]
    winter_t = winter.temperature_millic.values[high_lat]
    if terrain.grid.coordinate(high_lat).y >= terrain.grid.height // 2:
        assert summer_t >= winter_t
    else:
        assert winter_t >= summer_t


def test_solar_temperature_is_symmetric_and_responds_to_tilt_and_elevation():
    north, south = -750_000, 750_000
    tilt = 23_500
    assert solar_temperature_millic(north, 0, tilt, 0) == solar_temperature_millic(
        south, 0, tilt, 2,
    )
    assert solar_temperature_millic(north, 0, tilt, 2) == solar_temperature_millic(
        south, 0, tilt, 0,
    )
    assert solar_temperature_millic(north, 0, 0, 0) == solar_temperature_millic(
        north, 0, 0, 2,
    )
    low_tilt_range = abs(
        solar_temperature_millic(north, 0, 10_000, 0)
        - solar_temperature_millic(north, 0, 10_000, 2)
    )
    high_tilt_range = abs(
        solar_temperature_millic(north, 0, 30_000, 0)
        - solar_temperature_millic(north, 0, 30_000, 2)
    )
    assert high_tilt_range > low_tilt_range > 0
    assert (solar_temperature_millic(0, 1_000, tilt, 1)
            == solar_temperature_millic(0, 0, tilt, 1) - 6_000)


def test_precipitation_is_non_negative(physical_world):
    """P8.C05C: All precipitation values must be non-negative."""
    _, _, climate, *_ = physical_world
    for season in climate.seasons:
        assert all(p >= 0 for p in season.precipitation_mm.values)


def test_seasonal_water_ledgers_snow_ice_and_storms_are_exact(physical_world):
    _, _, climate, *_ = physical_world
    assert len(climate.water_ledger) == len(climate.seasons) == 4
    for index, (season, ledger) in enumerate(zip(climate.seasons, climate.water_ledger)):
        assert ledger.season == index
        assert ledger.precipitation_total_mm == sum(season.precipitation_mm.values)
        assert ledger.evaporation_total_mm == sum(season.evaporation_mm.values)
        assert ledger.snowpack_total_mm == sum(season.snowpack_mm.values)
        assert ledger.ice_cell_count == sum(season.ice.values)
        assert ledger.final_atmospheric_moisture_mm >= 0
        assert all(0 <= evaporation <= rain for evaporation, rain in zip(
            season.evaporation_mm.values, season.precipitation_mm.values,
        ))
        assert all(0 <= value <= 1_000_000 for value in season.storm_ppm.values)
        assert all(value in (0, 1) for value in season.ice.values)
        assert all(
            snow == 0 or temperature <= 0
            for snow, temperature in zip(
                season.snowpack_mm.values, season.temperature_millic.values,
            )
        )


def test_prevailing_wind_cells_and_orographic_rain_shadow_are_deterministic():
    assert prevailing_wind_mmps(0, 1) == (-3_500, 0)
    assert prevailing_wind_mmps(500_000, 1) == (4_000, 0)
    assert prevailing_wind_mmps(900_000, 1) == (-3_000, 0)
    grid = GridSpec(7, 1, 1_000)
    elevation = (0, 0, 400, 800, 400, 0, 0)
    land = (0, 1, 1, 1, 1, 1, 1)
    moisture = (1_200, 100, 100, 100, 100, 100, 100)
    eastward = tuple(4_000 for _ in grid.indices())
    still = tuple(0 for _ in grid.indices())
    first = directional_moisture_pass(grid, elevation, land, moisture, eastward, still)
    second = directional_moisture_pass(grid, elevation, land, moisture, eastward, still)
    assert first == second
    updated, lift, shadow = first
    assert lift[2] > 0 and lift[3] > 0
    assert shadow[4] > 0 and shadow[5] > 0
    assert all(0 <= value <= 2_500 for value in updated)


def test_weather_regime_covers_all_cells(physical_world):
    """P8.C05C: Every cell has a weather regime classification."""
    terrain, _, climate, *_ = physical_world
    assert len(climate.weather_regime.values) == terrain.grid.cell_count
    assert all(0 <= r <= 4 for r in climate.weather_regime.values)


def test_ocean_temperature_stays_within_plausible_range(physical_world):
    """P8.C05C-FIXED: Ocean cells have bounded temperature."""
    terrain, _, climate, *_ = physical_world
    for i in terrain.grid.indices():
        if not terrain.land.values[i]:
            for season in climate.seasons:
                t = season.temperature_millic.values[i]
                assert -50_000 <= t <= 50_000, f"ocean temp out of range: {t} at {i}"
