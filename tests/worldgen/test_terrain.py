import ast
import hashlib
from pathlib import Path

import pytest

from src.worldgen.artifacts import canonical_json
from src.worldgen.grid import GridSpec
from src.worldgen.physical_models import Plate, PlateBoundaryClass
from src.worldgen.physical_terrain import (
    LAND_FRACTION_TOLERANCE_PPM,
    MAX_ELEVATION_MM,
    MIN_ELEVATION_MM,
    _spaced_centers,
    classify_plate_boundary,
    generate_physical_terrain,
)


def test_terrain_has_no_raw_division_operators():
    source = Path("src/worldgen/physical_terrain.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [node for node in ast.walk(tree) if isinstance(node, (ast.FloorDiv, ast.Div))]


def test_exact_continent_count_and_mass_conserving_erosion():
    grid = GridSpec(40, 32, 8000)
    before = generate_physical_terrain(grid, 7, continent_count=2, plate_count=5, erosion_passes=0)
    after = generate_physical_terrain(grid, 7, continent_count=2, plate_count=5, erosion_passes=4)
    assert set(after.continent_id.values) - {0} == {1, 2}
    assert sum(before.elevation_mm.values) == sum(after.elevation_mm.values)
    assert tuple(entry.pass_index for entry in after.erosion_ledger) == (0, 1, 2, 3)
    assert all(entry.mass_before_mm == entry.mass_after_mm for entry in after.erosion_ledger)
    assert all(
        entry.thermal_moved_mm <= grid.cell_count * 16
        and entry.hydraulic_moved_mm <= grid.cell_count * 8
        for entry in after.erosion_ledger
    )
    assert any(entry.thermal_moved_mm > 0 for entry in after.erosion_ledger)
    assert any(entry.hydraulic_moved_mm > 0 for entry in after.erosion_ledger)
    assert all(
        left.mass_after_mm == right.mass_before_mm
        for left, right in zip(after.erosion_ledger, after.erosion_ledger[1:])
    )


@pytest.mark.parametrize("continent_count", [1, 2, 3])
def test_textured_continents_are_exact_connected_and_keep_border_ocean(continent_count):
    grid = GridSpec(48, 36, 8000)
    terrain = generate_physical_terrain(
        grid,
        73,
        continent_count=continent_count,
        plate_count=max(5, continent_count),
        erosion_passes=1,
        minimum_continent_cells=4,
    )
    assert set(terrain.continent_id.values) == set(range(continent_count + 1))
    assert all(
        terrain.continent_id.values[grid.index(x, y)] == 0
        for y in range(grid.height)
        for x in range(grid.width)
        if x in (0, grid.width - 1) or y in (0, grid.height - 1)
    )
    for number in range(1, continent_count + 1):
        cells = {
            index for index, value in enumerate(terrain.continent_id.values) if value == number
        }
        reached = {min(cells)}
        frontier = [min(cells)]
        while frontier:
            index = frontier.pop()
            for neighbor in grid.neighbors4(index):
                if neighbor in cells and neighbor not in reached:
                    reached.add(neighbor)
                    frontier.append(neighbor)
        assert reached == cells

    source = Path("src/worldgen/physical_terrain.py").read_text(encoding="utf-8")
    assert "fractal_noise_ppm" in source and "octaves=4" in source


def test_terrain_is_byte_deterministic():
    args = (GridSpec(32, 32, 8000), 42)
    a = generate_physical_terrain(*args, continent_count=1, plate_count=4, erosion_passes=2)
    b = generate_physical_terrain(*args, continent_count=1, plate_count=4, erosion_passes=2)
    assert a.elevation_mm.encode("elevation") == b.elevation_mm.encode("elevation")
    assert (
        hashlib.sha256(canonical_json(a)).hexdigest()
        == "1efef7c4f8b4a27364e73f9d94d0b0e1c8dd3b16564933a0de084303c377dc53"
    )


def test_plate_boundaries_are_versioned_classes():
    terrain = generate_physical_terrain(
        GridSpec(32, 32, 8000), 9, continent_count=1, plate_count=5, erosion_passes=1
    )
    assert set(terrain.plate_boundary.values) <= {0, 1, 2, 3}
    assert any(terrain.plate_boundary.values)


def test_plate_centres_voronoi_motion_and_boundary_contract():
    grid = GridSpec(32, 24, 8000)
    centers = _spaced_centers(grid, 7, 91)
    assert len(centers) == len(set(centers)) == 7
    for position, center in enumerate(centers[1:], 1):
        prior = centers[:position]

        def minimum_distance(index):
            point = grid.coordinate(index)
            return min(
                (point.x - grid.coordinate(other).x) ** 2
                + (point.y - grid.coordinate(other).y) ** 2
                for other in prior
            )

        assert minimum_distance(center) == max(minimum_distance(index) for index in grid.indices())

    terrain = generate_physical_terrain(
        grid,
        91,
        continent_count=1,
        plate_count=7,
        erosion_passes=1,
    )
    for index in grid.indices():
        point = grid.coordinate(index)
        expected = (
            min(
                range(len(centers)),
                key=lambda plate_index: (
                    (point.x - grid.coordinate(centers[plate_index]).x) ** 2
                    + (point.y - grid.coordinate(centers[plate_index]).y) ** 2,
                    plate_index,
                ),
            )
            + 1
        )
        assert terrain.plate_id.values[index] == expected
    assert all(
        -1_000_000 <= component <= 1_000_000
        for plate in terrain.plates
        for component in (plate.motion_x_ppm, plate.motion_y_ppm)
    )

    left_center, right_center = grid.index(8, 12), grid.index(24, 12)
    assert (
        classify_plate_boundary(
            grid,
            Plate("left", left_center, 500_000, 0),
            Plate("right", right_center, -500_000, 0),
        )
        is PlateBoundaryClass.CONVERGENT
    )
    assert (
        classify_plate_boundary(
            grid,
            Plate("left", left_center, -500_000, 0),
            Plate("right", right_center, 500_000, 0),
        )
        is PlateBoundaryClass.DIVERGENT
    )
    assert (
        classify_plate_boundary(
            grid,
            Plate("left", left_center, 0, -500_000),
            Plate("right", right_center, 0, 500_000),
        )
        is PlateBoundaryClass.TRANSFORM
    )


def test_seed_divergence_produces_different_terrain():
    """P8.C05C: Same-seed bytes equal; different-seed bytes diverge."""
    grid = GridSpec(32, 32, 8000)
    a = generate_physical_terrain(grid, 42, continent_count=1, plate_count=4, erosion_passes=2)
    b = generate_physical_terrain(grid, 99, continent_count=1, plate_count=4, erosion_passes=2)
    assert a.elevation_mm.values != b.elevation_mm.values
    assert a.plate_id.values != b.plate_id.values


def test_pathological_four_by_four_grid():
    """P8.C05C: Tiny grids with edge cells only (all ocean boundary)."""
    grid = GridSpec(4, 4, 8000)
    terrain = generate_physical_terrain(
        grid,
        1,
        continent_count=1,
        plate_count=2,
        erosion_passes=1,
        sea_level_ppm=750_000,
    )
    # All boundary cells are forced ocean, so interior cells might be land
    assert len(terrain.elevation_mm.values) == 16
    assert len(terrain.land.values) == 16
    # All cells classified
    assert all(terrain.land.values[i] in (0, 1) for i in range(16))


def test_elevation_bounds(physical_world):
    """P8.C05C-FIXED: Elevation stays within signed 32-bit range."""
    terrain = physical_world[0]
    for e in terrain.elevation_mm.values:
        assert MIN_ELEVATION_MM <= e <= MAX_ELEVATION_MM, f"elevation out of range: {e}"


@pytest.mark.parametrize("sea_level_ppm", [250_000, 380_000, 650_000])
def test_requested_land_fraction_is_satisfied(sea_level_ppm):
    grid = GridSpec(64, 48, 8_000)
    terrain = generate_physical_terrain(
        grid,
        83,
        continent_count=2,
        plate_count=6,
        erosion_passes=2,
        minimum_continent_cells=4,
        sea_level_ppm=sea_level_ppm,
    )
    actual_land_ppm = round(sum(terrain.land.values) * 1_000_000 / grid.cell_count)
    assert abs(actual_land_ppm - (1_000_000 - sea_level_ppm)) <= LAND_FRACTION_TOLERANCE_PPM
    assert set(terrain.continent_id.values) - {0} == {1, 2}


def test_unrepresentable_land_fraction_is_rejected_on_pathological_grid():
    with pytest.raises(ValueError, match="WG-LAND-FRACTION"):
        generate_physical_terrain(
            GridSpec(4, 4, 8_000),
            1,
            continent_count=1,
            plate_count=2,
            erosion_passes=0,
            sea_level_ppm=50_000,
        )
