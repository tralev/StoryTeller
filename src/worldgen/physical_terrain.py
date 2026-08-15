"""Deterministic fixed-point tectonics, textured continents, and erosion."""
from __future__ import annotations

from collections import deque

from .grid import GridSpec, IntGrid
from .numeric import (PPM, div_floor_exact, div_round_half_up, fractal_noise_ppm,
                      rng_for_decision)
from .physical_models import ErosionPassLedger, Plate, PlateBoundaryClass, Terrain

ALGORITHM_VERSION = 1
MIN_ELEVATION_MM = -100_000
MAX_ELEVATION_MM = 100_000
LAND_FRACTION_TOLERANCE_PPM = 25_000


def _spaced_centers(grid: GridSpec, count: int, seed: int) -> tuple[int, ...]:
    rng = rng_for_decision(seed, "physical.plates", "world", "first_center")
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


def _spaced_interior_centers(grid: GridSpec, count: int, seed: int) -> tuple[int, ...]:
    candidates = tuple(index for index in grid.indices()
                       if 0 < grid.coordinate(index).x < grid.width - 1
                       and 0 < grid.coordinate(index).y < grid.height - 1)
    if count > len(candidates):
        raise ValueError("WG-CONTINENTS: more continents than interior cells")
    rng = rng_for_decision(seed, "physical.continents", "world", "first_center")
    selected = [candidates[rng.below(len(candidates))]]
    while len(selected) < count:
        def score(index: int) -> tuple[int, int]:
            point = grid.coordinate(index)
            distance = min(
                (point.x - grid.coordinate(other).x) ** 2
                + (point.y - grid.coordinate(other).y) ** 2
                for other in selected
            )
            return distance, -index
        selected.append(max(candidates, key=score))
    return tuple(selected)


def _retain_seeded_components(
    grid: GridSpec, labels: list[int], centers: tuple[int, ...],
) -> list[int]:
    """Keep exactly the connected component containing each continent seed."""
    retained = [0] * grid.cell_count
    for number, center in enumerate(centers, 1):
        if labels[center] != number:
            raise AssertionError("continent centre must belong to its own landmass")
        queue = deque([center])
        retained[center] = number
        while queue:
            index = queue.popleft()
            for neighbor in grid.neighbors4(index):
                if labels[neighbor] == number and retained[neighbor] == 0:
                    retained[neighbor] = number
                    queue.append(neighbor)
    return retained


def _erode(
    grid: GridSpec, elevation: tuple[int, ...], passes: int,
) -> tuple[tuple[int, ...], tuple[ErosionPassLedger, ...]]:
    values = list(elevation)
    ledger: list[ErosionPassLedger] = []
    for pass_index in range(passes):
        mass_before = sum(values)
        thermal_delta = [0] * grid.cell_count
        hydraulic_delta = [0] * grid.cell_count
        thermal_moved = 0
        hydraulic_moved = 0
        for index in grid.indices():
            lower = [n for n in grid.neighbors4(index) if values[n] < values[index]]
            if not lower:
                continue
            target = min(lower, key=lambda n: (values[n], n))
            difference = values[index] - values[target]
            thermal_transfer = min(
                16, max(0, div_round_half_up(difference, 32)),
            )
            hydraulic_transfer = min(
                8, max(0, div_round_half_up(difference, 64)),
            )
            thermal_delta[index] -= thermal_transfer
            thermal_delta[target] += thermal_transfer
            hydraulic_delta[index] -= hydraulic_transfer
            hydraulic_delta[target] += hydraulic_transfer
            thermal_moved += thermal_transfer
            hydraulic_moved += hydraulic_transfer
        if sum(thermal_delta) != 0 or sum(hydraulic_delta) != 0:
            raise AssertionError("erosion must conserve elevation mass")
        values = [value + thermal_delta[index] + hydraulic_delta[index]
                  for index, value in enumerate(values)]
        mass_after = sum(values)
        if mass_after != mass_before:
            raise AssertionError("erosion mass ledger mismatch")
        ledger.append(ErosionPassLedger(
            pass_index, mass_before, thermal_moved, hydraulic_moved, mass_after,
        ))
    return tuple(values), tuple(ledger)


