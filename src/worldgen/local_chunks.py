"""Canonical bounded 3D material chunks for site-local worlds."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .local_binary import encode_local_chunk
from .numeric import div_floor_exact

LOCAL_CHUNK_WIDTH = 32
LOCAL_CHUNK_HEIGHT = 32
LOCAL_CHUNK_DEPTH = 16


@dataclass(frozen=True, order=True)
class LocalVoxelChunk:
    chunk_x: int
    chunk_y: int
    chunk_z: int
    width: int
    height: int
    depth: int
    materials: tuple[int, ...]
    sha256: str


def _chunk_bytes(
    chunk_x: int,
    chunk_y: int,
    chunk_z: int,
    width: int,
    height: int,
    depth: int,
    materials: tuple[int, ...],
) -> bytes:
    return encode_local_chunk(
        "material",
        {
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "chunk_z": chunk_z,
            "width": width,
            "height": height,
            "depth": depth,
            "materials": materials,
        }
    )


def encode_material_chunk(chunk: LocalVoxelChunk) -> bytes:
    return _chunk_bytes(
        chunk.chunk_x, chunk.chunk_y, chunk.chunk_z,
        chunk.width, chunk.height, chunk.depth, chunk.materials,
    )


def _make_chunk(
    chunk_x: int,
    chunk_y: int,
    chunk_z: int,
    width: int,
    height: int,
    depth: int,
    materials: tuple[int, ...],
) -> LocalVoxelChunk:
    digest = hashlib.sha256(
        _chunk_bytes(
            chunk_x,
            chunk_y,
            chunk_z,
            width,
            height,
            depth,
            materials,
        )
    ).hexdigest()
    return LocalVoxelChunk(
        chunk_x,
        chunk_y,
        chunk_z,
        width,
        height,
        depth,
        materials,
        digest,
    )


def generate_material_chunks(
    width: int,
    height: int,
    z_levels: int,
    surface_height: tuple[int, ...],
    strata: tuple[int, ...],
) -> tuple[LocalVoxelChunk, ...]:
    """Materialize every local voxel in canonical z/y/x chunk order."""
    chunks: list[LocalVoxelChunk] = []
    for origin_z in range(0, z_levels, LOCAL_CHUNK_DEPTH):
        for origin_y in range(0, height, LOCAL_CHUNK_HEIGHT):
            for origin_x in range(0, width, LOCAL_CHUNK_WIDTH):
                chunk_width = min(LOCAL_CHUNK_WIDTH, width - origin_x)
                chunk_height = min(LOCAL_CHUNK_HEIGHT, height - origin_y)
                chunk_depth = min(LOCAL_CHUNK_DEPTH, z_levels - origin_z)
                materials = tuple(
                    strata[z] if z <= surface_height[y * width + x] else 0
                    for z in range(origin_z, origin_z + chunk_depth)
                    for y in range(origin_y, origin_y + chunk_height)
                    for x in range(origin_x, origin_x + chunk_width)
                )
                chunks.append(
                    _make_chunk(
                        div_floor_exact(origin_x, LOCAL_CHUNK_WIDTH),
                        div_floor_exact(origin_y, LOCAL_CHUNK_HEIGHT),
                        div_floor_exact(origin_z, LOCAL_CHUNK_DEPTH),
                        chunk_width,
                        chunk_height,
                        chunk_depth,
                        materials,
                    )
                )
    return tuple(chunks)


def validate_material_chunks(
    width: int,
    height: int,
    z_levels: int,
    surface_height: tuple[int, ...],
    strata: tuple[int, ...],
    chunks: tuple[LocalVoxelChunk, ...],
) -> None:
    expected = generate_material_chunks(width, height, z_levels, surface_height, strata)
    if chunks != expected:
        raise ValueError(
            "WG-LOCAL-CHUNK: missing, reordered, corrupt, or contradictory material chunk"
        )


def local_voxel_chunk_from_mapping(value: Mapping[str, object]) -> LocalVoxelChunk:
    """Strictly decode and hash-check one persisted local material chunk."""
    expected = {
        "chunk_x",
        "chunk_y",
        "chunk_z",
        "width",
        "height",
        "depth",
        "materials",
        "sha256",
    }
    if set(value) != expected:
        raise ValueError("WG-LOCAL-CHUNK-READ: field set mismatch")

    def integer(name: str) -> int:
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-CHUNK-READ: {name} must be an integer")
        return item

    raw_materials = value["materials"]
    if not isinstance(raw_materials, Sequence) or isinstance(raw_materials, (str, bytes)):
        raise ValueError("WG-LOCAL-CHUNK-READ: materials must be a sequence")
    materials = tuple(raw_materials)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in materials):
        raise ValueError("WG-LOCAL-CHUNK-READ: materials must contain integers")
    sha256 = value["sha256"]
    if not isinstance(sha256, str):
        raise ValueError("WG-LOCAL-CHUNK-READ: sha256 must be text")
    chunk = LocalVoxelChunk(
        integer("chunk_x"),
        integer("chunk_y"),
        integer("chunk_z"),
        integer("width"),
        integer("height"),
        integer("depth"),
        materials,
        sha256,
    )
    expected_hash = hashlib.sha256(
        _chunk_bytes(
            chunk.chunk_x,
            chunk.chunk_y,
            chunk.chunk_z,
            chunk.width,
            chunk.height,
            chunk.depth,
            chunk.materials,
        )
    ).hexdigest()
    if chunk.sha256 != expected_hash:
        raise ValueError("WG-LOCAL-CHUNK-READ: content hash mismatch")
    return chunk
