"""Four-season fixed-point climate and weather regimes."""
from __future__ import annotations

from .grid import GridSpec, IntGrid
from .numeric import div_round_half_up
from .physical_models import (ClimateLayer, ClimateWaterLedger, Hydrology,
                              SeasonProfile, Terrain)

ALGORITHM_VERSION = 4

LATITUDE_SCALE = 1_000_000
EQUATOR_TEMPERATURE_MILLIC = 30_000
POLE_COOLING_MILLIC = 55_000
LAPSE_MILLIC_PER_ELEVATION_MM = 6
SEASON_DECLINATION_SIGNS: tuple[int, int, int, int] = (-1, 0, 1, 0)
SEASON_MERIDIONAL_WIND_MMPS: tuple[int, int, int, int] = (-400, 0, 400, 0)


def solar_temperature_millic(
    signed_latitude_ppm: int, elevation_mm: int, axial_tilt_millidegrees: int,
    season: int,
) -> int:
    """Approximate seasonal solar forcing using fixed-point angular distance.

    Latitude uses -1,000,000 at the north pole and +1,000,000 at the south
    pole. Axial tilt is converted from millidegrees to that same 90-degree
    scale; the four declinations are north solstice, equinox, south solstice,
    equinox. Elevation applies a 6 °C/km lapse rate when elevation is in mm.
    """
    if not -LATITUDE_SCALE <= signed_latitude_ppm <= LATITUDE_SCALE:
        raise ValueError("WG-CLIMATE-SOLAR: latitude outside fixed-point globe")
    if not 0 <= axial_tilt_millidegrees <= 90_000 or not 0 <= season < 4:
        raise ValueError("WG-CLIMATE-SOLAR: invalid tilt or season")
    tilt_ppm = div_round_half_up(
        axial_tilt_millidegrees * LATITUDE_SCALE, 90_000,
    )
    declination_ppm = SEASON_DECLINATION_SIGNS[season] * tilt_ppm
    solar_distance_ppm = min(
        LATITUDE_SCALE, abs(signed_latitude_ppm - declination_ppm),
    )
    temperature = EQUATOR_TEMPERATURE_MILLIC - div_round_half_up(
        solar_distance_ppm * POLE_COOLING_MILLIC, LATITUDE_SCALE,
    )
    temperature -= max(0, elevation_mm) * LAPSE_MILLIC_PER_ELEVATION_MM
    return max(-80_000, min(60_000, temperature))


def prevailing_wind_mmps(signed_latitude_ppm: int, season: int) -> tuple[int, int]:
    """Return frozen three-cell circulation bands plus seasonal meridional flow."""
    if not -LATITUDE_SCALE <= signed_latitude_ppm <= LATITUDE_SCALE or not 0 <= season < 4:
        raise ValueError("WG-CLIMATE-WIND: invalid latitude or season")
    latitude = abs(signed_latitude_ppm)
    if latitude >= 666_667:
        zonal = -3_000  # polar easterlies
    elif latitude >= 333_333:
        zonal = 4_000  # mid-latitude westerlies
    else:
        zonal = -3_500  # tropical trade winds
    meridional = SEASON_MERIDIONAL_WIND_MMPS[season]
    return zonal, meridional if signed_latitude_ppm >= 0 else -meridional


