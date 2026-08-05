"""Deterministic fixed-point tectonics, continents, and erosion."""
from __future__ import annotations

from .grid import GridSpec, IntGrid
from .numeric import SplitMix64, rng_for
from .physical_models import Plate, Terrain

ALGORITHM_VERSION = 1


def _spaced_centers(grid: GridSpec, count: int, seed: int) -> tuple[int, ...]:
    rng = rng_for(seed, "physical.plates")
    candidates = list(grid.indices())
    # Deterministic farthest-point sampling, with a seeded first point.
    first = candidates[rng.below(len(candidates))]
    selected = [first]
    while len(selected) < count:
        def score(index: int) -> tuple[int, int]:
            p = grid.coordinate(index)
            distance = min(
                (p.x - grid.coordinate(other).x) ** 2
                + (p.y - grid.coordinate(other).y) ** 2
                for other in selected
            )
            return distance, -index
        selected.append(max(candidates, key=score))
    return tuple(selected)


def _erode(grid: GridSpec, elevation: tuple[int, ...], passes: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    values = list(elevation)
    ledger: list[int] = []
    for _ in range(passes):
        delta = [0] * grid.cell_count
        for index in grid.indices():
            lower = [n for n in grid.neighbors4(index) if values[n] < values[index]]
            if not lower:
                continue
            target = min(lower, key=lambda n: (values[n], n))
            transfer = min(25, max(0, (values[index] - values[target]) // 16))
            delta[index] -= transfer
            delta[target] += transfer
        if sum(delta) != 0:
            raise AssertionError("erosion must conserve elevation mass")
        values = [value + delta[index] for index, value in enumerate(values)]
        ledger.append(sum(delta))
    return tuple(values), tuple(ledger)


def generate_physical_terrain(
    grid: GridSpec, seed: int, *, continent_count: int, plate_count: int,
    erosion_passes: int, minimum_continent_cells: int = 1,
) -> Terrain:
    if continent_count < 1 or plate_count < continent_count:
        raise ValueError("WG-CONTINENTS: invalid continent/plate count")
    if plate_count > grid.cell_count:
        raise ValueError("WG-PLATES: more plates than cells")
    plate_centers = _spaced_centers(grid, plate_count, seed)
    continent_centers = _spaced_centers(grid, continent_count, seed ^ 0xC071E17)
    motion_rng = rng_for(seed, "physical.plate.motion")
    plates = tuple(
        Plate(f"plate_{i + 1:03d}", center, motion_rng.below(2_000_001) - 1_000_000,
              motion_rng.below(2_000_001) - 1_000_000)
        for i, center in enumerate(plate_centers)
    )
    plate_owner: list[int] = []
    continent: list[int] = []
    elevation: list[int] = []
    radius_x = max(3, grid.width // max(2, continent_count + 1))
    radius_y = max(3, grid.height // 3)
    noise = SplitMix64(seed & ((1 << 64) - 1))
    for index in grid.indices():
        p = grid.coordinate(index)
        owner = min(range(plate_count), key=lambda i: (
            (p.x - grid.coordinate(plate_centers[i]).x) ** 2
            + (p.y - grid.coordinate(plate_centers[i]).y) ** 2, i))
        plate_owner.append(owner + 1)
        nearest = min(range(continent_count), key=lambda i: (
            ((p.x - grid.coordinate(continent_centers[i]).x) * 1_000 // radius_x) ** 2
            + ((p.y - grid.coordinate(continent_centers[i]).y) * 1_000 // radius_y) ** 2, i))
        center = grid.coordinate(continent_centers[nearest])
        radial = ((p.x - center.x) * 1_000 // radius_x) ** 2 + ((p.y - center.y) * 1_000 // radius_y) ** 2
        # Border ocean keeps continents separated and gives hydrology an outlet.
        border = p.x == 0 or p.y == 0 or p.x == grid.width - 1 or p.y == grid.height - 1
        is_land = radial <= 850_000 and not border
        continent.append(nearest + 1 if is_land else 0)
        relief = max(0, 900_000 - radial) // 90
        jitter = noise.below(801) - 400
        elevation.append((500 + relief + jitter) if is_land else (-2_000 - min(4_000, radial // 500)))
    counts = {number: continent.count(number) for number in range(1, continent_count + 1)}
    too_small = {number: count for number, count in counts.items() if count < minimum_continent_cells}
    if too_small:
        raise ValueError(f"WG-CONTINENT-AREA: continents below minimum area: {too_small}")
    boundaries: list[int] = []
    for index in grid.indices():
        others = sorted({plate_owner[n] for n in grid.neighbors4(index) if plate_owner[n] != plate_owner[index]})
        if not others:
            boundaries.append(0)
            continue
        left = plates[plate_owner[index] - 1]
        right = plates[others[0] - 1]
        dot = left.motion_x_ppm * right.motion_x_ppm + left.motion_y_ppm * right.motion_y_ppm
        boundary = 1 if dot < -100_000_000_000 else 2 if dot > 100_000_000_000 else 3
        boundaries.append(boundary)
        if continent[index]:
            elevation[index] += 1_000 if boundary == 1 else -300 if boundary == 2 else 200
    eroded, ledger = _erode(grid, tuple(elevation), erosion_passes)
    land = tuple(1 if cid else 0 for cid in continent)
    slopes = tuple(max((abs(eroded[i] - eroded[n]) for n in grid.neighbors4(i)), default=0)
                   for i in grid.indices())
    return Terrain(ALGORITHM_VERSION, grid, plates, IntGrid(grid, tuple(plate_owner)),
                   IntGrid(grid, tuple(boundaries)),
                   IntGrid(grid, eroded), IntGrid(grid, slopes), IntGrid(grid, land),
                   IntGrid(grid, tuple(continent)), ledger)
