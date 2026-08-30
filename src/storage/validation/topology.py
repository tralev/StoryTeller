"""Region, site, and route topology validation for v2 packages."""

from __future__ import annotations

import zipfile
from collections.abc import Mapping
from typing import Any

from .common import JsonLoader, PackageV2Error
from .grids import grid_layer_values


def validate_region_site_topology(archive: zipfile.ZipFile, load_json: JsonLoader) -> None:
    world = load_json(archive.read("world/index.json"), "world/index.json")
    width, height = world.get("width"), world.get("height")
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise PackageV2Error("PACKAGE_REGION_PARTITION", "invalid world dimensions")

    document = load_json(archive.read("world/regions.json"), "world/regions.json")
    regions = document.get("regions")
    if not isinstance(regions, list) or not regions:
        raise PackageV2Error("PACKAGE_REGION_PARTITION", "regions must be non-empty")
    owners: dict[str, set[int]] = {}
    all_cells: list[int] = []
    for region in regions:
        region_id = region.get("region_id") if isinstance(region, dict) else None
        cells = region.get("cells") if isinstance(region, dict) else None
        if (
            not isinstance(region_id, str)
            or region_id in owners
            or not isinstance(cells, list)
            or not cells
            or any(type(cell) is not int for cell in cells)
            or len(cells) != len(set(cells))
        ):
            raise PackageV2Error("PACKAGE_REGION_PARTITION", "invalid region record")
        owners[region_id] = set(cells)
        all_cells.extend(cells)

    terrain_path = "world/terrain/index.json"
    terrain_index = load_json(archive.read(terrain_path), terrain_path)
    if "terrain_land" in terrain_index.get("layers", {}):
        land_cells = {
            index
            for index, is_land in enumerate(
                grid_layer_values(archive, "terrain", "terrain_land", load_json)
            )
            if is_land == 1
        }
    else:
        # Minimal conformance fixtures model an all-land world and intentionally
        # omit the optional physical land mask.
        land_cells = set(range(width * height))
    if set(all_cells) != land_cells or len(all_cells) != len(land_cells):
        raise PackageV2Error("PACKAGE_REGION_PARTITION", "regions must partition every land cell")

    neighbor_map = {region["region_id"]: region.get("neighbors") for region in regions}
    for region_id, neighbors in neighbor_map.items():
        if (
            not isinstance(neighbors, list)
            or region_id in neighbors
            or len(neighbors) != len(set(neighbors))
            or any(neighbor not in owners for neighbor in neighbors)
            or any(region_id not in neighbor_map[neighbor] for neighbor in neighbors)
        ):
            raise PackageV2Error("PACKAGE_REGION_PARTITION", "invalid region adjacency")

    sites_doc = load_json(archive.read("world/sites.json"), "world/sites.json")
    sites = sites_doc.get("sites")
    if not isinstance(sites, list):
        raise PackageV2Error("PACKAGE_SITE_REGION", "invalid site catalog")
    site_ids: set[str] = set()
    for site in sites:
        site_id = site.get("site_id") if isinstance(site, dict) else None
        region_id = site.get("region_id") if isinstance(site, dict) else None
        cell = site.get("cell") if isinstance(site, dict) else None
        if (
            not isinstance(site_id, str)
            or site_id in site_ids
            or region_id not in owners
            or type(cell) is not int
            or cell not in owners[region_id]
        ):
            raise PackageV2Error("PACKAGE_SITE_REGION", "site is outside its declared region")
        site_ids.add(site_id)


def validate_route_topology(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    load_json: JsonLoader,
) -> None:
    world = load_json(archive.read("world/index.json"), "world/index.json")
    width, height = int(world["width"]), int(world["height"])
    regions_doc = load_json(archive.read("world/regions.json"), "world/regions.json")
    owners = {region["region_id"]: set(region["cells"]) for region in regions_doc["regions"]}
    routes_doc = load_json(archive.read("world/routes.json"), "world/routes.json")
    routes = routes_doc.get("routes") if isinstance(routes_doc, dict) else None
    if not isinstance(routes, list):
        raise PackageV2Error("PACKAGE_ROUTE_TOPOLOGY", "invalid route catalog")
    known_sources = {record["artifact_id"] for record in manifest["artifacts"]} | set(owners)
    route_ids: set[str] = set()

    def contiguous(cells: list[int]) -> bool:
        return all(
            abs((left % width) - (right % width)) + abs((left // width) - (right // width)) == 1
            for left, right in zip(cells, cells[1:])
        )

    for route in routes:
        if not isinstance(route, dict):
            raise PackageV2Error("PACKAGE_ROUTE_TOPOLOGY", "invalid route record")
        route_id = route.get("route_id")
        start = route.get("start_region")
        end = route.get("end_region")
        cells = route.get("cells")
        seasonal = route.get("seasonal_cells")
        sources = route.get("source_ids")
        if (
            not isinstance(route_id, str)
            or route_id in route_ids
            or start == end
            or start not in owners
            or end not in owners
            or not isinstance(cells, list)
            or not cells
            or any(type(cell) is not int or not 0 <= cell < width * height for cell in cells)
            or cells[0] not in owners[start]
            or cells[-1] not in owners[end]
            or not contiguous(cells)
            or not isinstance(seasonal, list)
            or len(seasonal) != 4
            or any(
                not isinstance(path, list)
                or not path
                or path[0] != cells[0]
                or path[-1] != cells[-1]
                or not contiguous(path)
                for path in seasonal
            )
            or not isinstance(sources, list)
            or any(source not in known_sources for source in sources)
        ):
            raise PackageV2Error("PACKAGE_ROUTE_TOPOLOGY", "route topology is inconsistent")
        route_ids.add(route_id)