def directional_moisture_pass(
    grid: GridSpec, elevation_mm: tuple[int, ...], land: tuple[int, ...],
    moisture_mm: tuple[int, ...], wind_x_mmps: tuple[int, ...],
    wind_y_mmps: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Apply one immutable upwind transport pass with lift and rain shadow."""
    inputs = (elevation_mm, land, moisture_mm, wind_x_mmps, wind_y_mmps)
    if any(len(values) != grid.cell_count for values in inputs):
        raise ValueError("WG-CLIMATE-MOISTURE: input coverage mismatch")
    updated = list(moisture_mm)
    lift = [0] * grid.cell_count
    shadow = [0] * grid.cell_count
    for index in grid.indices():
        if not land[index]:
            continue
        point = grid.coordinate(index)
        upstream_x = point.x + (-1 if wind_x_mmps[index] > 0 else
                                1 if wind_x_mmps[index] < 0 else 0)
        upstream_y = point.y + (-1 if wind_y_mmps[index] > 0 else
                                1 if wind_y_mmps[index] < 0 else 0)
        if not (0 <= upstream_x < grid.width and 0 <= upstream_y < grid.height):
            continue
        upstream = grid.index(upstream_x, upstream_y)
        elevation_change = elevation_mm[index] - elevation_mm[upstream]
        lift[index] = min(600, div_round_half_up(max(0, elevation_change), 4))
        shadow[index] = min(600, div_round_half_up(max(0, -elevation_change), 4))
        transported = div_round_half_up(3 * moisture_mm[index] + moisture_mm[upstream], 4)
        updated[index] = max(0, min(2_500, transported - lift[index] - shadow[index]))
    return tuple(updated), tuple(lift), tuple(shadow)


def generate_weather(terrain: Terrain, hydrology: Hydrology, *, axial_tilt_millidegrees: int,
                     relaxation_passes: int) -> ClimateLayer:
    grid = terrain.grid
    seasons: list[SeasonProfile] = []
    water_ledger: list[ClimateWaterLedger] = []
    for season in range(4):
        temperatures: list[int] = []
        precipitation: list[int] = []
        evaporation: list[int] = []
        snowpack: list[int] = []
        ice: list[int] = []
        storms: list[int] = []
        wind_x: list[int] = []
        wind_y: list[int] = []
        hazards: list[int] = []
        moisture = [0] * grid.cell_count
        for index in grid.indices():
            point = grid.coordinate(index)
            signed_latitude_ppm = div_round_half_up(
                (2 * point.y - (grid.height - 1)) * LATITUDE_SCALE,
                max(1, grid.height - 1),
            )
            temperatures.append(solar_temperature_millic(
                signed_latitude_ppm, terrain.elevation_mm.values[index],
                axial_tilt_millidegrees, season,
            ))
            zonal, meridional = prevailing_wind_mmps(signed_latitude_ppm, season)
            wind_x.append(zonal)
            wind_y.append(meridional)
            moisture[index] = (
                1_200 if not terrain.land.values[index]
                else div_round_half_up(hydrology.aquifer_capacity_mm.values[index], 4)
            )
        lift = tuple(0 for _ in grid.indices())
        shadow = lift
        # Immutable integer passes; the configured bound is part of the algorithm version.
        for _ in range(relaxation_passes):
            relaxed, lift, shadow = directional_moisture_pass(
                grid, terrain.elevation_mm.values, terrain.land.values,
                tuple(moisture), tuple(wind_x), tuple(wind_y),
            )
            moisture = list(relaxed)
        for index in grid.indices():
            rain = max(0, moisture[index] + lift[index] - shadow[index]
                       + (200 if hydrology.coastline.values[index] else 0))
            precipitation.append(rain)
            evaporated = min(rain, div_round_half_up(
                max(0, temperatures[index] + 10_000), 100,
            ))
            evaporation.append(evaporated)
            retained = rain - evaporated
            snow = retained if temperatures[index] <= 0 else 0
            snowpack.append(snow)
            ice.append(int(temperatures[index] <= -10_000 and snow >= 100))
            storm = min(1_000_000, rain * 180 + abs(wind_x[index]) * 60
                        + abs(wind_y[index]) * 80)
            storms.append(storm)
            hazards.append(min(1_000_000, storm + rain * 40
                               + (300_000 if hydrology.glacier.values[index] else 0)))
        seasons.append(SeasonProfile(
            IntGrid(grid, tuple(temperatures)), IntGrid(grid, tuple(precipitation)),
            IntGrid(grid, tuple(evaporation)), IntGrid(grid, tuple(snowpack)),
            IntGrid(grid, tuple(ice)), IntGrid(grid, tuple(storms)),
            IntGrid(grid, tuple(wind_x)), IntGrid(grid, tuple(wind_y)),
            IntGrid(grid, tuple(hazards)),
        ))
        water_ledger.append(ClimateWaterLedger(
            season, sum(precipitation), sum(evaporation), sum(snowpack), sum(ice),
            sum(moisture),
        ))
    annual_temp = tuple(
        div_round_half_up(sum(s.temperature_millic.values[i] for s in seasons), 4)
        for i in grid.indices()
    )
    annual_rain = tuple(sum(s.precipitation_mm.values[i] for s in seasons) for i in grid.indices())
    regime = tuple(0 if not terrain.land.values[i] else
                   (1 if annual_temp[i] < 0 else 2 if annual_rain[i] < 1_000 else 3 if annual_rain[i] < 4_000 else 4)
                   for i in grid.indices())
    return ClimateLayer(ALGORITHM_VERSION, tuple(seasons), tuple(water_ledger), IntGrid(grid, annual_temp),
                        IntGrid(grid, annual_rain), IntGrid(grid, regime))
