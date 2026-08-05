def test_hydrology_coverage_and_river_continuity(physical_world):
    terrain, hydrology, *_ = physical_world
    assert len(hydrology.flow_to.values) == terrain.grid.cell_count
    assert all(edge.discharge_m3s > 0 for edge in hydrology.rivers)
    assert all(hydrology.flow_to.values[edge.upstream] == edge.downstream for edge in hydrology.rivers)
    assert all(edge.upstream != edge.downstream for edge in hydrology.rivers)


def test_coastline_is_land_adjacent_to_ocean(physical_world):
    terrain, hydrology, *_ = physical_world
    for index, coastal in enumerate(hydrology.coastline.values):
        if coastal:
            assert terrain.land.values[index]
            assert any(not terrain.land.values[n] for n in terrain.grid.neighbors4(index))
