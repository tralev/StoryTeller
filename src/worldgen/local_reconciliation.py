"""Macro-authority reconciliation for site-local material and occupancy chunks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..world.views import WorldView
from .local_boundaries import MacroBoundaryEdge, derive_local_boundaries
from .local_society import derive_cultural_layout, generate_persistent_local_entities
from .numeric import div_floor_exact

if TYPE_CHECKING:
    from .local_maps import LocalFeature, LocalSiteMap


def macro_edge_anchor(
    width: int, height: int, z_levels: int, edge: MacroBoundaryEdge,
) -> tuple[int, int, int]:
    """Project one macro edge to a stable local perimeter elevation anchor."""
    midpoint_x, midpoint_y, midpoint_z = (
        div_floor_exact(width, 2), div_floor_exact(height, 2),
        div_floor_exact(z_levels, 2),
    )
    x, y = {
        "north": (midpoint_x, 0),
        "east": (width - 1, midpoint_y),
        "south": (midpoint_x, height - 1),
        "west": (0, midpoint_y),
    }[edge.direction]
    neighbor = edge.neighbor_elevation_mm
    delta = 0 if neighbor is None else neighbor - edge.elevation_mm
    offset = max(-2, min(2, div_floor_exact(delta, 1_000)))
    return x, y, max(0, min(z_levels - 1, midpoint_z + offset))


def validate_local_reconciliation(world: WorldView, local: LocalSiteMap) -> None:
    """Reject local facts that move, erase, or invent authoritative macro facts."""
    from .local_maps import validate_local_map

    expected_by_site = {
        boundary.site_id: boundary for boundary in derive_local_boundaries(world)
    }
    expected = expected_by_site.get(local.site_id)
    if expected is None or local.boundary != expected:
        raise ValueError("WG-LOCAL-RECONCILE-BOUNDARY: macro boundary mismatch")
    validate_local_map(local)
    features_by_kind: dict[str, list[LocalFeature]] = {}
    for feature in local.features:
        features_by_kind.setdefault(feature.kind, []).append(feature)

    deposits = features_by_kind.get("mineral_deposit", [])
    deposit_ids = {
        source for feature in deposits for source in feature.source_ids
        if source != world.artifact_ids["resources"]
    }
    if deposit_ids != set(expected.deposit_ids):
        raise ValueError("WG-LOCAL-RECONCILE-RESOURCE: deposit set contradicts macro world")
    if bool(features_by_kind.get("coast_water")) != expected.coastline:
        raise ValueError("WG-LOCAL-RECONCILE-COAST: coastline presence mismatch")

    river_ids = {item for edge in expected.edges for item in edge.river_edge_ids}
    local_river_ids = {
        source for feature in features_by_kind.get("river_water", [])
        for source in feature.source_ids if source != world.artifact_ids["hydrology"]
    }
    if local_river_ids != river_ids:
        raise ValueError("WG-LOCAL-RECONCILE-RIVER: river boundary mismatch")
    route_ids = {item for edge in expected.edges for item in edge.route_ids}
    local_route_ids = {
        source for feature in features_by_kind.get("route_connection", [])
        for source in feature.source_ids if source != world.artifact_ids["routes"]
    }
    if local_route_ids != route_ids:
        raise ValueError("WG-LOCAL-RECONCILE-ROUTE: route boundary mismatch")

    expected_anchors = {macro_edge_anchor(
        local.width, local.height, local.z_levels, edge
    ) for edge in expected.edges}
    actual_anchors = {
        cell for feature in features_by_kind.get("macro_elevation_anchor", [])
        for cell in feature.cells
    }
    if actual_anchors != expected_anchors or any(
        local.surface_height[y * local.width + x] != z for x, y, z in expected_anchors
    ):
        raise ValueError("WG-LOCAL-RECONCILE-ELEVATION: perimeter anchor mismatch")
    seed = int(world.payload("world_index")["seed"])
    building = next(
        feature.cells for feature in local.features if feature.kind == "supported_building"
    )
    if (local.layout != derive_cultural_layout(seed, expected)
            or local.entities != generate_persistent_local_entities(seed, expected, building)):
        raise ValueError("WG-LOCAL-RECONCILE-SOCIETY: local culture/entity mismatch")
