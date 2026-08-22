"""Typed forcing plan for conditional local-world feature families."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .local_boundaries import CARDINAL_EDGES, LocalBoundaryConditions


@dataclass(frozen=True)
class LocalConditionalPlan:
    coastline: bool
    river_directions: tuple[str, ...]
    route_directions: tuple[str, ...]
    bridge_directions: tuple[str, ...]
    deposit_ids: tuple[str, ...]
    settlement_form: str


@dataclass(frozen=True, order=True)
class ConditionalFeatureSpec:
    key: str
    kind: str
    cells: tuple[tuple[int, int, int], ...]
    source_ids: tuple[str, ...]

    @property
    def feature_id(self) -> str:
        """Compatibility identity consumed by sparse chunk builders."""
        return self.key


def plan_local_conditionals(
    boundary: LocalBoundaryConditions, street_axis: str,
) -> LocalConditionalPlan:
    """Resolve all conditional families without relying on fixture incidence."""
    if street_axis not in {"east_west", "north_south"}:
        raise ValueError("WG-LOCAL-CONDITIONAL: invalid street axis")
    expected_directions = tuple(direction for direction, _, _ in CARDINAL_EDGES)
    if tuple(edge.direction for edge in boundary.edges) != expected_directions:
        raise ValueError("WG-LOCAL-CONDITIONAL: noncanonical edge order")
    river_directions = tuple(
        edge.direction for edge in boundary.edges if edge.river_edge_ids
    )
    route_directions = tuple(
        edge.direction for edge in boundary.edges if edge.route_ids
    )
    aligned = {"east", "west"} if street_axis == "east_west" else {"north", "south"}
    bridge_directions = tuple(
        direction for direction in river_directions
        if direction in route_directions and direction in aligned
    )
    status = boundary.settlement_status
    if status not in {"inhabited", "abandoned", "ruined"}:
        raise ValueError("WG-LOCAL-CONDITIONAL: unsupported settlement status")
    return LocalConditionalPlan(
        boundary.coastline, river_directions, route_directions, bridge_directions,
        boundary.deposit_ids, status,
    )


def synthesize_conditional_features(
    boundary: LocalBoundaryConditions, plan: LocalConditionalPlan,
    width: int, height: int, z_levels: int, surface: tuple[int, ...],
    center: tuple[int, int, int], cave: tuple[tuple[int, int, int], ...],
    building: tuple[tuple[int, int, int], ...],
    edge_anchors: tuple[tuple[int, int, int], ...], artifact_ids: Mapping[str, str],
) -> tuple[ConditionalFeatureSpec, ...]:
    """Produce the exact conditional feature geometry used by production."""
    specs: list[ConditionalFeatureSpec] = []
    if plan.coastline:
        specs.append(ConditionalFeatureSpec(
            "coast_water", "coast_water",
            tuple((x, 0, min(z_levels - 1, surface[x] + 1)) for x in range(width)),
            (artifact_ids["hydrology"],),
        ))
    for edge, (x, y, _) in zip(boundary.edges, edge_anchors):
        if edge.direction in plan.river_directions:
            specs.append(ConditionalFeatureSpec(
                f"river_water_{edge.direction}", "river_water",
                ((x, y, min(z_levels - 1, surface[y * width + x] + 1)),),
                (artifact_ids["hydrology"], *edge.river_edge_ids),
            ))
        if edge.direction in plan.route_directions:
            if x != center[0]:
                step = 1 if x > center[0] else -1
                route_cells = tuple(
                    (route_x, center[1], center[2])
                    for route_x in range(center[0], x + step, step)
                )
            else:
                step = 1 if y > center[1] else -1
                route_cells = tuple(
                    (center[0], route_y, center[2])
                    for route_y in range(center[1], y + step, step)
                )
            specs.append(ConditionalFeatureSpec(
                f"route_connection_{edge.direction}", "route_connection",
                route_cells, (artifact_ids["routes"], *edge.route_ids),
            ))
        if edge.direction in plan.bridge_directions:
            if edge.direction == "east":
                bridge_cells = ((x - 1, y, center[2]), (x, y, center[2]))
            elif edge.direction == "west":
                bridge_cells = ((x, y, center[2]), (x + 1, y, center[2]))
            elif edge.direction == "south":
                bridge_cells = ((x, y - 1, center[2]), (x, y, center[2]))
            else:
                bridge_cells = ((x, y, center[2]), (x, y + 1, center[2]))
            specs.append(ConditionalFeatureSpec(
                f"bridge_{edge.direction}", "bridge", bridge_cells,
                (artifact_ids["routes"], artifact_ids["hydrology"]),
            ))
    if plan.deposit_ids:
        specs.append(ConditionalFeatureSpec(
            "deposit", "mineral_deposit", (cave[0], cave[-1]),
            (artifact_ids["resources"], *plan.deposit_ids),
        ))
    if plan.settlement_form != "inhabited":
        specs.append(ConditionalFeatureSpec(
            "ruin", "ruin", building,
            (artifact_ids["settlements"], artifact_ids["civilizations"]),
        ))
    return tuple(specs)
