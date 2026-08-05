from src.worldgen.grid import GridSpec
from src.worldgen.physical_terrain import generate_physical_terrain


def test_exact_continent_count_and_mass_conserving_erosion():
    grid = GridSpec(40, 32, 8000)
    before = generate_physical_terrain(grid, 7, continent_count=2, plate_count=5, erosion_passes=0)
    after = generate_physical_terrain(grid, 7, continent_count=2, plate_count=5, erosion_passes=4)
    assert set(after.continent_id.values) - {0} == {1, 2}
    assert sum(before.elevation_mm.values) == sum(after.elevation_mm.values)
    assert after.adjustment_ledger_mm == (0, 0, 0, 0)


def test_terrain_is_byte_deterministic():
    args = (GridSpec(32, 32, 8000), 42)
    a = generate_physical_terrain(*args, continent_count=1, plate_count=4, erosion_passes=2)
    b = generate_physical_terrain(*args, continent_count=1, plate_count=4, erosion_passes=2)
    assert a.elevation_mm.encode("elevation") == b.elevation_mm.encode("elevation")
    assert hashlib.sha256(canonical_json(a)).hexdigest() == \
        "1179155c3d72a1eb06bbb60bffda01eab018163a45c79461b08cf08670b1c0f1"


def test_plate_boundaries_are_versioned_classes():
    terrain = generate_physical_terrain(GridSpec(32, 32, 8000), 9,
                                        continent_count=1, plate_count=5, erosion_passes=1)
    assert set(terrain.plate_boundary.values) <= {0, 1, 2, 3}
    assert any(terrain.plate_boundary.values)
import hashlib

from src.worldgen.artifacts import canonical_json
