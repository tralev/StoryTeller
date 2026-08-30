"""Canonical sparse natural occupancy overlays for local voxel chunks."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .artifacts import canonical_json
from .local_chunks import LOCAL_CHUNK_DEPTH, LOCAL_CHUNK_HEIGHT, LOCAL_CHUNK_WIDTH
from .numeric import div_floor_exact

NATURAL_OCCUPANCY_KINDS = (
    "aquifer_water",
    "coast_water",
    "mineral_deposit",
    "river_water",
    "sealed_cave",
    "vegetation",
)


@dataclass(frozen=True, order=True)
class LocalOccupancyRecord:
    kind: str
    voxel_indices: tuple[int, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True, order=True)
class LocalOccupancyChunk:
    chunk_x: int
    chunk_y: int
    chunk_z: int
    records: tuple[LocalOccupancyRecord, ...]
    sha256: str


def _payload_bytes(
    chunk_x: int,
    chunk_y: int,
    chunk_z: int,
    records: tuple[LocalOccupancyRecord, ...],
) -> bytes:
    return canonical_json(
        {
            "format": "storyteller.local-occupancy-chunk.v1",
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "chunk_z": chunk_z,
            "records": records,
        }
    )


def generate_occupancy_chunks(
    width: int,
    height: int,
    z_levels: int,
    features: Sequence[object],
) -> tuple[LocalOccupancyChunk, ...]:
    """Partition natural feature cells into hashed sparse chunks."""
    grouped: dict[tuple[int, int, int, str, tuple[str, ...]], list[int]] = defaultdict(list)
    for feature in features:
        kind = str(getattr(feature, "kind"))
        if kind not in NATURAL_OCCUPANCY_KINDS:
            continue
        source_ids = tuple(str(item) for item in getattr(feature, "source_ids"))
        if not source_ids:
            raise ValueError("WG-LOCAL-OCCUPANCY: natural feature lacks provenance")
        for x, y, z in getattr(feature, "cells"):
            if not (0 <= x < width and 0 <= y < height and 0 <= z < z_levels):
                raise ValueError("WG-LOCAL-OCCUPANCY: voxel outside local bounds")
            chunk_x = div_floor_exact(x, LOCAL_CHUNK_WIDTH)
            chunk_y = div_floor_exact(y, LOCAL_CHUNK_HEIGHT)
            chunk_z = div_floor_exact(z, LOCAL_CHUNK_DEPTH)
            local_x = x % LOCAL_CHUNK_WIDTH
            local_y = y % LOCAL_CHUNK_HEIGHT
            local_z = z % LOCAL_CHUNK_DEPTH
            index = (
                local_z * LOCAL_CHUNK_WIDTH * LOCAL_CHUNK_HEIGHT
                + local_y * LOCAL_CHUNK_WIDTH
                + local_x
            )
            grouped[(chunk_x, chunk_y, chunk_z, kind, source_ids)].append(index)
    by_chunk: dict[tuple[int, int, int], list[LocalOccupancyRecord]] = defaultdict(list)
    for (chunk_x, chunk_y, chunk_z, kind, source_ids), indices in grouped.items():
        canonical = tuple(sorted(set(indices)))
        if len(canonical) != len(indices):
            raise ValueError("WG-LOCAL-OCCUPANCY: duplicate feature voxel")
        by_chunk[(chunk_x, chunk_y, chunk_z)].append(
            LocalOccupancyRecord(kind, canonical, source_ids)
        )
    result: list[LocalOccupancyChunk] = []
    for coordinate in sorted(by_chunk, key=lambda item: (item[2], item[1], item[0])):
        records = tuple(sorted(by_chunk[coordinate]))
        digest = hashlib.sha256(_payload_bytes(*coordinate, records)).hexdigest()
        result.append(LocalOccupancyChunk(*coordinate, records, digest))
    return tuple(result)


def validate_occupancy_chunks(
    width: int,
    height: int,
    z_levels: int,
    features: Sequence[object],
    chunks: tuple[LocalOccupancyChunk, ...],
) -> None:
    expected = generate_occupancy_chunks(width, height, z_levels, features)
    if chunks != expected:
        raise ValueError("WG-LOCAL-OCCUPANCY: missing, reordered, corrupt, or forged overlay")
    occupants: dict[tuple[int, int, int, int], set[str]] = defaultdict(set)
    for chunk in chunks:
        for record in chunk.records:
            for index in record.voxel_indices:
                occupants[(chunk.chunk_x, chunk.chunk_y, chunk.chunk_z, index)].add(record.kind)
    incompatible = (
        {"vegetation", "aquifer_water"},
        {"vegetation", "river_water"},
        {"vegetation", "coast_water"},
        {"sealed_cave", "aquifer_water"},
    )
    if any(any(pair <= kinds for pair in incompatible) for kinds in occupants.values()):
        raise ValueError("WG-LOCAL-OCCUPANCY: incompatible natural occupants overlap")


def local_occupancy_chunk_from_mapping(value: Mapping[str, object]) -> LocalOccupancyChunk:
    """Strictly decode and hash-check a persisted occupancy chunk."""
    if set(value) != {"chunk_x", "chunk_y", "chunk_z", "records", "sha256"}:
        raise ValueError("WG-LOCAL-OCCUPANCY-READ: field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-OCCUPANCY-READ: {name} must be an integer")
        return item

    raw_records = value["records"]
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes)):
        raise ValueError("WG-LOCAL-OCCUPANCY-READ: records must be a sequence")
    records: list[LocalOccupancyRecord] = []
    for raw in raw_records:
        if not isinstance(raw, Mapping) or set(raw) != {"kind", "voxel_indices", "source_ids"}:
            raise ValueError("WG-LOCAL-OCCUPANCY-READ: invalid record shape")
        kind, indices, sources = raw["kind"], raw["voxel_indices"], raw["source_ids"]
        if (
            not isinstance(kind, str)
            or kind not in NATURAL_OCCUPANCY_KINDS
            or not isinstance(indices, Sequence)
            or isinstance(indices, (str, bytes))
            or not isinstance(sources, Sequence)
            or isinstance(sources, (str, bytes))
        ):
            raise ValueError("WG-LOCAL-OCCUPANCY-READ: invalid record values")
        index_values = tuple(indices)
        source_values = tuple(sources)
        if (
            any(isinstance(item, bool) or not isinstance(item, int) for item in index_values)
            or not source_values
            or any(not isinstance(item, str) for item in source_values)
        ):
            raise ValueError("WG-LOCAL-OCCUPANCY-READ: invalid record members")
        records.append(LocalOccupancyRecord(kind, index_values, source_values))
    sha256 = value["sha256"]
    if not isinstance(sha256, str):
        raise ValueError("WG-LOCAL-OCCUPANCY-READ: sha256 must be text")
    chunk = LocalOccupancyChunk(
        integer(value, "chunk_x"),
        integer(value, "chunk_y"),
        integer(value, "chunk_z"),
        tuple(records),
        sha256,
    )
    if (
        chunk.sha256
        != hashlib.sha256(
            _payload_bytes(
                chunk.chunk_x,
                chunk.chunk_y,
                chunk.chunk_z,
                chunk.records,
            )
        ).hexdigest()
    ):
        raise ValueError("WG-LOCAL-OCCUPANCY-READ: content hash mismatch")
    return chunk
