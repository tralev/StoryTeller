"""Canonical dependency-free PNG rendering for derived physical maps."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .physical_models import BiomeLayer, RegionLayer, RouteLayer, Terrain
from ..storage.fs import atomic_write_bytes

PALETTE = ((20, 55, 100), (220, 235, 245), (115, 105, 100), (150, 165, 150),
           (215, 185, 105), (150, 180, 90), (65, 125, 70), (35, 105, 65), (75, 135, 120))


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    if len(rgb) != width * height * 3:
        raise ValueError("WG-MAP: pixel payload mismatch")
    scanlines = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) \
        + _chunk(b"IDAT", zlib.compress(scanlines, 9)) + _chunk(b"IEND", b"")


def render_maps(output: Path, terrain: Terrain, biomes: BiomeLayer,
                regions: RegionLayer, routes: RouteLayer) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    # The directory is a derived cache. Remove only files owned by this renderer
    # so a rerun cannot expose stale region maps in the artifact tree.
    for stale in output.glob("region_*.png"):
        stale.unlink()
    route_cells = {cell for route in routes.routes for cell in route.cells}
    pixels = bytearray()
    for i in terrain.grid.indices():
        color = (220, 190, 80) if i in route_cells else PALETTE[biomes.biome_id.values[i]]
        pixels.extend(color)
    result = {"world": output / "world.png"}
    atomic_write_bytes(result["world"], encode_png(terrain.grid.width, terrain.grid.height, bytes(pixels)))
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
                region_pixels.extend(source_rgb if index in selected else bytes(c // 4 for c in source_rgb))
        path = output / f"{region.region_id}.png"
        atomic_write_bytes(path, encode_png(width, height, bytes(region_pixels)))
        result[region.region_id] = path
    return result
