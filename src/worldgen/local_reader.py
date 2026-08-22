"""Bounded lazy reader and storage-budget audit for retained local worlds."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, cast

from .local_chunks import local_voxel_chunk_from_mapping
from .local_construction import construction_chunk_from_mapping
from .local_index import LocalWorldIndex, local_world_index_from_mapping
from .local_occupancy import local_occupancy_chunk_from_mapping

MAX_LOCAL_INDEX_BYTES = 16 * 1024 * 1024
MAX_LOCAL_MAP_BYTES = 64 * 1024 * 1024
MAX_LOCAL_CHUNK_BYTES = 2 * 1024 * 1024
MAX_LOCAL_TOTAL_BYTES_PER_SITE = 96 * 1024 * 1024
CHUNK_FAMILIES = ("material", "occupancy", "construction")


class LazyLocalWorldReader:
    """Read one verified local map or chunk while retaining a bounded LRU cache."""

    def __init__(self, root: str | Path, *, cache_entries: int = 2) -> None:
        if cache_entries < 1:
            raise ValueError("WG-LOCAL-READER: cache_entries must be positive")
        self.root = Path(root).resolve()
        raw = (self.root / "local_index.json").read_bytes()
        if len(raw) > MAX_LOCAL_INDEX_BYTES:
            raise ValueError("WG-LOCAL-BUDGET: local index exceeds byte budget")
        self.index: LocalWorldIndex = local_world_index_from_mapping(json.loads(raw))
        self._entries = {entry.site_id: entry for entry in self.index.entries}
        self._capacity = cache_entries
        self._cache: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
        self.disk_reads = 0

    @property
    def cached_entry_count(self) -> int:
        return len(self._cache)

    def _load(
        self, key: tuple[str, str, str], path: Path, max_bytes: int,
        *, expected_file_sha256: str | None = None,
    ) -> dict[str, Any]:
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        raw = path.read_bytes()
        self.disk_reads += 1
        if len(raw) > max_bytes:
            raise ValueError("WG-LOCAL-BUDGET: local member exceeds byte budget")
        if (expected_file_sha256 is not None
                and hashlib.sha256(raw).hexdigest() != expected_file_sha256):
            raise ValueError("WG-LOCAL-READER: local map hash mismatch")
        value = cast(dict[str, Any], json.loads(raw))
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._capacity:
            self._cache.popitem(last=False)
        return value

    def map(self, site_id: str) -> dict[str, Any]:
        entry = self._entries.get(site_id)
        if entry is None:
            raise KeyError(f"WG-LOCAL-READER: unknown site {site_id}")
        path = self.root / "local_maps" / f"{site_id}.json"
        return self._load(
            (site_id, "map", entry.local_map_sha256), path, MAX_LOCAL_MAP_BYTES,
            expected_file_sha256=entry.local_map_sha256,
        )

    def chunk(self, site_id: str, family: str, sha256: str) -> dict[str, Any]:
        entry = self._entries.get(site_id)
        if entry is None or family not in CHUNK_FAMILIES:
            raise KeyError("WG-LOCAL-READER: unknown site or chunk family")
        allowed = {
            "material": entry.material_chunk_hashes,
            "occupancy": entry.occupancy_chunk_hashes,
            "construction": entry.construction_chunk_hashes,
        }[family]
        if sha256 not in allowed:
            raise KeyError("WG-LOCAL-READER: chunk is absent from site inventory")
        path = self.root / "local_chunks" / site_id / family / f"{sha256}.json"
        value = self._load((site_id, family, sha256), path, MAX_LOCAL_CHUNK_BYTES)
        if value.get("sha256") != sha256:
            raise ValueError("WG-LOCAL-READER: chunk hash identity mismatch")
        {
            "material": local_voxel_chunk_from_mapping,
            "occupancy": local_occupancy_chunk_from_mapping,
            "construction": construction_chunk_from_mapping,
        }[family](value)
        return value


def audit_local_storage(root: str | Path, index: LocalWorldIndex) -> dict[str, int]:
    """Reject missing, extra, oversized, or hash-mismatched retained local members."""
    base = Path(root).resolve()
    expected_maps = {f"{entry.site_id}.json" for entry in index.entries}
    actual_maps = {path.name for path in (base / "local_maps").glob("*.json")}
    if actual_maps != expected_maps:
        raise ValueError("WG-LOCAL-BUDGET: local map inventory mismatch")
    total_bytes = (base / "local_index.json").stat().st_size
    chunk_count = 0
    reader = LazyLocalWorldReader(base, cache_entries=1)
    for entry in index.entries:
        reader.map(entry.site_id)
        total_bytes += (base / "local_maps" / f"{entry.site_id}.json").stat().st_size
        for family, hashes in (
            ("material", entry.material_chunk_hashes),
            ("occupancy", entry.occupancy_chunk_hashes),
            ("construction", entry.construction_chunk_hashes),
        ):
            directory = base / "local_chunks" / entry.site_id / family
            actual = {path.stem for path in directory.glob("*.json")}
            if actual != set(hashes):
                raise ValueError("WG-LOCAL-BUDGET: local chunk inventory mismatch")
            for sha256 in hashes:
                reader.chunk(entry.site_id, family, sha256)
                total_bytes += (directory / f"{sha256}.json").stat().st_size
                chunk_count += 1
    total_budget = MAX_LOCAL_INDEX_BYTES + len(index.entries) * MAX_LOCAL_TOTAL_BYTES_PER_SITE
    if total_bytes > total_budget:
        raise ValueError("WG-LOCAL-BUDGET: retained local worlds exceed total disk budget")
    return {
        "site_count": len(index.entries), "chunk_count": chunk_count,
        "total_bytes": total_bytes, "total_budget_bytes": total_budget,
        "max_cache_entries": 1,
    }
