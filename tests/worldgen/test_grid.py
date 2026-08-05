import pytest

from src.worldgen.grid import GridSpec, IntGrid


def test_grid_bounds_and_canonical_round_trip():
    spec = GridSpec(3, 2, 1000)
    grid = IntGrid(spec, (1, 2, 3, 4, 5, 6))
    assert grid.at(2, 1) == 6
    assert IntGrid(spec, tuple(grid.values)).encode("sample") == grid.encode("sample")
    with pytest.raises(IndexError):
        spec.index(3, 0)
