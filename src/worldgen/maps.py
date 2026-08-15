"""Canonical dependency-free PNG rendering for derived physical maps."""
from __future__ import annotations

import struct
import zlib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable, Mapping

from .grid import GridSpec
from .numeric import div_round_half_up
from .physical_models import BiomeLayer, RegionLayer, RouteLayer, Terrain
from ..storage.fs import atomic_write_bytes

BIOME_PALETTE_V1 = ((20, 55, 100), (220, 235, 245), (115, 105, 100), (150, 165, 150),
                    (215, 185, 105), (150, 180, 90), (65, 125, 70), (35, 105, 65),
                    (75, 135, 120))
SCALAR_RAMPS_V1 = {
    "biome-v1": ((20, 55, 100), (75, 135, 120)),
    "climate-v1": ((45, 80, 180), (210, 55, 35)),
    "hazard-v1": ((245, 235, 170), (130, 15, 20)),
    "hydrology-v1": ((235, 245, 250), (10, 65, 155)),
    "political-v1": ((65, 65, 65), (225, 205, 120)),
    "resource-v1": ((35, 35, 35), (225, 180, 40)),
    "soil-v1": ((85, 45, 20), (190, 165, 95)),
    "terrain-v1": ((15, 45, 85), (245, 245, 235)),
}
ROUTE_COLOR_V1 = (220, 190, 80)
EMPTY_VECTOR_COLOR_V1 = (20, 20, 20)
RESAMPLING_POLICY_V1 = "nearest-cell-v1"
LABEL_PLACEMENT_POLICY_V1 = "none-v1"
RENDERER_POLICY_V1 = "storyteller-raster-v1"


@dataclass(frozen=True)
class ScalarMapLayer:
    layer_id: str
    source_kind: str
    source_artifact_id: str
    source_layer: str
    color_table_id: str
    resampling: str


@dataclass(frozen=True)
class VectorMapLayer:
    layer_id: str
    source_kind: str
    source_artifact_id: str
    geometry: str
    feature_ids: tuple[str, ...]
    color_table_id: str
    label_placement: str


@dataclass(frozen=True)
class MapLayerCatalog:
    """Canonical presentation-layer references; source facts remain authoritative."""
    format: str
    grid: GridSpec
    scalar_layers: tuple[ScalarMapLayer, ...]
    vector_layers: tuple[VectorMapLayer, ...]

    def __post_init__(self) -> None:
        if self.format != "storyteller.map-layer-catalog.v1":
            raise ValueError("WG-MAP-LAYERS: unsupported format")
        scalar_ids = tuple(layer.layer_id for layer in self.scalar_layers)
        vector_ids = tuple(layer.layer_id for layer in self.vector_layers)
        ids = scalar_ids + vector_ids
        if scalar_ids != tuple(sorted(scalar_ids)) or vector_ids != tuple(sorted(vector_ids)) \
                or len(ids) != len(set(ids)):
            raise ValueError("WG-MAP-LAYERS: layer IDs must be unique and category-sorted")
        if not self.scalar_layers or not self.vector_layers:
            raise ValueError("WG-MAP-LAYERS: scalar and vector layers are required")
        if any(not layer.source_artifact_id for layer in self.scalar_layers + self.vector_layers):
            raise ValueError("WG-MAP-LAYERS: source artifact IDs are required")
        if any(layer.color_table_id not in SCALAR_RAMPS_V1
               or layer.resampling != RESAMPLING_POLICY_V1 for layer in self.scalar_layers):
            raise ValueError("WG-MAP-LAYERS: unknown scalar rendering policy")
        if any(layer.color_table_id not in {"regions-v1", "routes-v1"}
               or layer.label_placement != LABEL_PLACEMENT_POLICY_V1
               for layer in self.vector_layers):
            raise ValueError("WG-MAP-LAYERS: unknown vector rendering policy")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "MapLayerCatalog":
        grid = value.get("grid")
        scalars = value.get("scalar_layers")
        vectors = value.get("vector_layers")
        if not isinstance(grid, Mapping) or not isinstance(scalars, Iterable) \
                or isinstance(scalars, (str, bytes)) or not isinstance(vectors, Iterable) \
                or isinstance(vectors, (str, bytes)):
            raise ValueError("WG-MAP-LAYERS: invalid persisted shape")
        def integer(key: str) -> int:
            item = grid[key]
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError(f"WG-MAP-LAYERS: {key} must be an integer")
            return item
        return cls(
            str(value.get("format")),
            GridSpec(integer("width"), integer("height"), integer("metres_per_world_cell")),
            tuple(ScalarMapLayer(str(item["layer_id"]), str(item["source_kind"]),
                                 str(item["source_artifact_id"]), str(item["source_layer"]),
                                 str(item["color_table_id"]), str(item["resampling"]))
                  for item in scalars if isinstance(item, Mapping)),
            tuple(VectorMapLayer(str(item["layer_id"]), str(item["source_kind"]),
                                 str(item["source_artifact_id"]), str(item["geometry"]),
                                 tuple(str(entry) for entry in item["feature_ids"]),
                                 str(item["color_table_id"]), str(item["label_placement"]))
                  for item in vectors if isinstance(item, Mapping)),
        )


