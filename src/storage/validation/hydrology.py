"""Hydrology catalog topology validation for v2 packages."""

from __future__ import annotations

import zipfile

from .common import JsonLoader, PackageV2Error


def validate_hydrology_catalog(
    archive: zipfile.ZipFile, load_json: JsonLoader
) -> None:
    world = load_json(archive.read("world/index.json"), "world/index.json")
    cell_count = int(world["width"]) * int(world["height"])
    document = load_json(
        archive.read("world/hydrology.json"), "world/hydrology.json"
    )
    if not isinstance(document, dict):
        raise PackageV2Error("PACKAGE_HYDROLOGY_CATALOG", "invalid hydrology catalog")
    lakes, rivers, terminals = (
        document.get("lakes"),
        document.get("rivers"),
        document.get("terminals"),
    )
    if not all(isinstance(records, list) for records in (lakes, rivers, terminals)):
        raise PackageV2Error(
            "PACKAGE_HYDROLOGY_CATALOG", "invalid hydrology collections"
        )
    assert isinstance(lakes, list)
    assert isinstance(rivers, list)
    assert isinstance(terminals, list)

    lake_ids: set[str] = set()
    lake_cells: set[int] = set()
    for lake in lakes:
        lake_id = lake.get("lake_id") if isinstance(lake, dict) else None
        cells = lake.get("cells") if isinstance(lake, dict) else None
        spillway = lake.get("spillway_cell") if isinstance(lake, dict) else None
        outlet = lake.get("outlet") if isinstance(lake, dict) else None
        if (
            not isinstance(lake_id, str)
            or lake_id in lake_ids
            or not isinstance(cells, list)
            or len(cells) != len(set(cells))
            or any(type(cell) is not int or not 0 <= cell < cell_count for cell in cells)
            or bool(lake_cells.intersection(cells))
            or (spillway is not None and spillway not in cells)
            or (
                outlet is not None
                and (type(outlet) is not int or not 0 <= outlet < cell_count)
            )
        ):
            raise PackageV2Error("PACKAGE_HYDROLOGY_CATALOG", "invalid lake topology")
        lake_ids.add(lake_id)
        lake_cells.update(cells)

    river_edges: set[tuple[int, int]] = set()
    for river in rivers:
        upstream = river.get("upstream") if isinstance(river, dict) else None
        downstream = river.get("downstream") if isinstance(river, dict) else None
        discharge = river.get("discharge_m3s") if isinstance(river, dict) else None
        seasonal = river.get("seasonal_discharge_m3s") if isinstance(river, dict) else None
        if (
            type(upstream) is not int
            or type(downstream) is not int
            or upstream == downstream
            or not 0 <= upstream < cell_count
            or not 0 <= downstream < cell_count
            or (upstream, downstream) in river_edges
            or type(discharge) is not int
            or discharge < 0
            or not isinstance(seasonal, list)
            or len(seasonal) != 4
            or any(type(value) is not int or value < 0 for value in seasonal)
        ):
            raise PackageV2Error("PACKAGE_HYDROLOGY_CATALOG", "invalid river topology")
        river_edges.add((upstream, downstream))

    terminal_ids: set[str] = set()
    terminal_cells: set[int] = set()
    for terminal in terminals:
        terminal_id = terminal.get("terminal_id") if isinstance(terminal, dict) else None
        cell = terminal.get("cell") if isinstance(terminal, dict) else None
        if (
            not isinstance(terminal_id, str)
            or terminal_id in terminal_ids
            or type(cell) is not int
            or not 0 <= cell < cell_count
            or cell in terminal_cells
        ):
            raise PackageV2Error(
                "PACKAGE_HYDROLOGY_CATALOG", "invalid drainage terminal"
            )
        terminal_ids.add(terminal_id)
        terminal_cells.add(cell)
