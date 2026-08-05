"""Four-season fixed-point climate and weather regimes."""
from __future__ import annotations

from .grid import IntGrid
from .physical_models import ClimateLayer, Hydrology, SeasonProfile, Terrain

ALGORITHM_VERSION = 1


def generate_weather(terrain: Terrain, hydrology: Hydrology, *, axial_tilt_millidegrees: int,
                     relaxation_passes: int) -> ClimateLayer:
    grid = terrain.grid
    seasons: list[SeasonProfile] = []
    tilt = axial_tilt_millidegrees * 18 // 100
    for season, seasonal_sign in enumerate((-1, 0, 1, 0)):
        temperatures: list[int] = []
        precipitation: list[int] = []
        wind_x: list[int] = []
        wind_y: list[int] = []
        hazards: list[int] = []
        moisture = [0] * grid.cell_count
        for index in grid.indices():
            point = grid.coordinate(index)
            latitude_ppm = abs(2 * point.y - (grid.height - 1)) * 1_000_000 // max(1, grid.height - 1)
            temp = 30_000 - latitude_ppm * 55_000 // 1_000_000
            temp += seasonal_sign * tilt * (1 if point.y >= grid.height // 2 else -1)
            temp -= max(0, terrain.elevation_mm.values[index]) * 6
            temperatures.append(max(-80_000, min(60_000, temp)))
            wind_x.append(4_000 if latitude_ppm < 650_000 else -3_000)
            wind_y.append((season - 2) * 400)
            moisture[index] = 1_200 if not terrain.land.values[index] else hydrology.aquifer_capacity_mm.values[index] // 4
        # Integer synchronous relaxation; bounded passes are part of the algorithm version.
        for _ in range(relaxation_passes):
            updated = moisture[:]
            for index in grid.indices():
                if not terrain.land.values[index]:
                    continue
                neighbors = grid.neighbors4(index)
                incoming = sum(moisture[n] for n in neighbors) // max(1, len(neighbors))
                shadow = terrain.slope_ppm.values[index] // 20
                updated[index] = max(0, min(2_500, (3 * moisture[index] + incoming) // 4 - shadow))
            moisture = updated
        for index in grid.indices():
            rain = max(0, moisture[index] + (200 if hydrology.coastline.values[index] else 0))
            precipitation.append(rain)
            hazards.append(min(1_000_000, abs(wind_x[index]) * 50 + rain * 120
                               + (300_000 if hydrology.glacier.values[index] else 0)))
        seasons.append(SeasonProfile(IntGrid(grid, tuple(temperatures)), IntGrid(grid, tuple(precipitation)),
                                     IntGrid(grid, tuple(wind_x)), IntGrid(grid, tuple(wind_y)),
                                     IntGrid(grid, tuple(hazards))))
    annual_temp = tuple(sum(s.temperature_millic.values[i] for s in seasons) // 4 for i in grid.indices())
    annual_rain = tuple(sum(s.precipitation_mm.values[i] for s in seasons) for i in grid.indices())
    regime = tuple(0 if not terrain.land.values[i] else
                   (1 if annual_temp[i] < 0 else 2 if annual_rain[i] < 1_000 else 3 if annual_rain[i] < 4_000 else 4)
                   for i in grid.indices())
    return ClimateLayer(ALGORITHM_VERSION, tuple(seasons), IntGrid(grid, annual_temp),
                        IntGrid(grid, annual_rain), IntGrid(grid, regime))