def build_map_layers(grid: GridSpec, scalar_sources: Mapping[str, tuple[str, str, str]],
                     region_artifact_id: str, route_artifact_id: str,
                     regions: RegionLayer, routes: RouteLayer) -> MapLayerCatalog:
    return MapLayerCatalog(
        "storyteller.map-layer-catalog.v1", grid,
        tuple(ScalarMapLayer(layer_id, *scalar_sources[layer_id], f"{layer_id}-v1",
                             RESAMPLING_POLICY_V1)
              for layer_id in sorted(scalar_sources)),
        (
            VectorMapLayer("regions", "regions", region_artifact_id, "cell-mask",
                           tuple(region.region_id for region in regions.regions), "regions-v1",
                           LABEL_PLACEMENT_POLICY_V1),
            VectorMapLayer("routes", "routes", route_artifact_id, "cell-path",
                           tuple(route.route_id for route in routes.routes), "routes-v1",
                           LABEL_PLACEMENT_POLICY_V1),
        ),
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    if len(rgb) != width * height * 3:
        raise ValueError("WG-MAP: pixel payload mismatch")
    scanlines = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) \
        + _chunk(b"IDAT", zlib.compress(scanlines, 9)) + _chunk(b"IEND", b"")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("WG-MAP: invalid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        raise ValueError("WG-MAP: invalid PNG dimensions")
    return width, height


def _ramp_color(value: int, low: int, high: int,
                ramp: tuple[tuple[int, int, int], tuple[int, int, int]]) -> tuple[int, int, int]:
    if low == high:
        return tuple(div_round_half_up(left + right, 2) for left, right in zip(*ramp))
    offset, span = value - low, high - low
    return tuple(left + div_round_half_up((right - left) * offset, span)
                 for left, right in zip(*ramp))


def render_maps(output: Path, terrain: Terrain, biomes: BiomeLayer,
                regions: RegionLayer, routes: RouteLayer,
                layers: MapLayerCatalog | None = None,
                scalar_values: Mapping[str, tuple[int, ...]] | None = None) -> dict[str, Path]:
    if layers is not None:
        if layers.grid != terrain.grid:
            raise ValueError("WG-MAP-LAYERS: renderer grid mismatch")
        if scalar_values is None or set(scalar_values) != {
                layer.layer_id for layer in layers.scalar_layers}:
            raise ValueError("WG-MAP-LAYERS: scalar render sources do not match catalog")
        if any(len(values) != terrain.grid.cell_count for values in scalar_values.values()):
            raise ValueError("WG-MAP-LAYERS: scalar render source size mismatch")
    output.mkdir(parents=True, exist_ok=True)
    # The directory is a derived cache. Remove only files owned by this renderer
    # so a rerun cannot expose stale region maps in the artifact tree.
    for stale in output.glob("region_*.png"):
        stale.unlink()
    route_cells = {cell for route in routes.routes for cell in route.cells}
    biome_pixels = bytearray()
    region_pixels = bytearray()
    route_pixels = bytearray()
    pixels = bytearray()
    for i in terrain.grid.indices():
        biome_color = BIOME_PALETTE_V1[biomes.biome_id.values[i]]
        region_id = regions.cell_region.values[i]
        region_color = BIOME_PALETTE_V1[(region_id % (len(BIOME_PALETTE_V1) - 1)) + 1]
        route_color = ROUTE_COLOR_V1 if i in route_cells else EMPTY_VECTOR_COLOR_V1
        biome_pixels.extend(biome_color)
        region_pixels.extend(region_color)
        route_pixels.extend(route_color)
        pixels.extend(ROUTE_COLOR_V1 if i in route_cells else biome_color)
    result = {name: output / f"{name}.png" for name in ("biomes", "regions", "routes", "world")}
    for name, payload in (("biomes", biome_pixels), ("regions", region_pixels),
                          ("routes", route_pixels), ("world", pixels)):
        atomic_write_bytes(result[name], encode_png(
            terrain.grid.width, terrain.grid.height, bytes(payload)))
    if layers is not None and scalar_values is not None:
        # These diagnostic rasters intentionally use a simple fixed integer
        # ramp. They visualize facts referenced by the catalog; they are not a
        # substitute serialization for those facts.
        for layer in layers.scalar_layers:
            values = scalar_values[layer.layer_id]
            low, high = min(values), max(values)
            ramp = SCALAR_RAMPS_V1[layer.color_table_id]
            rendered = bytearray()
            for value in values:
                rendered.extend(_ramp_color(value, low, high, ramp))
            path = output / f"layer_{layer.layer_id}.png"
            atomic_write_bytes(path, encode_png(terrain.grid.width, terrain.grid.height,
                                                bytes(rendered)))
            result[f"layer_{layer.layer_id}"] = path
    for region in regions.regions:
        selected = set(region.cells)
        points = [terrain.grid.coordinate(i) for i in region.cells]
        min_x, max_x = min(p.x for p in points), max(p.x for p in points)
        min_y, max_y = min(p.y for p in points), max(p.y for p in points)
        width, height = max_x - min_x + 1, max_y - min_y + 1
        region_pixels = bytearray()
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                index = terrain.grid.index(x, y)
                base = index * 3
                source_rgb = pixels[base:base + 3]
                region_pixels.extend(
                    source_rgb if index in selected
                    else bytes(div_round_half_up(channel, 4) for channel in source_rgb)
                )
        path = output / f"{region.region_id}.png"
        atomic_write_bytes(path, encode_png(width, height, bytes(region_pixels)))
        result[region.region_id] = path
    return result


def build_map_manifest(root: Path, paths: Mapping[str, Path], layers: MapLayerCatalog,
                       regions: RegionLayer) -> dict[str, object]:
    scalar = {layer.layer_id: layer for layer in layers.scalar_layers}
    vector = {layer.layer_id: layer for layer in layers.vector_layers}
    region_ids = {region.region_id for region in regions.regions}
    records: dict[str, object] = {}
    for name, path in sorted(paths.items()):
        if name.startswith("layer_"):
            layer_ids = (name.removeprefix("layer_"),)
        elif name == "biomes":
            layer_ids = ("biome",)
        elif name in vector:
            layer_ids = (name,)
        elif name == "world":
            layer_ids = ("biome", "routes")
        elif name in region_ids:
            layer_ids = ("biome", "regions", "routes")
        else:
            raise ValueError(f"WG-MAP: unregistered raster {name}")
        selected = tuple(scalar.get(item) or vector[item] for item in layer_ids)
        data = path.read_bytes()
        width, height = png_dimensions(data)
        records[name] = {
            "path": str(path.relative_to(root)), "sha256": hashlib.sha256(data).hexdigest(),
            "width": width, "height": height, "layer_ids": layer_ids,
            "source_artifact_ids": tuple(sorted({layer.source_artifact_id for layer in selected})),
            "renderer_policy": RENDERER_POLICY_V1,
        }
    return {"format": "storyteller.map-raster-catalog.v1", "rasters": records}


def validate_map_manifest(root: Path, payload: Mapping[str, object],
                          layers: MapLayerCatalog) -> None:
    if payload.get("format") != "storyteller.map-raster-catalog.v1":
        raise ValueError("WG-MAP: unsupported raster catalog")
    rasters = payload.get("rasters")
    if not isinstance(rasters, Mapping) or not rasters:
        raise ValueError("WG-MAP: raster records required")
    known = {layer.layer_id: layer for layer in layers.scalar_layers + layers.vector_layers}
    for name, raw in rasters.items():
        if not isinstance(name, str) or not isinstance(raw, Mapping):
            raise ValueError("WG-MAP: invalid raster record")
        expected_path = f"maps/{name}.png"
        if raw.get("path") != expected_path or raw.get("renderer_policy") != RENDERER_POLICY_V1:
            raise ValueError("WG-MAP: noncanonical path or renderer policy")
        layer_ids = raw.get("layer_ids")
        source_ids = raw.get("source_artifact_ids")
        if not isinstance(layer_ids, Iterable) or isinstance(layer_ids, (str, bytes)) \
                or not isinstance(source_ids, Iterable) or isinstance(source_ids, (str, bytes)):
            raise ValueError("WG-MAP: invalid raster provenance")
        selected = tuple(str(item) for item in layer_ids)
        if not selected or any(item not in known for item in selected):
            raise ValueError("WG-MAP: unknown contributing layer")
        expected_sources = tuple(sorted({known[item].source_artifact_id for item in selected}))
        if tuple(str(item) for item in source_ids) != expected_sources:
            raise ValueError("WG-MAP: source provenance mismatch")
        data = (root / expected_path).read_bytes()
        if hashlib.sha256(data).hexdigest() != raw.get("sha256"):
            raise ValueError("WG-MAP: raster hash mismatch")
        if png_dimensions(data) != (raw.get("width"), raw.get("height")):
            raise ValueError("WG-MAP: raster dimension mismatch")
