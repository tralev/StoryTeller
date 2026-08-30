"""Resource catalog and geological provenance validation for v2 packages."""

from __future__ import annotations

import zipfile
from collections.abc import Mapping
from typing import Any

from .common import JsonLoader, PackageV2Error
from .grids import grid_layer_values


def validate_resource_geology(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    load_json: JsonLoader,
) -> None:
    world = load_json(archive.read("world/index.json"), "world/index.json")
    width = world["width"]
    cell_count = width * world["height"]
    scale = manifest["world"]["metres_per_world_cell"]
    rock = grid_layer_values(archive, "geology", "geology_rock_class_id", load_json)
    strata = grid_layer_values(archive, "geology", "geology_strata_id", load_json)
    fault = grid_layer_values(archive, "geology", "geology_fault", load_json)
    volcano = grid_layer_values(archive, "geology", "geology_volcano", load_json)
    renewable = grid_layer_values(archive, "resource_grid", "resource_renewable_yield", load_json)
    if len(renewable) != cell_count or any(value < 0 for value in renewable):
        raise PackageV2Error("PACKAGE_RESOURCE_CATALOG", "invalid renewable resource yield")

    resources = load_json(archive.read("world/resources.json"), "world/resources.json")
    deposits = resources.get("deposits") if isinstance(resources, dict) else None
    if not isinstance(deposits, list):
        raise PackageV2Error("PACKAGE_RESOURCE_CATALOG", "invalid deposit catalog")
    densities = {
        "iron": 5_000,
        "copper": 3_000,
        "tin": 2_000,
        "coal": 1_500,
        "flux_stone": 4_000,
        "gems": 250,
    }
    deposit_ids: set[str] = set()
    occupied: set[int] = set()
    for deposit in deposits:
        cells = deposit.get("cells") if isinstance(deposit, dict) else None
        deposit_id = deposit.get("deposit_id") if isinstance(deposit, dict) else None
        if (
            not isinstance(deposit_id, str)
            or deposit_id in deposit_ids
            or not isinstance(cells, list)
            or len(cells) < 2
            or cells != sorted(set(cells))
            or any(type(cell) is not int or not 0 <= cell < cell_count for cell in cells)
            or bool(occupied.intersection(cells))
        ):
            raise PackageV2Error("PACKAGE_DEPOSIT_GEOLOGY", "invalid deposit geometry")

        reached = {cells[0]}
        while True:
            expanded = reached | {
                candidate
                for cell in reached
                for candidate in cells
                if abs(cell % width - candidate % width) + abs(cell // width - candidate // width)
                == 1
            }
            if expanded == reached:
                break
            reached = expanded

        fault_related = any(fault[cell] for cell in cells)
        volcanic_related = any(volcano[cell] for cell in cells)
        rock_id = deposit.get("rock_class_id")
        strata_id = deposit.get("strata_id")
        expected_resource = (
            "gems"
            if volcanic_related
            else ("copper" if rock_id % 2 == 0 else "tin")
            if fault_related
            else {1: "coal", 2: "iron", 3: "flux_stone", 4: "copper", 5: "iron"}.get(rock_id)
        )
        grade = deposit.get("grade_ppm")
        expected_quantity = (
            (len(cells) * scale * scale * densities[expected_resource] * grade + 500_000)
            // 1_000_000
            if expected_resource in densities and type(grade) is int
            else -1
        )
        if (
            reached != set(cells)
            or {rock[cell] for cell in cells} != {rock_id}
            or {strata[cell] for cell in cells} != {strata_id}
            or fault_related is not deposit.get("fault_related")
            or volcanic_related is not deposit.get("volcanic_related")
            or deposit.get("resource") != expected_resource
            or deposit.get("quantity_kg") != expected_quantity
        ):
            raise PackageV2Error("PACKAGE_DEPOSIT_GEOLOGY", "deposit provenance differs")
        deposit_ids.add(deposit_id)
        occupied.update(cells)
