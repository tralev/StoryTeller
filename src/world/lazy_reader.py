"""P8.WG1 — Lazy complete-world lookup reader.

Queries world, history, and local-map indexes lazily through stable
fact/source IDs and bounded excerpts. Does NOT deserialize the complete
retained world for each question.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class FactExcerpt:
    """A bounded typed excerpt from the authoritative world."""

    fact_id: str
    kind: str
    field: str
    value: Any
    source_artifact_id: str
    byte_size: int


@dataclass(frozen=True)
class SiteSnapshot:
    """Minimal site record for GM retrieval — no full world deserialization."""

    site_id: str
    region_id: str
    x: int
    y: int
    settlement_id: str
    civilization_id: str
    capital: bool
    local_map_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "region_id": self.region_id,
            "x": self.x,
            "y": self.y,
            "settlement_id": self.settlement_id,
            "civilization_id": self.civilization_id,
            "capital": self.capital,
            "local_map_id": self.local_map_id,
        }


@dataclass(frozen=True)
class RegionSnapshot:
    """Minimal region record."""

    region_id: str
    centre_x: int
    centre_y: int
    biome_id: int
    climate_regime: int
    adjacent_regions: tuple[str, ...]
    cell_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "centre_x": self.centre_x,
            "centre_y": self.centre_y,
            "biome_id": self.biome_id,
            "climate_regime": self.climate_regime,
            "adjacent_regions": list(self.adjacent_regions),
            "cell_count": self.cell_count,
        }


class LazyWorldReader:
    """Query the authoritative world repository without full deserialization.

    Usage::

        reader = LazyWorldReader("tmp/conformance_run/simulated")
        site = reader.site("site_abc123...")
        history = reader.recent_events(region_id="region_...", limit=5)
        route = reader.route_between("region_a", "region_b")
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._artifacts_dir = self.root / "artifacts"
        self._index_cache: dict[str, Any] = {}
        self._file_hash_cache: dict[str, str] = {}
        self._width: int | None = None

    @property
    def width(self) -> int:
        """World grid width, lazily loaded from world_index."""
        if self._width is None:
            wi = self._index("world_index")
            self._width = int(wi.get("width", 64))
        return self._width

    # ── Lazy artifact loading ──────────────────────────────────────

    def _read_json(self, artifact_kind: str) -> dict[str, Any]:
        """Read a single artifact JSON without caching all payloads."""
        path = self._artifacts_dir / f"{artifact_kind}.json"
        if not path.is_file():
            raise KeyError(f"WORLD-LOOKUP: missing artifact {artifact_kind}")
        raw = path.read_bytes()
        self._file_hash_cache[artifact_kind] = hashlib.sha256(raw).hexdigest()
        return cast(dict[str, Any], json.loads(raw))

    def _index(self, kind: str) -> dict[str, Any]:
        """Lazily load an artifact index (single load, cached)."""
        if kind not in self._index_cache:
            self._index_cache[kind] = self._read_json(kind)
        return cast(dict[str, Any], self._index_cache[kind])

    # ── Internal helpers ───────────────────────────────────────────

    def _entries(self, artifact_kind: str) -> list[dict[str, Any]]:
        """Extract the payload array from an artifact JSON.

        Artifacts use either ``payload`` (v2 artifact envelope as a list
        or dict with a nested domain key), or a domain-named key.
        """
        data = self._index(artifact_kind)
        payload = data.get("payload")
        if payload is not None:
            if isinstance(payload, list):
                return list(payload)
            if isinstance(payload, dict):
                nested = payload.get(artifact_kind)
                if isinstance(nested, list):
                    return list(nested)
        # Legacy format: domain-named key
        domain_keys = {
            "sites": ["sites"],
            "regions": ["regions"],
            "routes": ["routes"],
            "civilizations": ["civilizations"],
            "settlements": ["settlements"],
            "biomes": ["biomes"],
            "hydrology": ["hydrology"],
            "resources": ["resources"],
        }
        for key in domain_keys.get(artifact_kind, [artifact_kind]):
            if key in data and isinstance(data[key], list):
                return list(data[key])
        return []

    def _artifact_id(self, artifact_kind: str) -> str:
        """Get the artifact_id from the artifact envelope."""
        return str(self._index(artifact_kind).get("artifact_id", ""))

    # ── Bounded excerpt queries ────────────────────────────────────

    def excerpt(self, fact_id: str, field: str) -> FactExcerpt:
        """Look up a single named field from a fact, returning a bounded excerpt."""
        prefix = fact_id.split("_")[0] if "_" in fact_id else fact_id
        kind_map: dict[str, str] = {
            "region": "regions",
            "site": "sites",
            "route": "routes",
            "civ": "civilizations",
            "settlement": "settlements",
            "event": "history",
            "lake": "hydrology",
            "deposit": "resources",
            "biome": "biomes",
            "magic": "civilizations",
            "religion": "civilizations",
            "lang": "civilizations",
            "people": "civilizations",
            "local": "civilizations",
        }
        artifact_kind = kind_map.get(prefix)
        if artifact_kind is None:
            raise KeyError(f"WORLD-LOOKUP: unknown fact prefix {prefix!r}")
        entries = self._entries(artifact_kind)
        source_id = self._artifact_id(artifact_kind)

        for entry in entries:
            eid = (
                entry.get(f"{prefix}_id")
                or entry.get("id")
                or entry.get("event_id")
                or entry.get("site_id")
                or entry.get("region_id")
                or ""
            )
            if eid == fact_id:
                value = entry.get(field)
                raw_field = json.dumps(value, default=str)
                return FactExcerpt(
                    fact_id=fact_id,
                    kind=prefix,
                    field=field,
                    value=value,
                    source_artifact_id=source_id,
                    byte_size=len(raw_field.encode("utf-8")),
                )

        raise KeyError(f"WORLD-LOOKUP: fact {fact_id!r} not found in {artifact_kind}")

    # ── Structured snapshots (lazy, bounded) ───────────────────────

    def site(self, site_id: str) -> SiteSnapshot:
        """Load a single site without deserializing all sites."""
        entries = self._entries("sites")
        for s in entries:
            if s.get("site_id") == site_id:
                return SiteSnapshot(
                    site_id=str(s["site_id"]),
                    region_id=str(s.get("region_id", "")),
                    x=int(s.get("x", s.get("cell", 0) % self.width)),
                    y=int(s.get("y", s.get("cell", 0) // self.width)),
                    settlement_id=str(s.get("settlement_id", "")),
                    civilization_id=str(s.get("civilization_id", "")),
                    capital=bool(s.get("capital", False)),
                    local_map_id=str(s.get("local_map_id", "")),
                )
        raise KeyError(f"WORLD-LOOKUP: site {site_id!r} not found")

    def region(self, region_id: str) -> RegionSnapshot:
        """Load a single region without deserializing all regions."""
        entries = self._entries("regions")
        for r in entries:
            if r.get("region_id") == region_id:
                center = r.get("center", 0)
                if isinstance(center, (list, tuple)):
                    cx, cy = int(center[0]), int(center[1]) if len(center) > 1 else 0
                else:
                    cx = int(center) % self.width
                    cy = int(center) // self.width
                return RegionSnapshot(
                    region_id=str(r["region_id"]),
                    centre_x=cx,
                    centre_y=cy,
                    biome_id=0,
                    climate_regime=0,
                    adjacent_regions=tuple(r.get("neighbors", [])),
                    cell_count=len(r.get("cells", [])),
                )
        raise KeyError(f"WORLD-LOOKUP: region {region_id!r} not found")

    def route_between(self, region_a: str, region_b: str) -> str | None:
        """Find the route connecting two regions (if any)."""
        entries = self._entries("routes")
        for rt in entries:
            start = rt.get("start_region", rt.get("start_region_id", ""))
            end = rt.get("end_region", rt.get("end_region_id", ""))
            if (start == region_a and end == region_b) or (start == region_b and end == region_a):
                return str(rt.get("route_id", ""))
        return None

    def recent_events(
        self, *, region_id: str | None = None, kind: str | None = None, limit: int = 5
    ) -> tuple[dict[str, Any], ...]:
        """Load recent history events without deserializing all events."""
        entries = self._entries("history")
        result: list[dict[str, Any]] = []
        for event in reversed(entries):
            if region_id is not None:
                locs = event.get("locations", event.get("location_ids", []))
                if region_id not in locs:
                    continue
            if kind is not None and event.get("kind") != kind:
                continue
            result.append(
                {
                    "event_id": event.get("event_id", ""),
                    "year": event.get("year", 0),
                    "month": event.get("month", 1),
                    "kind": event.get("kind", ""),
                    "summary": event.get("summary", ""),
                }
            )
            if len(result) >= limit:
                break
        return tuple(result)

    def present_year(self) -> int:
        """Get the simulation's present year without loading all state."""
        data = self._index("simulation_index")
        return int(data.get("present_year", 0))

    # ── Verification ───────────────────────────────────────────────

    @property
    def loaded_artifact_count(self) -> int:
        """How many distinct artifacts have been loaded so far."""
        return len(self._index_cache)

    def assert_hashes_unchanged(self) -> None:
        """Verify that files on disk match the hashes seen at first load."""
        for kind, expected in list(self._file_hash_cache.items()):
            path = self._artifacts_dir / f"{kind}.json"
            if path.is_file():
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    raise ValueError(f"WORLD-MUTATED: {kind}")

    def hashes(self) -> dict[str, str]:
        return dict(self._file_hash_cache)
