"""Verified bounded readers for canonical derived physical indexes."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .artifacts import WorldArtifactRepository
from .grid import DenseGridCatalog, DenseGridRepository, IntGrid
from .indexes import BoundingBox, SpatialIndex


@dataclass(frozen=True)
class IndexedEntity:
    entity_id: str
    kind: str
    source_artifact_id: str


@dataclass(frozen=True)
class IndexLoadBudget:
    artifact_envelopes: int
    dense_chunks: int


@dataclass(frozen=True)
class RegionReferences:
    region_id: str
    route_ids: tuple[str, ...]
    deposit_ids: tuple[str, ...]


@dataclass(frozen=True)
class CellReferences:
    cell_index: int
    river_ids: tuple[str, ...]
    lake_ids: tuple[str, ...]


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(message)
    return value


def _strings(value: object, message: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(message)
    return tuple(str(item) for item in value)


class VerifiedSpatialIndexReader:
    MAX_QUERY_RESULTS = SpatialIndex.MAX_QUERY_RESULTS

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.repository = WorldArtifactRepository(self.root / "artifacts")
        self.artifact = self.repository.load_verified("spatial_index")
        self.payload = _mapping(self.artifact.payload, "WG-INDEX: invalid spatial payload")
        if self.payload.get("format") != "storyteller.spatial-index.v1":
            raise ValueError("WG-INDEX: unsupported spatial index")
        source_ids = tuple(str(self.payload[key]) for key in
                           ("cell_region_catalog", "region_source", "route_source"))
        if not set(source_ids) <= set(self.artifact.depends_on):
            raise ValueError("WG-INDEX: spatial provenance mismatch")
        self._ownership: IntGrid[int] | None = None
        self._loaded_artifacts = {"spatial_index"}
        self._dense_chunks = 0

    @property
    def load_budget(self) -> IndexLoadBudget:
        return IndexLoadBudget(len(self._loaded_artifacts), self._dense_chunks)

    def _region_ownership(self) -> IntGrid[int]:
        if self._ownership is None:
            catalog_artifact = self.repository.load_verified("region_grid_catalog")
            if catalog_artifact.artifact_id != self.payload["cell_region_catalog"]:
                raise ValueError("WG-INDEX: region catalog identity mismatch")
            catalog = DenseGridCatalog.from_mapping(
                _mapping(catalog_artifact.payload, "WG-INDEX: invalid region catalog"))
            manifest = catalog.manifest("region_cell_region")
            self._ownership = DenseGridRepository(self.root / "chunks").load(manifest)
            self._loaded_artifacts.add("region_grid_catalog")
            self._dense_chunks += len(manifest.chunks)
        return self._ownership

    def region_at(self, x: int, y: int) -> str | None:
        if (isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int)
                or not isinstance(y, int)):
            raise ValueError("WG-INDEX-QUERY: point coordinates must be integers")
        owner = self._region_ownership()
        if not (0 <= x < owner.spec.width and 0 <= y < owner.spec.height):
            return None
        value = owner.values[owner.spec.index(x, y)]
        return None if value <= 0 else f"region_{value:05d}"

    def regions_in_bbox(self, bbox: BoundingBox, *, limit: int = MAX_QUERY_RESULTS) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        raw = _mapping(self.payload.get("region_bboxes"), "WG-INDEX: missing region boxes")
        found = []
        for region_id, value in raw.items():
            box = _mapping(value, "WG-INDEX: invalid region box")
            if (int(box["min_x"]) <= bbox.max_x and int(box["max_x"]) >= bbox.min_x
                    and int(box["min_y"]) <= bbox.max_y and int(box["max_y"]) >= bbox.min_y):
                found.append(region_id)
        return tuple(sorted(found)[:limit])

    def routes_for_region(self, region_id: str) -> tuple[str, ...]:
        values = _mapping(self.payload.get("routes_by_region"), "WG-INDEX: missing route lookup")
        return _strings(values.get(region_id, ()), "WG-INDEX: invalid route lookup")


class VerifiedReferenceIndexReader:
    MAX_QUERY_RESULTS = 256

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.repository = WorldArtifactRepository(self.root / "artifacts")
        self.artifact = self.repository.load_verified("reference_index")
        self.payload = _mapping(self.artifact.payload, "WG-INDEX: invalid reference payload")
        if self.payload.get("format") != "storyteller.reference-index.v1":
            raise ValueError("WG-INDEX: unsupported reference index")
        self.sources = _mapping(self.payload.get("sources"), "WG-INDEX: missing sources")
        if not set(self.sources.values()) <= set(self.artifact.depends_on):
            raise ValueError("WG-INDEX: reference provenance mismatch")

    @property
    def load_budget(self) -> IndexLoadBudget:
        return IndexLoadBudget(1, 0)

    @staticmethod
    def _entity_id(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError("WG-INDEX-QUERY: invalid entity ID")
        return value

    def entity(self, entity_id: str) -> IndexedEntity | None:
        entity_id = self._entity_id(entity_id)
        entities = _mapping(self.payload.get("entities"), "WG-INDEX: missing entities")
        source_kind = {"regions": "regions", "routes": "routes", "lakes": "hydrology",
                       "species": "species", "deposits": "resources"}
        for plural, kind in source_kind.items():
            if entity_id in _strings(entities.get(plural, ()), "WG-INDEX: invalid entity lookup"):
                return IndexedEntity(entity_id, plural[:-1] if plural != "species" else "species",
                                     str(self.sources[kind]))
        return None

    def route(self, route_id: str) -> IndexedEntity | None:
        result = self.entity(route_id)
        return result if result is not None and result.kind == "route" else None

    def by_source_id(self, source_artifact_id: str,
                     *, limit: int = MAX_QUERY_RESULTS) -> tuple[IndexedEntity, ...]:
        self._entity_id(source_artifact_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        entities = _mapping(self.payload.get("entities"), "WG-INDEX: missing entities")
        source_kind = {"regions": "regions", "routes": "routes", "lakes": "hydrology",
                       "species": "species", "deposits": "resources"}
        found = []
        for plural, kind in source_kind.items():
            if str(self.sources[kind]) != source_artifact_id:
                continue
            for entity_id in _strings(entities.get(plural, ()), "WG-INDEX: invalid entity lookup"):
                found.append(IndexedEntity(
                    entity_id, plural[:-1] if plural != "species" else "species",
                    source_artifact_id,
                ))
        return tuple(sorted(found, key=lambda item: (item.kind, item.entity_id))[:limit])

    def reverse(self, relation: str, key: str, *, limit: int = MAX_QUERY_RESULTS) -> tuple[str, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        if relation not in {"routes_through_region", "deposits_in_region", "species_in_biome",
                            "rivers_by_cell", "lakes_by_cell"}:
            raise ValueError("WG-INDEX-QUERY: unknown reverse relation")
        values = _mapping(self.payload.get(relation), "WG-INDEX: missing reverse lookup")
        return _strings(values.get(key, ()), "WG-INDEX: invalid reverse lookup")[:limit]

    def active_between(self, start: int, end: int, *, limit: int = MAX_QUERY_RESULTS) -> tuple[str, ...]:
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                or not isinstance(end, int) or start > end):
            raise ValueError("WG-INDEX-QUERY: invalid temporal range")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        ranges = _mapping(self.payload.get("temporal_ranges"), "WG-INDEX: missing temporal lookup")
        found = []
        for entity_id, value in ranges.items():
            if not isinstance(value, Sequence) or len(value) != 2:
                raise ValueError("WG-INDEX: invalid temporal record")
            first, last = value
            if int(first) <= end and (last is None or start <= int(last)):
                found.append(entity_id)
        return tuple(sorted(found)[:limit])


class VerifiedWorldIndex:
    """Single bounded facade over all published P8.C05D index query forms."""

    def __init__(self, root: str | Path) -> None:
        self.spatial = VerifiedSpatialIndexReader(root)
        self.references = VerifiedReferenceIndexReader(root)

    @property
    def load_budget(self) -> IndexLoadBudget:
        spatial = self.spatial.load_budget
        reference = self.references.load_budget
        return IndexLoadBudget(spatial.artifact_envelopes + reference.artifact_envelopes,
                               spatial.dense_chunks + reference.dense_chunks)

    def fact(self, fact_id: str) -> IndexedEntity | None:
        return self.references.entity(fact_id)

    def source(self, source_artifact_id: str, *, limit: int = 256) -> tuple[IndexedEntity, ...]:
        return self.references.by_source_id(source_artifact_id, limit=limit)

    def route(self, route_id: str) -> IndexedEntity | None:
        return self.references.route(route_id)

    def point(self, x: int, y: int) -> str | None:
        return self.spatial.region_at(x, y)

    def bounding_box(self, bbox: BoundingBox, *, limit: int = 256) -> tuple[str, ...]:
        return self.spatial.regions_in_bbox(bbox, limit=limit)

    def region(self, region_id: str) -> RegionReferences:
        entity = self.references.entity(region_id)
        if entity is None or entity.kind != "region":
            raise KeyError(region_id)
        return RegionReferences(
            region_id, self.spatial.routes_for_region(region_id),
            self.references.reverse("deposits_in_region", region_id),
        )

    def cell(self, cell_index: int) -> CellReferences:
        if isinstance(cell_index, bool) or not isinstance(cell_index, int) or cell_index < 0:
            raise ValueError("WG-INDEX-QUERY: invalid cell index")
        key = str(cell_index)
        return CellReferences(
            cell_index, self.references.reverse("rivers_by_cell", key),
            self.references.reverse("lakes_by_cell", key),
        )

    def time_range(self, start: int, end: int, *, limit: int = 256) -> tuple[str, ...]:
        return self.references.active_between(start, end, limit=limit)
