import hashlib
from dataclasses import replace

import pytest

from src.worldgen.maps import (
    LABEL_PLACEMENT_POLICY_V1,
    RESAMPLING_POLICY_V1,
    SCALAR_RAMPS_V1,
    build_map_layers,
    build_map_manifest,
    render_maps,
    validate_map_manifest,
)


def test_map_pixels_are_deterministic(tmp_path, physical_world):
    terrain, _, _, biomes, _, regions, routes = physical_world
    first = render_maps(tmp_path / "a", terrain, biomes, regions, routes)
    second = render_maps(tmp_path / "b", terrain, biomes, regions, routes)
    assert set(first) == set(second)
    assert {name: hashlib.sha256(path.read_bytes()).digest() for name, path in first.items()} == {
        name: hashlib.sha256(path.read_bytes()).digest() for name, path in second.items()
    }


def _layers(terrain, regions, routes):
    sources = {
        name: (f"{name}_grid_catalog", f"{name}_grid_catalog_" + "1" * 32, f"{name}_value")
        for name in (
            "biome",
            "climate",
            "hazard",
            "hydrology",
            "political",
            "resource",
            "soil",
            "terrain",
        )
    }
    return build_map_layers(
        terrain.grid, sources, "regions_" + "2" * 32, "routes_" + "3" * 32, regions, routes
    )


def test_render_contract_freezes_styles_dimensions_and_provenance(tmp_path, physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    layers = _layers(terrain, regions, routes)
    values = {
        "biome": biomes.biome_id.values,
        "climate": climate.annual_temperature_millic.values,
        "hazard": climate.seasons[0].hazard_ppm.values,
        "hydrology": hydrology.accumulation.values,
        "political": regions.cell_region.values,
        "resource": resources.renewable_yield.values,
        "soil": tuple(0 for _ in terrain.grid.indices()),
        "terrain": terrain.elevation_mm.values,
    }
    paths = render_maps(tmp_path / "maps", terrain, biomes, regions, routes, layers, values)
    manifest = build_map_manifest(tmp_path, paths, layers, regions)
    validate_map_manifest(tmp_path, manifest, layers)
    assert {layer.color_table_id for layer in layers.scalar_layers} == set(SCALAR_RAMPS_V1)
    assert {layer.resampling for layer in layers.scalar_layers} == {RESAMPLING_POLICY_V1}
    assert {layer.label_placement for layer in layers.vector_layers} == {LABEL_PLACEMENT_POLICY_V1}
    rasters = manifest["rasters"]
    assert isinstance(rasters, dict)
    world = rasters["world"]
    assert isinstance(world, dict)
    assert world["layer_ids"] == ("biome", "routes")
    assert world["width"] == terrain.grid.width
    assert world["height"] == terrain.grid.height


def test_corrupt_raster_is_rejected_without_changing_authoritative_layers(tmp_path, physical_world):
    terrain, hydrology, climate, biomes, resources, regions, routes = physical_world
    layers = _layers(terrain, regions, routes)
    values = {
        "biome": biomes.biome_id.values,
        "climate": climate.annual_temperature_millic.values,
        "hazard": climate.seasons[0].hazard_ppm.values,
        "hydrology": hydrology.accumulation.values,
        "political": regions.cell_region.values,
        "resource": resources.renewable_yield.values,
        "soil": tuple(0 for _ in terrain.grid.indices()),
        "terrain": terrain.elevation_mm.values,
    }
    paths = render_maps(tmp_path / "maps", terrain, biomes, regions, routes, layers, values)
    manifest = build_map_manifest(tmp_path, paths, layers, regions)
    before = layers
    paths["world"].write_bytes(paths["world"].read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="raster hash mismatch"):
        validate_map_manifest(tmp_path, manifest, layers)
    assert layers == before


def test_layer_reader_rejects_unfrozen_style(physical_world):
    terrain, _, _, _, _, regions, routes = physical_world
    layers = _layers(terrain, regions, routes)
    with pytest.raises(ValueError, match="unknown scalar rendering policy"):
        replace(
            layers,
            scalar_layers=(replace(layers.scalar_layers[0], resampling="bilinear"),)
            + layers.scalar_layers[1:],
        )
