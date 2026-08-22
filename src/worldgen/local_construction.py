"""Canonical constructed occupancy chunks for site-local worlds."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .artifacts import canonical_json
from .local_boundaries import LocalBoundaryConditions
from .local_chunks import LOCAL_CHUNK_DEPTH, LOCAL_CHUNK_HEIGHT, LOCAL_CHUNK_WIDTH
from .numeric import div_floor_exact

CONSTRUCTED_FEATURE_KINDS = {
    "bridge", "climbable", "door", "interior", "item", "parcel", "ramp", "road",
    "route_connection", "ruin", "stockpile", "supported_building", "wall", "workshop",
}


@dataclass(frozen=True, order=True)
class ConstructedOccupancyRecord:
    kind: str
    voxel_indices: tuple[int, ...]
    source_ids: tuple[str, ...]
    civilization_id: str
    culture: str
    settlement_status: str
    container_id: str


@dataclass(frozen=True, order=True)
class ConstructedOccupancyChunk:
    chunk_x: int
    chunk_y: int
    chunk_z: int
    records: tuple[ConstructedOccupancyRecord, ...]
    sha256: str


def _payload_bytes(
    chunk_x: int, chunk_y: int, chunk_z: int,
    records: tuple[ConstructedOccupancyRecord, ...],
) -> bytes:
    return canonical_json({
        "format": "storyteller.local-construction-chunk.v1",
        "chunk_x": chunk_x, "chunk_y": chunk_y, "chunk_z": chunk_z,
        "records": records,
    })


def generate_construction_chunks(
    width: int, height: int, z_levels: int, features: Sequence[object],
    boundary: LocalBoundaryConditions,
) -> tuple[ConstructedOccupancyChunk, ...]:
    """Partition constructed cells into culture/owner-aware sparse chunks."""
    building = next(
        (item for item in features if getattr(item, "kind") == "supported_building"), None
    )
    parcel = next((item for item in features if getattr(item, "kind") == "parcel"), None)
    building_id = "" if building is None else str(getattr(building, "feature_id"))
    parcel_id = "" if parcel is None else str(getattr(parcel, "feature_id"))
    grouped: dict[tuple[int, int, int, str, tuple[str, ...], str], list[int]] = defaultdict(list)
    for feature in features:
        kind = str(getattr(feature, "kind"))
        if kind not in CONSTRUCTED_FEATURE_KINDS:
            continue
        source_ids = tuple(str(item) for item in getattr(feature, "source_ids"))
        if not source_ids:
            raise ValueError("WG-LOCAL-CONSTRUCTION: constructed feature lacks provenance")
        if kind in {"interior", "item", "stockpile", "workshop"}:
            container_id = building_id
        elif kind in {"supported_building", "wall"}:
            container_id = parcel_id
        else:
            container_id = ""
        for x, y, z in getattr(feature, "cells"):
            if not (0 <= x < width and 0 <= y < height and 0 <= z < z_levels):
                raise ValueError("WG-LOCAL-CONSTRUCTION: voxel outside local bounds")
            chunk_x, chunk_y, chunk_z = (
                div_floor_exact(x, LOCAL_CHUNK_WIDTH),
                div_floor_exact(y, LOCAL_CHUNK_HEIGHT),
                div_floor_exact(z, LOCAL_CHUNK_DEPTH),
            )
            index = (
                (z % LOCAL_CHUNK_DEPTH) * LOCAL_CHUNK_WIDTH * LOCAL_CHUNK_HEIGHT
                + (y % LOCAL_CHUNK_HEIGHT) * LOCAL_CHUNK_WIDTH
                + x % LOCAL_CHUNK_WIDTH
            )
            grouped[(chunk_x, chunk_y, chunk_z, kind, source_ids, container_id)].append(index)
    chunks: dict[tuple[int, int, int], list[ConstructedOccupancyRecord]] = defaultdict(list)
    for key, indices in grouped.items():
        chunk_x, chunk_y, chunk_z, kind, sources, container_id = key
        canonical = tuple(sorted(set(indices)))
        if len(canonical) != len(indices):
            raise ValueError("WG-LOCAL-CONSTRUCTION: duplicate constructed voxel")
        chunks[(chunk_x, chunk_y, chunk_z)].append(ConstructedOccupancyRecord(
            kind, canonical, sources, boundary.civilization_id, boundary.culture,
            boundary.settlement_status, container_id,
        ))
    result: list[ConstructedOccupancyChunk] = []
    for coordinate in sorted(chunks, key=lambda item: (item[2], item[1], item[0])):
        records = tuple(sorted(chunks[coordinate]))
        digest = hashlib.sha256(_payload_bytes(*coordinate, records)).hexdigest()
        result.append(ConstructedOccupancyChunk(*coordinate, records, digest))
    return tuple(result)


def validate_construction_chunks(
    width: int, height: int, z_levels: int, features: Sequence[object],
    boundary: LocalBoundaryConditions, chunks: tuple[ConstructedOccupancyChunk, ...],
) -> None:
    if chunks != generate_construction_chunks(
        width, height, z_levels, features, boundary
    ):
        raise ValueError("WG-LOCAL-CONSTRUCTION: missing, reordered, corrupt, or forged overlay")
    cells = {
        str(getattr(feature, "kind")): set(getattr(feature, "cells"))
        for feature in features if str(getattr(feature, "kind")) in CONSTRUCTED_FEATURE_KINDS
    }
    building = cells.get("supported_building", set())
    parcel = cells.get("parcel", set())
    contained = cells.get("interior", set()) | cells.get("item", set())
    contained |= cells.get("stockpile", set()) | cells.get("workshop", set())
    if not building or not parcel or not contained <= building:
        raise ValueError("WG-LOCAL-CONSTRUCTION: building containment is invalid")
    if not {(x, y) for x, y, _ in building} <= {(x, y) for x, y, _ in parcel}:
        raise ValueError("WG-LOCAL-CONSTRUCTION: building leaves its parcel")
    road = cells.get("road", set())
    if not road or not any(
        abs(rx - bx) + abs(ry - by) + abs(rz - bz) <= 1
        for rx, ry, rz in road for bx, by, bz in building
    ):
        raise ValueError("WG-LOCAL-CONSTRUCTION: building has no street access")
    if cells.get("bridge", set()) and not cells["bridge"] <= road:
        raise ValueError("WG-LOCAL-CONSTRUCTION: bridge is not carried by a street")
    if boundary.settlement_status == "inhabited" and cells.get("ruin", set()):
        raise ValueError(
            "WG-LOCAL-CONSTRUCTION: inhabited settlement cannot be synthesized as ruin"
        )


def construction_chunk_from_mapping(
    value: Mapping[str, object],
) -> ConstructedOccupancyChunk:
    """Strictly decode and hash-check one constructed occupancy chunk."""
    if set(value) != {"chunk_x", "chunk_y", "chunk_z", "records", "sha256"}:
        raise ValueError("WG-LOCAL-CONSTRUCTION-READ: field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-CONSTRUCTION-READ: {name} must be an integer")
        return item

    raw_records = value["records"]
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes)):
        raise ValueError("WG-LOCAL-CONSTRUCTION-READ: records must be a sequence")
    expected_fields = {
        "kind", "voxel_indices", "source_ids", "civilization_id", "culture",
        "settlement_status", "container_id",
    }
    records: list[ConstructedOccupancyRecord] = []
    for raw in raw_records:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise ValueError("WG-LOCAL-CONSTRUCTION-READ: invalid record shape")
        indices, sources = raw["voxel_indices"], raw["source_ids"]
        texts = (raw["kind"], raw["civilization_id"], raw["culture"],
                 raw["settlement_status"], raw["container_id"])
        if (not isinstance(indices, Sequence) or isinstance(indices, (str, bytes))
                or not isinstance(sources, Sequence) or isinstance(sources, (str, bytes))
                or any(not isinstance(item, str) for item in texts)):
            raise ValueError("WG-LOCAL-CONSTRUCTION-READ: invalid record values")
        index_values, source_values = tuple(indices), tuple(sources)
        if (any(isinstance(item, bool) or not isinstance(item, int) for item in index_values)
                or not source_values or any(not isinstance(item, str) for item in source_values)):
            raise ValueError("WG-LOCAL-CONSTRUCTION-READ: invalid record members")
        records.append(ConstructedOccupancyRecord(
            texts[0], index_values, source_values, texts[1], texts[2], texts[3], texts[4]
        ))
    sha256 = value["sha256"]
    if not isinstance(sha256, str):
        raise ValueError("WG-LOCAL-CONSTRUCTION-READ: sha256 must be text")
    chunk = ConstructedOccupancyChunk(
        integer(value, "chunk_x"), integer(value, "chunk_y"),
        integer(value, "chunk_z"), tuple(records), sha256,
    )
    if chunk.sha256 != hashlib.sha256(_payload_bytes(
        chunk.chunk_x, chunk.chunk_y, chunk.chunk_z, chunk.records,
    )).hexdigest():
        raise ValueError("WG-LOCAL-CONSTRUCTION-READ: content hash mismatch")
    return chunk
