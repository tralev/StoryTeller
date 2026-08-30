"""Embedded miniature worldgen conformance kernel from generation.md."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from heapq import heapify, heappop, heappush
from typing import cast

from ..domain.run_spec import derive_seed
from .numeric import PPM, div_floor_exact, div_round_half_up, rng_for_decision

CARDINAL = ((0, -1), (-1, 0), (1, 0), (0, 1))
REFERENCE_SHA256 = "ab52448d56900b6f27855fdd7b48c237b1b80abbea2c66a207d37f9a93df131a"
REFERENCE_SIZE = 130_306
REFERENCE_SITES = (331, 626, 692)
REFERENCE_EVENT_COUNT = 50


@dataclass(frozen=True)
class ReferenceSpec:
    seed: int = 42
    width: int = 40
    height: int = 24
    sea_level_m: int = 0
    years: int = 50


@dataclass(frozen=True)
class ReferenceEvent:
    id: str
    year: int
    kind: str
    causes: tuple[str, ...]
    before: int
    after: int


def _neighbors(index: int, spec: ReferenceSpec) -> tuple[int, ...]:
    x, y = index % spec.width, div_floor_exact(index, spec.width)
    return tuple(
        ny * spec.width + nx
        for dx, dy in CARDINAL
        for nx, ny in ((x + dx, y + dy),)
        if 0 <= nx < spec.width and 0 <= ny < spec.height
    )


def _terrain(spec: ReferenceSpec) -> tuple[int, ...]:
    cx2, cy2 = spec.width - 1, spec.height - 1
    radius2 = min(spec.width, spec.height) - 4
    result: list[int] = []
    for y in range(spec.height):
        for x in range(spec.width):
            dx2, dy2 = 2 * x - cx2, 2 * y - cy2
            radial = radius2 * radius2 - dx2 * dx2 - dy2 * dy2
            texture = (
                derive_seed(
                    spec.seed,
                    "reference.terrain",
                    f"block:{div_floor_exact(x, 3)}:{div_floor_exact(y, 3)}",
                    "texture",
                )
                % 401
                - 200
            )
            detail = (
                derive_seed(
                    spec.seed,
                    "reference.terrain",
                    f"cell:{x}:{y}",
                    "detail",
                )
                % 81
                - 40
            )
            result.append(radial * 3 + texture + detail)
    for x in range(spec.width):
        result[x] = result[(spec.height - 1) * spec.width + x] = -10_000
    for y in range(spec.height):
        result[y * spec.width] = result[y * spec.width + spec.width - 1] = -10_000
    return tuple(result)


def _retain_largest(values: tuple[int, ...], spec: ReferenceSpec) -> tuple[int, ...]:
    land = {i for i, value in enumerate(values) if value > spec.sea_level_m}
    components: list[set[int]] = []
    while land:
        start = min(land)
        stack, component = [start], set()
        land.remove(start)
        while stack:
            current = stack.pop()
            component.add(current)
            for nxt in _neighbors(current, spec):
                if nxt in land:
                    land.remove(nxt)
                    stack.append(nxt)
        components.append(component)
    if not components:
        raise ValueError("no land generated")
    keep = min(components, key=lambda component: (-len(component), min(component)))
    return tuple(
        value if index in keep or value <= spec.sea_level_m else spec.sea_level_m
        for index, value in enumerate(values)
    )


def _priority_flood(
    values: tuple[int, ...],
    spec: ReferenceSpec,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    filled, parent = list(values), [-1] * len(values)
    seen, heap = [False] * len(values), []
    boundary = sorted(
        {
            *range(spec.width),
            *((spec.height - 1) * spec.width + x for x in range(spec.width)),
            *(y * spec.width for y in range(spec.height)),
            *(y * spec.width + spec.width - 1 for y in range(spec.height)),
        }
    )
    for index in boundary:
        seen[index] = True
        heap.append((filled[index], index))
    heapify(heap)
    while heap:
        level, current = heappop(heap)
        for nxt in _neighbors(current, spec):
            if seen[nxt]:
                continue
            seen[nxt], parent[nxt] = True, current
            filled[nxt] = max(values[nxt], level)
            heappush(heap, (filled[nxt], nxt))
    return tuple(filled), tuple(parent)


def _drainage(
    values: tuple[int, ...],
    filled: tuple[int, ...],
    parent: tuple[int, ...],
    spec: ReferenceSpec,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    flow = [-1] * len(values)
    for index in range(len(values)):
        options = sorted((filled[n], n) for n in _neighbors(index, spec))
        if options and options[0][0] < filled[index]:
            flow[index] = options[0][1]
        elif parent[index] >= 0:
            flow[index] = parent[index]
    accumulation = [1] * len(values)
    for index in sorted(range(len(values)), key=lambda item: (filled[item], item), reverse=True):
        if flow[index] >= 0:
            accumulation[flow[index]] += accumulation[index]
    return tuple(flow), tuple(accumulation)


def _climate(
    values: tuple[int, ...],
    accumulation: tuple[int, ...],
    spec: ReferenceSpec,
) -> tuple[dict[str, object], ...]:
    cells: list[dict[str, object]] = []
    for index, elevation in enumerate(values):
        x, y = index % spec.width, div_floor_exact(index, spec.width)
        latitude = div_round_half_up(
            abs(2 * y - (spec.height - 1)) * PPM,
            max(1, spec.height - 1),
        )
        temperature = 28_000 - div_round_half_up(latitude * 38_000, PPM) - max(0, elevation) * 6
        coast = any(values[n] <= spec.sea_level_m for n in _neighbors(index, spec))
        rain = (
            250
            + (500 if coast else 0)
            + derive_seed(
                spec.seed,
                "reference.climate",
                f"cell:{index}",
                "rainfall",
            )
            % 700
        )
        river = accumulation[index] >= 25 and elevation > spec.sea_level_m
        if elevation <= spec.sea_level_m:
            biome = "ocean"
        elif elevation > 900:
            biome = "mountain"
        elif temperature <= -5_000:
            biome = "tundra"
        elif rain < 300:
            biome = "desert"
        elif rain >= 900:
            biome = "forest"
        else:
            biome = "grassland"
        cells.append(
            {
                "i": index,
                "x": x,
                "y": y,
                "elevation_m": elevation,
                "temperature_mc": temperature,
                "rain_mm": rain,
                "river": river,
                "biome": biome,
            }
        )
    return tuple(cells)


def _settlements(cells: tuple[dict[str, object], ...], spec: ReferenceSpec) -> tuple[int, ...]:
    candidates: list[tuple[int, int]] = []
    for cell in cells:
        if cell["biome"] in ("ocean", "mountain", "tundra"):
            continue
        score = cast(int, cell["rain_mm"]) + (800 if cell["river"] else 0)
        score -= div_round_half_up(
            abs(cast(int, cell["temperature_mc"]) - 15_000),
            20,
        )
        candidates.append((-score, cast(int, cell["i"])))
    selected: list[int] = []
    for _, index in sorted(candidates):
        x, y = index % spec.width, div_floor_exact(index, spec.width)
        if all(
            abs(x - item % spec.width) + abs(y - div_floor_exact(item, spec.width)) >= 8
            for item in selected
        ):
            selected.append(index)
        if len(selected) == 3:
            break
    if not selected:
        raise ValueError("no suitable settlement")
    return tuple(sorted(selected))


def _history(sites: tuple[int, ...], spec: ReferenceSpec) -> tuple[ReferenceEvent, ...]:
    population, previous = 100 * len(sites), ""
    events: list[ReferenceEvent] = []
    for year in range(spec.years):
        rng = rng_for_decision(
            spec.seed,
            "reference.history",
            f"year:{year}",
            "demography",
        )
        capacity = 450 * len(sites)
        births = div_round_half_up(population * 35, 1_000)
        deaths = div_round_half_up(population * (18 + rng.below(8)), 1_000)
        growth = min(births - deaths, max(0, capacity - population))
        before, population = population, max(0, population + growth)
        event_id = f"event_{hashlib.sha256(f'{spec.seed}:{year}'.encode()).hexdigest()[:32]}"
        events.append(
            ReferenceEvent(
                event_id,
                year,
                "population_change",
                (previous,) if previous else (),
                before,
                population,
            )
        )
        previous = event_id
    return tuple(events)


def generate_reference(spec: ReferenceSpec = ReferenceSpec()) -> dict[str, object]:
    elevation = _retain_largest(_terrain(spec), spec)
    filled, parent = _priority_flood(elevation, spec)
    flow, accumulation = _drainage(elevation, filled, parent, spec)
    cells = _climate(elevation, accumulation, spec)
    sites = _settlements(cells, spec)
    events = _history(sites, spec)
    return {
        "spec": spec,
        "elevation_m": elevation,
        "filled_m": filled,
        "flow": flow,
        "accumulation": accumulation,
        "cells": cells,
        "site_indices": sites,
        "events": events,
    }


def reference_bytes(spec: ReferenceSpec = ReferenceSpec()) -> bytes:
    def convert(value: object) -> object:
        if is_dataclass(value) and not isinstance(value, type):
            return convert(asdict(value))
        if isinstance(value, dict):
            return {key: convert(item) for key, item in sorted(value.items())}
        if isinstance(value, (tuple, list)):
            return [convert(item) for item in value]
        return value

    return json.dumps(
        convert(generate_reference(spec)),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def verify_reference() -> dict[str, object]:
    world = generate_reference()
    encoded = reference_bytes()
    result = {
        "byte_length": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "site_indices": world["site_indices"],
        "event_count": len(world["events"]),  # type: ignore[arg-type]
    }
    expected = {
        "byte_length": REFERENCE_SIZE,
        "sha256": REFERENCE_SHA256,
        "site_indices": REFERENCE_SITES,
        "event_count": REFERENCE_EVENT_COUNT,
    }
    if result != expected:
        raise RuntimeError(f"worldgen reference mismatch: {result!r}")
    return result
