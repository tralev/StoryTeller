def test_four_seasons_and_integer_ranges(physical_world):
    terrain, _, climate, *_ = physical_world
    assert len(climate.seasons) == 4
    assert all(isinstance(value, int) for season in climate.seasons for value in season.temperature_millic.values)
    assert all(-80_000 <= value <= 60_000 for season in climate.seasons for value in season.temperature_millic.values)
    assert len(climate.annual_precipitation_mm.values) == terrain.grid.cell_count
