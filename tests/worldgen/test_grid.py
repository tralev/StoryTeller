import hashlib

import pytest

from src.worldgen.artifacts import GridChunk, canonical_json
from src.worldgen.grid import (
    GridSpec,
    IntGrid,
    build_grid_manifest,
    iter_grid_chunks,
    reconstruct_grid,
)


def test_grid_bounds_and_canonical_round_trip():
    spec = GridSpec(3, 2, 1000)
    grid = IntGrid(spec, (1, 2, 3, 4, 5, 6))
    assert grid.at(2, 1) == 6
    assert IntGrid(spec, tuple(grid.values)).encode("sample") == grid.encode("sample")
    with pytest.raises(IndexError):
        spec.index(3, 0)


def test_dense_grid_manifest_has_frozen_canonical_vector():
    grid = IntGrid(GridSpec(3, 2, 1000), (1, 2, 3, 4, 5, 6))
    manifest = build_grid_manifest("sample", grid, chunk_width=2, chunk_height=2)
    assert hashlib.sha256(canonical_json(manifest)).hexdigest() == (
        "c00fac2235d8af69a6e793009a16d7da0ad3efc5a94281cad7e31d46ef64e6a5"
    )
    assert (
        reconstruct_grid(
            manifest,
            reversed(
                tuple(
                    iter_grid_chunks(
                        "sample",
                        grid,
                        chunk_width=2,
                        chunk_height=2,
                    )
                )
            ),
        )
        == grid
    )


def test_dense_grid_partial_edges_and_chunk_memory_bound():
    spec = GridSpec(300, 270, 8000)
    grid = IntGrid(spec, tuple(range(spec.cell_count)))
    chunks = tuple(iter_grid_chunks("elevation", grid))
    manifest = build_grid_manifest("elevation", grid)
    assert [(item.chunk_x, item.chunk_y, item.width, item.height) for item in manifest.chunks] == [
        (0, 0, 256, 256),
        (1, 0, 44, 256),
        (0, 1, 256, 14),
        (1, 1, 44, 14),
    ]
    assert max(len(chunk.values) for chunk in chunks) == 256 * 256
    assert reconstruct_grid(manifest, reversed(chunks)) == grid


def test_dense_grid_reconstruction_rejects_missing_duplicate_and_corrupt_chunks():
    grid = IntGrid(GridSpec(3, 2, 1000), (1, 2, 3, 4, 5, 6))
    chunks = tuple(iter_grid_chunks("sample", grid, chunk_width=2, chunk_height=2))
    manifest = build_grid_manifest("sample", grid, chunk_width=2, chunk_height=2)
    with pytest.raises(ValueError, match="incomplete"):
        reconstruct_grid(manifest, chunks[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        reconstruct_grid(manifest, chunks + (chunks[0],))
    corrupt = GridChunk(
        chunks[0].layer,
        chunks[0].chunk_x,
        chunks[0].chunk_y,
        chunks[0].width,
        chunks[0].height,
        (99,) + chunks[0].values[1:],
    )
    with pytest.raises(ValueError, match="corrupt"):
        reconstruct_grid(manifest, (corrupt,) + chunks[1:])
