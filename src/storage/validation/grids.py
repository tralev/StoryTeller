"""Chunked physical-grid integrity and layer-inventory validation."""

from __future__ import annotations

import hashlib
import zipfile

from ...worldgen.artifacts import GridChunk
from .common import JsonLoader, PackageV2Error


def validate_grid_domain(
    archive: zipfile.ZipFile,
    names: set[str],
    domain: str,
    load_json: JsonLoader,
) -> None:
    """Prove a chunked reader-facing grid projection matches its declared chunks."""
    index_path = f"world/{domain}/index.json"
    if index_path not in names:
        raise PackageV2Error("PACKAGE_GRID_DOMAIN", "grid domain index is missing", index_path)
    index = load_json(archive.read(index_path), index_path)
    if (
        not isinstance(index, dict)
        or index.get("format") != "storyteller.grid-domain-index.v1"
        or not isinstance(index.get("width"), int)
        or not isinstance(index.get("height"), int)
        or not isinstance(index.get("layers"), dict)
        or not index["layers"]
    ):
        raise PackageV2Error(
            "PACKAGE_GRID_DOMAIN", "grid domain index shape is invalid", index_path
        )
    layers = index["layers"]
    if list(layers) != sorted(layers):
        raise PackageV2Error("PACKAGE_GRID_DOMAIN", "layers must be canonically sorted", index_path)
    for layer, entry in layers.items():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"chunk_width", "chunk_height", "chunks"}
            or not isinstance(entry["chunks"], list)
            or not entry["chunks"]
        ):
            raise PackageV2Error(
                "PACKAGE_GRID_DOMAIN", f"{domain}/{layer} shape is invalid", index_path
            )
        chunk_width, chunk_height = entry["chunk_width"], entry["chunk_height"]
        if (
            type(chunk_width) is not int
            or type(chunk_height) is not int
            or not 1 <= chunk_width <= 256
            or not 1 <= chunk_height <= 256
        ):
            raise PackageV2Error("PACKAGE_GRID_DOMAIN", "invalid nominal chunk shape", index_path)
        expected = [
            (
                y // chunk_height,
                x // chunk_width,
                min(chunk_width, index["width"] - x),
                min(chunk_height, index["height"] - y),
            )
            for y in range(0, index["height"], chunk_height)
            for x in range(0, index["width"], chunk_width)
        ]
        actual = [
            (item.get("chunk_y"), item.get("chunk_x"), item.get("width"), item.get("height"))
            for item in entry["chunks"]
            if isinstance(item, dict)
        ]
        if actual != expected:
            raise PackageV2Error(
                "PACKAGE_GRID_DOMAIN", "chunks do not exactly cover grid", index_path
            )
        previous: tuple[int, int] | None = None
        for descriptor in entry["chunks"]:
            if not isinstance(descriptor, dict) or set(descriptor) != {
                "chunk_x",
                "chunk_y",
                "width",
                "height",
                "sha256",
            }:
                raise PackageV2Error(
                    "PACKAGE_GRID_DOMAIN",
                    f"{domain}/{layer} chunk descriptor invalid",
                    index_path,
                )
            order = (descriptor["chunk_y"], descriptor["chunk_x"])
            if previous is not None and order <= previous:
                raise PackageV2Error(
                    "PACKAGE_GRID_DOMAIN",
                    f"{domain}/{layer} chunks must be canonically ordered",
                    index_path,
                )
            previous = order
            chunk_path = f"world/{domain}/chunks/{layer}/{descriptor['sha256']}.bin"
            if chunk_path not in names:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_COVERAGE", "indexed grid chunk missing", chunk_path
                )
            data = archive.read(chunk_path)
            if hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "grid chunk identity mismatch", chunk_path
                )
            try:
                chunk = GridChunk.decode(data)
            except (KeyError, TypeError, ValueError) as error:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "invalid grid chunk payload", chunk_path
                ) from error
            if (
                chunk.layer != layer
                or chunk.chunk_x != descriptor["chunk_x"]
                or chunk.chunk_y != descriptor["chunk_y"]
                or chunk.width != descriptor["width"]
                or chunk.height != descriptor["height"]
            ):
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "grid chunk header mismatch", chunk_path
                )


def validate_climate_layers(archive: zipfile.ZipFile, load_json: JsonLoader) -> None:
    source = load_json(archive.read("world/source/climate.json"), "world/source/climate.json")
    payload = source.get("payload") if isinstance(source, dict) else None
    season_count = payload.get("season_count") if isinstance(payload, dict) else None
    if type(season_count) is not int or not 1 <= season_count <= 12:
        raise PackageV2Error("PACKAGE_CLIMATE_LAYERS", "invalid climate season count")
    expected = {
        "climate_annual_temperature_millic",
        "climate_annual_precipitation_mm",
        "climate_weather_regime",
    }
    for index in range(season_count):
        prefix = f"climate_season_{index:02d}"
        expected.update(
            f"{prefix}_{field}"
            for field in (
                "temperature_millic",
                "precipitation_mm",
                "evaporation_mm",
                "snowpack_mm",
                "ice",
                "storm_ppm",
                "wind_x_mmps",
                "wind_y_mmps",
                "hazard_ppm",
            )
        )
    climate = load_json(archive.read("world/climate/index.json"), "world/climate/index.json")
    if not isinstance(climate, dict) or set(climate.get("layers", {})) != expected:
        raise PackageV2Error("PACKAGE_CLIMATE_LAYERS", "climate layers differ from season count")


def validate_physical_layer_sets(archive: zipfile.ZipFile, load_json: JsonLoader) -> None:
    expected = {
        "hydrology": {
            "hydrology_filled_elevation_mm",
            "hydrology_flow_to",
            "hydrology_accumulation",
            "hydrology_watershed_id",
            "hydrology_coastline",
            "hydrology_aquifer_capacity_mm",
            "hydrology_salinity_ppm",
            "hydrology_snowpack_mm",
            "hydrology_glacier",
            "hydrology_delta",
        },
        "geology": {
            "geology_rock_class_id",
            "geology_strata_id",
            "geology_parent_material_id",
            "geology_fault",
            "geology_volcano",
            "geology_tectonic_relief_mm",
        },
        "resource_grid": {"resource_renewable_yield"},
    }
    for domain, layers in expected.items():
        path = f"world/{domain}/index.json"
        document = load_json(archive.read(path), path)
        if set(document.get("layers", {})) != layers:
            code = (
                "PACKAGE_HYDROLOGY_CATALOG" if domain == "hydrology" else "PACKAGE_RESOURCE_CATALOG"
            )
            raise PackageV2Error(code, f"{domain} layer inventory differs")


def grid_layer_values(
    archive: zipfile.ZipFile,
    domain: str,
    layer: str,
    load_json: JsonLoader,
) -> tuple[int, ...]:
    path = f"world/{domain}/index.json"
    index = load_json(archive.read(path), path)
    width, height = index["width"], index["height"]
    values = [0] * (width * height)
    for descriptor in index["layers"][layer]["chunks"]:
        chunk_path = f"world/{domain}/chunks/{layer}/{descriptor['sha256']}.bin"
        chunk = GridChunk.decode(archive.read(chunk_path))
        for local_y in range(chunk.height):
            for local_x in range(chunk.width):
                target = (chunk.chunk_y + local_y) * width + chunk.chunk_x + local_x
                values[target] = chunk.values[local_y * chunk.width + local_x]
    return tuple(values)
