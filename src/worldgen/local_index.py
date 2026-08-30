"""Canonical retained index for every generated site-local world."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

from .artifacts import canonical_json

HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, order=True)
class LocalWorldIndexEntry:
    site_id: str
    archive_path: str
    local_map_sha256: str
    boundary_id: str
    summary_id: str
    material_chunk_hashes: tuple[str, ...]
    occupancy_chunk_hashes: tuple[str, ...]
    construction_chunk_hashes: tuple[str, ...]


@dataclass(frozen=True)
class LocalWorldIndex:
    format: str
    selection_policy: str
    sites: tuple[str, ...]
    entries: tuple[LocalWorldIndexEntry, ...]


def build_local_world_index(local_maps: Sequence[object]) -> LocalWorldIndex:
    entries: list[LocalWorldIndexEntry] = []
    for local in sorted(local_maps, key=lambda item: str(getattr(item, "site_id"))):
        boundary = getattr(local, "boundary")
        summary = getattr(local, "macro_summary")
        if boundary is None or summary is None:
            raise ValueError("WG-LOCAL-INDEX-BUILD: incomplete local map")
        site_id = str(getattr(local, "site_id"))
        entries.append(
            LocalWorldIndexEntry(
                site_id,
                f"world/local/{site_id}/index.json",
                hashlib.sha256(canonical_json(local)).hexdigest(),
                str(getattr(boundary, "boundary_id")),
                str(getattr(summary, "summary_id")),
                tuple(str(getattr(chunk, "sha256")) for chunk in getattr(local, "chunks")),
                tuple(
                    str(getattr(chunk, "sha256")) for chunk in getattr(local, "occupancy_chunks")
                ),
                tuple(
                    str(getattr(chunk, "sha256")) for chunk in getattr(local, "construction_chunks")
                ),
            )
        )
    return LocalWorldIndex(
        "storyteller.local-world-index.v1",
        "all_registered_sites",
        tuple(entry.site_id for entry in entries),
        tuple(entries),
    )


def validate_local_world_index(
    index: LocalWorldIndex,
    local_maps: Sequence[object],
    *,
    expected_site_ids: Sequence[str] | None = None,
    local_root: Path | None = None,
) -> None:
    expected = build_local_world_index(local_maps) if index.entries else index
    if (
        index.format != "storyteller.local-world-index.v1"
        or index.selection_policy != "all_registered_sites"
    ):
        raise ValueError("WG-LOCAL-INDEX-FORMAT: unsupported format")
    if (
        index.sites != tuple(sorted(set(index.sites)))
        or index.entries != tuple(sorted(index.entries))
        or tuple(entry.site_id for entry in index.entries) != index.sites
        or len({entry.archive_path for entry in index.entries}) != len(index.entries)
    ):
        raise ValueError("WG-LOCAL-INDEX-SHAPE: noncanonical or duplicate inventory")
    if any(
        entry.archive_path != f"world/local/{entry.site_id}/index.json"
        or not HASH_RE.fullmatch(entry.local_map_sha256)
        or any(
            not HASH_RE.fullmatch(value)
            for value in (
                *entry.material_chunk_hashes,
                *entry.occupancy_chunk_hashes,
                *entry.construction_chunk_hashes,
            )
        )
        for entry in index.entries
    ):
        raise ValueError("WG-LOCAL-INDEX-SHAPE: invalid path or content hash")
    if expected_site_ids is not None and index.sites != tuple(sorted(expected_site_ids)):
        raise ValueError("WG-LOCAL-INDEX-COVERAGE: registered site inventory mismatch")
    if expected.entries and index != expected:
        raise ValueError("WG-LOCAL-INDEX-CONTENT: local map or chunk identity mismatch")
    if local_root is not None:
        for entry in index.entries:
            path = local_root / f"{entry.site_id}.json"
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != (
                entry.local_map_sha256
            ):
                raise ValueError("WG-LOCAL-INDEX-BYTES: missing or corrupt local map")


def local_world_index_from_mapping(value: Mapping[str, object]) -> LocalWorldIndex:
    if set(value) != {field.name for field in fields(LocalWorldIndex)}:
        raise ValueError("WG-LOCAL-INDEX-READ: index field set mismatch")
    raw_sites, raw_entries = value["sites"], value["entries"]
    if (
        value["format"] != "storyteller.local-world-index.v1"
        or not isinstance(raw_sites, Sequence)
        or isinstance(raw_sites, (str, bytes))
        or any(not isinstance(item, str) for item in raw_sites)
        or not isinstance(raw_entries, Sequence)
        or isinstance(raw_entries, (str, bytes))
    ):
        raise ValueError("WG-LOCAL-INDEX-READ: invalid index shape")
    expected_fields = {field.name for field in fields(LocalWorldIndexEntry)}

    def strings(raw: object) -> tuple[str, ...]:
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, (str, bytes))
            or any(not isinstance(item, str) for item in raw)
        ):
            raise ValueError("WG-LOCAL-INDEX-READ: invalid hash inventory")
        return tuple(raw)

    entries: list[LocalWorldIndexEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise ValueError("WG-LOCAL-INDEX-READ: entry field set mismatch")
        scalar_names = (
            "site_id",
            "archive_path",
            "local_map_sha256",
            "boundary_id",
            "summary_id",
        )
        if any(not isinstance(raw[name], str) or not raw[name] for name in scalar_names):
            raise ValueError("WG-LOCAL-INDEX-READ: invalid entry scalar")
        entries.append(
            LocalWorldIndexEntry(
                str(raw["site_id"]),
                str(raw["archive_path"]),
                str(raw["local_map_sha256"]),
                str(raw["boundary_id"]),
                str(raw["summary_id"]),
                strings(raw["material_chunk_hashes"]),
                strings(raw["occupancy_chunk_hashes"]),
                strings(raw["construction_chunk_hashes"]),
            )
        )
    if value["selection_policy"] != "all_registered_sites":
        raise ValueError("WG-LOCAL-INDEX-READ: invalid selection policy")
    result = LocalWorldIndex(
        str(value["format"]),
        str(value["selection_policy"]),
        tuple(raw_sites),
        tuple(entries),
    )
    validate_local_world_index(result, ())
    return result


def validate_narrative_independent_coverage(
    index: LocalWorldIndex,
    registered_site_ids: Sequence[str],
    narrative_site_ids: Sequence[str],
) -> None:
    """Prove selection is only a consumer subset and never a generation filter."""
    registered = tuple(sorted(set(registered_site_ids)))
    selected = tuple(sorted(set(narrative_site_ids)))
    if len(registered) != len(tuple(registered_site_ids)):
        raise ValueError("WG-LOCAL-SELECTION: duplicate registered site")
    if any(site_id not in set(registered) for site_id in selected):
        raise ValueError("WG-LOCAL-SELECTION: narrative references unknown site")
    if index.selection_policy != "all_registered_sites" or index.sites != registered:
        raise ValueError("WG-LOCAL-SELECTION: narrative filtered the local inventory")
