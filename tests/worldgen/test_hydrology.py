import ast
import hashlib
from dataclasses import replace
from pathlib import Path

from src.worldgen.artifacts import canonical_json
from src.worldgen.grid import GridSpec
from src.worldgen.hydrology import (D8_OFFSETS, connected_lakes, d8_neighbors,
                                    priority_flood, route_d8)
from src.worldgen.grid import IntGrid
from src.worldgen.hydrology import generate_hydrology
from src.worldgen.physical_models import DrainageTerminalKind


def test_hydrology_has_no_raw_division_operators():
    source = Path("src/worldgen/hydrology.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FloorDiv, ast.Div))
    ]


def test_hydrology_is_byte_deterministic(physical_world):
    _, hydrology, *_ = physical_world
    assert hashlib.sha256(canonical_json(hydrology)).hexdigest() == (
        "8d1aa02da65cc75ae1685a33850b3d943be28cfd0fa027b7764e5fe4a3307465"
    )


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


def test_every_land_cell_drains_to_ocean_or_closed_basin(physical_world):
    """P8.C05C: Every non-ocean surface cell must drain to ocean or a declared closed basin."""
    terrain, hydrology, *_ = physical_world
    terminal_by_cell = {terminal.cell: terminal for terminal in hydrology.terminals}
    assert tuple(terminal.terminal_id for terminal in hydrology.terminals) == tuple(
        f"terminal_{number:04d}" for number in range(1, len(hydrology.terminals) + 1)
    )
    for index in terrain.grid.indices():
        if not terrain.land.values[index]:
            continue  # ocean — skip
        # Follow flow to termination
        seen: set[int] = set()
        cursor = index
        while hydrology.flow_to.values[cursor] >= 0:
            assert cursor not in seen
            seen.add(cursor)
            cursor = hydrology.flow_to.values[cursor]
        terminal = terminal_by_cell[cursor]
        expected = (DrainageTerminalKind.OCEAN if not terrain.land.values[cursor]
                    else DrainageTerminalKind.CLOSED_BASIN)
        assert terminal.kind == expected
        assert terminal.watershed_id == hydrology.watershed_id.values[index]


def test_landlocked_world_declares_closed_basins(physical_world):
    terrain, *_ = physical_world
    landlocked = replace(
        terrain, land=IntGrid(terrain.grid, tuple(1 for _ in terrain.grid.indices())),
    )
    hydrology = generate_hydrology(landlocked)
    assert hydrology.terminals
    assert all(terminal.kind == DrainageTerminalKind.CLOSED_BASIN
               for terminal in hydrology.terminals)
    assert {terminal.cell for terminal in hydrology.terminals} == {
        index for index, target in enumerate(hydrology.flow_to.values) if target == -1
    }


def test_river_monotonicity(physical_world):
    """P8.C05C-FIXED: River flow must be monotonic in elevation."""
    terrain, hydrology, *_ = physical_world
    for edge in hydrology.rivers:
        upstream_elev = hydrology.filled_elevation_mm.values[edge.upstream]
        downstream_elev = hydrology.filled_elevation_mm.values[edge.downstream]
        assert downstream_elev <= upstream_elev, \
            f"river {edge.discharge_m3s} flows uphill: {upstream_elev} -> {downstream_elev}"


def test_priority_flood_d8_ties_are_frozen_and_acyclic():
    grid = GridSpec(5, 5, 1_000)
    elevations = (
        0, 0, 0, 0, 0,
        0, 9, 9, 9, 0,
        0, 9, 1, 9, 0,
        0, 9, 9, 9, 0,
        0, 0, 0, 0, 0,
    )
    outlets = tuple(value == 0 for value in elevations)
    filled, parent, rank = priority_flood(grid, elevations, outlets)
    flow = route_d8(grid, elevations, filled, parent, rank, tuple(1 for _ in elevations))
    assert D8_OFFSETS == (
        (0, -1), (1, -1), (1, 0), (1, 1),
        (0, 1), (-1, 1), (-1, 0), (-1, -1),
    )
    assert filled[12] == 9
    for index, target in enumerate(flow):
        if target < 0:
            continue
        assert target in d8_neighbors(grid, index)
        assert filled[target] <= filled[index]
        if filled[target] == filled[index]:
            assert rank[target] < rank[index]
    for start in grid.indices():
        seen: set[int] = set()
        cursor = start
        while flow[cursor] >= 0:
            assert cursor not in seen
            seen.add(cursor)
            cursor = flow[cursor]


def test_connected_lakes_spillways_accumulation_and_deltas(physical_world):
    terrain, hydrology, *_ = physical_world
    depressed = {
        index for index in terrain.grid.indices()
        if terrain.land.values[index]
        and hydrology.filled_elevation_mm.values[index] > terrain.elevation_mm.values[index]
    }
    cells = tuple(cell for lake in hydrology.lakes for cell in lake.cells)
    assert set(cells) == depressed
    assert len(cells) == len(set(cells))
    for lake in hydrology.lakes:
        assert tuple(sorted(lake.cells)) == lake.cells
        assert len({hydrology.filled_elevation_mm.values[cell] for cell in lake.cells}) == 1
        assert lake.spillway_cell in lake.cells
        assert hydrology.flow_to.values[lake.spillway_cell] == lake.outlet
        assert lake.outlet not in lake.cells
    for index, target in enumerate(hydrology.flow_to.values):
        if target >= 0:
            assert hydrology.accumulation.values[target] >= hydrology.accumulation.values[index]
    threshold = max(4, terrain.grid.cell_count // 200)
    assert all(
        value == int(
            bool(hydrology.coastline.values[index]) and hydrology.flow_to.values[index] >= 0
            and not terrain.land.values[hydrology.flow_to.values[index]]
            and hydrology.accumulation.values[index] >= threshold
        )
        for index, value in enumerate(hydrology.delta.values)
    )


def test_equal_surface_depressions_form_one_lake_with_canonical_spillway():
    grid = GridSpec(7, 7, 1_000)
    elevations = tuple(
        0 if (grid.coordinate(index).x in (0, 6) or grid.coordinate(index).y in (0, 6))
        else (1 if index == 24 else (2 if index == 25 else 9))
        for index in grid.indices()
    )
    outlets = tuple(value == 0 for value in elevations)
    filled, parent, rank = priority_flood(grid, elevations, outlets)
    land = tuple(int(value > 0) for value in elevations)
    flow = route_d8(grid, elevations, filled, parent, rank, land)
    lakes = connected_lakes(grid, elevations, filled, flow, land)
    assert len(lakes) == 1
    assert lakes[0].cells == (24, 25)
    assert lakes[0].spillway_cell in lakes[0].cells
    assert lakes[0].outlet not in lakes[0].cells
