"""P8.C05D — Spatial containment, bounding-box, and route-lookup indexes.

Built from authoritative RegionLayer and RouteLayer artifacts.
Index corruption invalidates only derived indexes; rebuild produces
canonical equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .grid import GridSpec
from .artifacts import canonical_json
from .physical_models import RegionLayer, RouteLayer


@dataclass(frozen=True)
class BoundingBox:
    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def __post_init__(self) -> None:
        values = (self.min_x, self.min_y, self.max_x, self.max_y)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("WG-INDEX-QUERY: bounding box coordinates must be integers")
        if self.min_x < 0 or self.min_y < 0 or self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError("WG-INDEX-QUERY: invalid bounding box")

    def contains_point(self, x: int, y: int) -> bool:
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y

    def contains(self, other: "BoundingBox") -> bool:
        return (self.min_x <= other.min_x and other.max_x <= self.max_x
                and self.min_y <= other.min_y and other.max_y <= self.max_y)


@dataclass(frozen=True)
class SpatialIndex:
    """Bounded lazy-lookup index over regions, cells, and bounding boxes."""

    algorithm_version: int
    grid: GridSpec
    region_ids: tuple[str, ...]  # owner number minus one -> stable region ID
    cell_to_region: tuple[int, ...]  # region_id index per cell (-1 = ocean)
    region_bboxes: dict[str, BoundingBox]  # region_id → bbox
    routes_by_region: dict[str, tuple[str, ...]]  # region_id → connected route_ids
    MAX_QUERY_RESULTS = 256

    @classmethod
    def build(cls, regions: RegionLayer, routes: RouteLayer,
              grid: GridSpec) -> "SpatialIndex":
        return cls._build(regions, routes, grid)

    @classmethod
    def _build(cls, regions: RegionLayer, routes: RouteLayer,
               grid_spec: GridSpec | None = None) -> "SpatialIndex":
        region_list = regions.regions
        cell_to_region = list(regions.cell_region.values)
        if grid_spec is None or len(cell_to_region) != grid_spec.cell_count:
            raise ValueError("WG-INDEX: explicit matching grid is required")

        bboxes: dict[str, BoundingBox] = {}
        for region in region_list:
            if not region.cells:
                bboxes[region.region_id] = BoundingBox(0, 0, 0, 0)
                continue
            xs = [grid_spec.coordinate(i).x for i in region.cells]
            ys = [grid_spec.coordinate(i).y for i in region.cells]
            bboxes[region.region_id] = BoundingBox(min(xs), min(ys), max(xs), max(ys))

        routes_by_region: dict[str, list[str]] = {r.region_id: [] for r in region_list}
        for route in routes.routes:
            if route.start_region in routes_by_region:
                routes_by_region[route.start_region].append(route.route_id)
            if route.end_region in routes_by_region:
                routes_by_region[route.end_region].append(route.route_id)

        return cls(2, grid_spec, tuple(region.region_id for region in region_list),
                   tuple(cell_to_region),
                   bboxes,
                   {k: tuple(sorted(v)) for k, v in routes_by_region.items()})

    def region_at(self, x: int, y: int) -> str | None:
        """Return the region containing (x, y), or None if ocean."""
        if not (0 <= x < self.grid.width and 0 <= y < self.grid.height):
            return None
        idx = self.grid.index(x, y)
        region_num = self.cell_to_region[idx]
        if region_num <= 0:
            return None
        return self.region_ids[region_num - 1]

    def regions_in_bbox(self, bbox: BoundingBox, *, limit: int = MAX_QUERY_RESULTS) -> tuple[str, ...]:
        """All regions whose bounding box intersects the query bbox."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        result: list[str] = []
        for rid, rb in self.region_bboxes.items():
            if (rb.min_x <= bbox.max_x and rb.max_x >= bbox.min_x
                    and rb.min_y <= bbox.max_y and rb.max_y >= bbox.min_y):
                result.append(rid)
        return tuple(sorted(result)[:limit])

    def routes_for_region(self, region_id: str) -> tuple[str, ...]:
        """All route IDs connected to a region."""
        return self.routes_by_region.get(region_id, ())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SpatialIndex):
            return NotImplemented
        return (self.region_ids == other.region_ids
                and self.cell_to_region == other.cell_to_region
                and self.region_bboxes == other.region_bboxes
                and self.routes_by_region == other.routes_by_region)


def build_spatial_index(regions: RegionLayer, routes: RouteLayer,
                        grid: GridSpec) -> SpatialIndex:
    """Create the canonical spatial index from authoritative artifacts."""
    return SpatialIndex._build(regions, routes, grid)


def spatial_index_payload(index: SpatialIndex, region_catalog_id: str,
                          region_artifact_id: str, route_artifact_id: str) -> dict[str, object]:
    return {
        "format": "storyteller.spatial-index.v1", "grid": index.grid,
        "cell_region_catalog": region_catalog_id, "region_source": region_artifact_id,
        "route_source": route_artifact_id, "region_bboxes": index.region_bboxes,
        "region_ids": index.region_ids,
        "routes_by_region": index.routes_by_region,
        "max_query_results": SpatialIndex.MAX_QUERY_RESULTS,
    }


def validate_spatial_index_payload(payload: Mapping[str, object], expected: Mapping[str, object],
                                   dependencies: tuple[str, ...]) -> None:
    if canonical_json(payload) != canonical_json(expected):
        raise ValueError("WG-INDEX: spatial index does not match authoritative rebuild")
    sources = (payload.get("cell_region_catalog"), payload.get("region_source"),
               payload.get("route_source"))
    if not set(sources) <= set(dependencies):
        raise ValueError("WG-INDEX: spatial index provenance mismatch")