def classify_plate_boundary(grid: GridSpec, left: Plate, right: Plate) -> PlateBoundaryClass:
    """Classify relative motion projected onto the centre-to-centre normal."""
    left_center = grid.coordinate(left.center)
    right_center = grid.coordinate(right.center)
    normal_x = right_center.x - left_center.x
    normal_y = right_center.y - left_center.y
    relative_x = right.motion_x_ppm - left.motion_x_ppm
    relative_y = right.motion_y_ppm - left.motion_y_ppm
    separation_rate = relative_x * normal_x + relative_y * normal_y
    transform_band = max(1, abs(normal_x) + abs(normal_y)) * 100_000
    if separation_rate < -transform_band:
        return PlateBoundaryClass.CONVERGENT
    if separation_rate > transform_band:
        return PlateBoundaryClass.DIVERGENT
    return PlateBoundaryClass.TRANSFORM


def generate_physical_terrain(
    grid: GridSpec, seed: int, *, continent_count: int, plate_count: int,
    erosion_passes: int, minimum_continent_cells: int = 1,
    sea_level_ppm: int = 380_000,
) -> Terrain:
    if continent_count < 1 or plate_count < continent_count:
        raise ValueError("WG-CONTINENTS: invalid continent/plate count")
    if plate_count > grid.cell_count:
        raise ValueError("WG-PLATES: more plates than cells")
    if not 50_000 <= sea_level_ppm <= 950_000:
        raise ValueError("WG-LAND-FRACTION: sea level must be within 50,000..950,000 ppm")
    plate_centers = _spaced_centers(grid, plate_count, seed)
    continent_centers = _spaced_interior_centers(grid, continent_count, seed ^ 0xC071E17)
    plates = tuple(
        Plate(
            f"plate_{i + 1:03d}", center,
            rng_for_decision(
                seed, "physical.plate.motion", f"center:{center}", "motion_x",
            ).below(2_000_001) - 1_000_000,
            rng_for_decision(
                seed, "physical.plate.motion", f"center:{center}", "motion_y",
            ).below(2_000_001) - 1_000_000,
        )
        for i, center in enumerate(plate_centers)
    )
    plate_owner: list[int] = []
    continent_owner: list[int] = []
    radial_values: list[int] = []
    texture_values: list[int] = []
    radius_x = max(3, div_floor_exact(grid.width, max(2, continent_count + 1)))
    radius_y = max(3, div_floor_exact(grid.height, 3))
    for index in grid.indices():
        p = grid.coordinate(index)
        owner = min(range(plate_count), key=lambda i: (
            (p.x - grid.coordinate(plate_centers[i]).x) ** 2
            + (p.y - grid.coordinate(plate_centers[i]).y) ** 2, i))
        plate_owner.append(owner + 1)
        nearest = min(range(continent_count), key=lambda i: (
            div_round_half_up(
                (p.x - grid.coordinate(continent_centers[i]).x) * 1_000,
                radius_x,
            ) ** 2
            + div_round_half_up(
                (p.y - grid.coordinate(continent_centers[i]).y) * 1_000,
                radius_y,
            ) ** 2,
            i,
        ))
        center = grid.coordinate(continent_centers[nearest])
        radial = (
            div_round_half_up((p.x - center.x) * 1_000, radius_x) ** 2
            + div_round_half_up((p.y - center.y) * 1_000, radius_y) ** 2
        )
        texture = fractal_noise_ppm(p.x, p.y, seed ^ 0x7E227A1, octaves=4)
        textured_radial = radial + div_round_half_up(texture * 240_000, PPM)
        # Border ocean gives hydrology an outlet; seeded-component retention
        # prevents texture-created satellite islands from changing continent count.
        border = p.x == 0 or p.y == 0 or p.x == grid.width - 1 or p.y == grid.height - 1
        continent_owner.append(nearest + 1 if not border else 0)
        radial_values.append(radial)
        texture_values.append(textured_radial)
    target_land = div_round_half_up(grid.cell_count * (PPM - sea_level_ppm), PPM)
    maximum_land = (grid.width - 2) * (grid.height - 2)
    if target_land > maximum_land:
        raise ValueError("WG-LAND-FRACTION: requested ocean fraction conflicts with border ocean")
    low, high = min(texture_values), max(texture_values)
    best: tuple[int, list[int]] | None = None
    while low <= high:
        threshold = div_floor_exact(low + high, 2)
        candidates = [owner if owner and (index in continent_centers
                                          or texture_values[index] <= threshold) else 0
                      for index, owner in enumerate(continent_owner)]
        retained = _retain_seeded_components(grid, candidates, continent_centers)
        difference = abs(sum(value != 0 for value in retained) - target_land)
        if best is None or difference < best[0]:
            best = difference, retained
        actual = sum(value != 0 for value in retained)
        if actual < target_land:
            low = threshold + 1
        else:
            high = threshold - 1
    if best is None:
        raise AssertionError("land-fraction search produced no candidate")
    continent = best[1]
    actual_land_ppm = div_round_half_up(sum(value != 0 for value in continent) * PPM,
                                        grid.cell_count)
    requested_land_ppm = PPM - sea_level_ppm
    if abs(actual_land_ppm - requested_land_ppm) > LAND_FRACTION_TOLERANCE_PPM:
        raise ValueError("WG-LAND-FRACTION: requested fraction cannot be represented by this grid")
    elevation: list[int] = []
    for index in grid.indices():
        radial = radial_values[index]
        is_land = continent[index] != 0
        relief = div_round_half_up(max(0, 900_000 - radial), 90)
        jitter = rng_for_decision(
            seed, "physical.terrain", f"cell:{index}", "elevation_jitter",
        ).below(801) - 400
        texture_relief = div_round_half_up(
            (texture_values[index] - radial_values[index]) * 600, PPM,
        )
        ocean_depth = min(4_000, div_round_half_up(radial, 500))
        elevation.append((500 + relief + texture_relief + jitter)
                         if is_land else (-2_000 - ocean_depth + texture_relief))
    counts = {number: continent.count(number) for number in range(1, continent_count + 1)}
    too_small = {number: count for number, count in counts.items() if count < minimum_continent_cells}
    if too_small:
        raise ValueError(f"WG-CONTINENT-AREA: continents below minimum area: {too_small}")
    boundaries: list[int] = []
    for index in grid.indices():
        others = sorted({plate_owner[n] for n in grid.neighbors4(index) if plate_owner[n] != plate_owner[index]})
        if not others:
            boundaries.append(PlateBoundaryClass.INTERIOR)
            continue
        left = plates[plate_owner[index] - 1]
        right = plates[others[0] - 1]
        boundary = classify_plate_boundary(grid, left, right)
        boundaries.append(boundary)
        if continent[index]:
            elevation[index] += (
                1_000 if boundary is PlateBoundaryClass.CONVERGENT
                else -300 if boundary is PlateBoundaryClass.DIVERGENT else 200
            )
    eroded, ledger = _erode(grid, tuple(elevation), erosion_passes)
    if any(not MIN_ELEVATION_MM <= value <= MAX_ELEVATION_MM for value in eroded):
        raise ValueError("WG-ELEVATION-BOUNDS: generated elevation is out of range")
    land = tuple(1 if cid else 0 for cid in continent)
    slopes = tuple(max((abs(eroded[i] - eroded[n]) for n in grid.neighbors4(i)), default=0)
                   for i in grid.indices())
    return Terrain(ALGORITHM_VERSION, grid, plates, IntGrid(grid, tuple(plate_owner)),
                   IntGrid(grid, tuple(boundaries)),
                   IntGrid(grid, eroded), IntGrid(grid, slopes), IntGrid(grid, land),
                   IntGrid(grid, tuple(continent)), ledger)
