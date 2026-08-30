"""Immutable legal 3D movement graphs for site-local worlds."""

from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..world.views import WorldView

if TYPE_CHECKING:
    from .local_maps import LocalSiteMap

MOVEMENT_COSTS = {
    "walk": 10,
    "door": 12,
    "bridge": 14,
    "ramp": 16,
    "stairs": 18,
    "climb": 30,
}
FEATURE_MOVEMENT = {
    "road": "walk",
    "sealed_cave": "walk",
    "interior": "walk",
    "supported_building": "walk",
    "route_connection": "walk",
    "door": "door",
    "bridge": "bridge",
    "ramp": "ramp",
    "vertical_stairs": "stairs",
    "climbable": "climb",
}


@dataclass(frozen=True, order=True)
class LocalMovementEdge:
    source: tuple[int, int, int]
    target: tuple[int, int, int]
    kind: str
    cost: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocalMovementGraph:
    algorithm_version: int
    nodes: tuple[tuple[int, int, int], ...]
    edges: tuple[LocalMovementEdge, ...]


@dataclass(frozen=True)
class LocalPathResult:
    path: tuple[tuple[int, int, int], ...]
    cost: int
    visited_nodes: int


@dataclass(frozen=True)
class MacroRouteTraversal:
    route_id: str
    start_region: str
    end_region: str
    cells: tuple[int, ...]
    cost: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class HierarchicalPathResult:
    route_id: str
    source_local: LocalPathResult
    macro_cells: tuple[int, ...]
    macro_cost: int
    destination_local: LocalPathResult
    total_cost: int


class LocalPathNotFound(ValueError):
    def __init__(
        self,
        start: tuple[int, int, int],
        goal: tuple[int, int, int],
        reachable_nodes: int,
    ) -> None:
        self.start = start
        self.goal = goal
        self.reachable_nodes = reachable_nodes
        super().__init__(f"WG-LOCAL-PATH-NOT-FOUND: {start}->{goal}; reachable={reachable_nodes}")


def _legal_step(
    source: tuple[int, int, int],
    target: tuple[int, int, int],
    kind: str,
) -> bool:
    dx, dy, dz = (abs(source[i] - target[i]) for i in range(3))
    if kind in {"walk", "door", "bridge"}:
        return dz == 0 and dx + dy == 1
    if kind in {"stairs", "climb"}:
        return dx == 0 and dy == 0 and dz == 1
    if kind == "ramp":
        return dx + dy == 1 and dz == 1
    return False


def build_movement_graph(features: Sequence[object]) -> LocalMovementGraph:
    """Build canonical bidirectional edges from explicitly traversable features."""
    edges: set[LocalMovementEdge] = set()
    for feature in features:
        feature_kind = str(getattr(feature, "kind"))
        kind = FEATURE_MOVEMENT.get(feature_kind)
        if kind is None:
            continue
        cells = tuple(getattr(feature, "cells"))
        source_ids = tuple(str(item) for item in getattr(feature, "source_ids"))
        if not source_ids:
            raise ValueError("WG-LOCAL-NAV: movement feature lacks provenance")
        for source, target in zip(cells, cells[1:]):
            if not _legal_step(source, target, kind):
                raise ValueError(f"WG-LOCAL-NAV: illegal {kind} edge")
            edges.add(
                LocalMovementEdge(
                    source,
                    target,
                    kind,
                    MOVEMENT_COSTS[kind],
                    source_ids,
                )
            )
            edges.add(
                LocalMovementEdge(
                    target,
                    source,
                    kind,
                    MOVEMENT_COSTS[kind],
                    source_ids,
                )
            )
    ordered_edges = tuple(sorted(edges))
    nodes = tuple(sorted({cell for edge in ordered_edges for cell in (edge.source, edge.target)}))
    return LocalMovementGraph(1, nodes, ordered_edges)


def validate_movement_graph(
    features: Sequence[object],
    graph: LocalMovementGraph,
) -> None:
    if graph != build_movement_graph(features):
        raise ValueError("WG-LOCAL-NAV: missing, reordered, forged, or illegal movement edge")
    if any(
        edge.cost != MOVEMENT_COSTS.get(edge.kind)
        or not _legal_step(edge.source, edge.target, edge.kind)
        for edge in graph.edges
    ):
        raise ValueError("WG-LOCAL-NAV: invalid movement cost or geometry")


def _heuristic(
    source: tuple[int, int, int],
    target: tuple[int, int, int],
) -> int:
    """Admissible lower bound when a ramp can reduce horizontal and Z together."""
    horizontal = abs(source[0] - target[0]) + abs(source[1] - target[1])
    vertical = abs(source[2] - target[2])
    return max(horizontal, vertical) * min(MOVEMENT_COSTS.values())


def find_local_path(
    graph: LocalMovementGraph,
    start: tuple[int, int, int],
    goal: tuple[int, int, int],
) -> LocalPathResult:
    """Return the canonical minimum-cost path using frozen A* ordering."""
    validate_nodes = set(graph.nodes)
    if start not in validate_nodes or goal not in validate_nodes:
        raise ValueError("WG-LOCAL-PATH-ENDPOINT: start and goal must be graph nodes")
    if start == goal:
        return LocalPathResult((start,), 0, 1)
    adjacency: dict[tuple[int, int, int], list[LocalMovementEdge]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, []).append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda edge: (edge.target, edge.cost, edge.kind, edge.source_ids))

    start_path = (start,)
    queue: list[
        tuple[
            int,
            int,
            tuple[tuple[int, int, int], ...],
            tuple[int, int, int],
        ]
    ] = [(_heuristic(start, goal), 0, start_path, start)]
    best: dict[tuple[int, int, int], tuple[int, tuple[tuple[int, int, int], ...]]] = {
        start: (0, start_path)
    }
    visited: set[tuple[int, int, int]] = set()
    while queue:
        _, cost, path, node = heapq.heappop(queue)
        if best.get(node) != (cost, path):
            continue
        visited.add(node)
        if node == goal:
            return LocalPathResult(path, cost, len(visited))
        for edge in adjacency.get(node, ()):
            next_cost = cost + edge.cost
            next_path = (*path, edge.target)
            previous = best.get(edge.target)
            if previous is not None and previous <= (next_cost, next_path):
                continue
            best[edge.target] = (next_cost, next_path)
            heapq.heappush(
                queue,
                (
                    next_cost + _heuristic(edge.target, goal),
                    next_cost,
                    next_path,
                    edge.target,
                ),
            )
    raise LocalPathNotFound(start, goal, len(visited))


def _route_anchors(
    features: Sequence[object],
    route_id: str,
) -> tuple[tuple[int, int, int], ...]:
    candidates = tuple(
        sorted(
            tuple(getattr(feature, "cells"))[-1]
            for feature in features
            if str(getattr(feature, "kind")) == "route_connection"
            and route_id in tuple(str(item) for item in getattr(feature, "source_ids"))
            and tuple(getattr(feature, "cells"))
        )
    )
    if not candidates:
        raise ValueError(f"WG-LOCAL-HIERARCHY-ANCHOR: route {route_id} has no local anchor")
    return candidates


def _best_anchor_path(
    graph: LocalMovementGraph,
    endpoint: tuple[int, int, int],
    anchors: tuple[tuple[int, int, int], ...],
    *,
    endpoint_first: bool,
) -> LocalPathResult:
    paths: list[LocalPathResult] = []
    for anchor in anchors:
        try:
            paths.append(
                find_local_path(graph, endpoint, anchor)
                if endpoint_first
                else find_local_path(graph, anchor, endpoint)
            )
        except LocalPathNotFound:
            continue
    if not paths:
        raise ValueError("WG-LOCAL-HIERARCHY-ANCHOR: no reachable local anchor")
    return min(paths, key=lambda result: (result.cost, result.path))


def find_hierarchical_path(
    source_graph: LocalMovementGraph,
    source_features: Sequence[object],
    source_region: str,
    start: tuple[int, int, int],
    destination_graph: LocalMovementGraph,
    destination_features: Sequence[object],
    destination_region: str,
    goal: tuple[int, int, int],
    route: MacroRouteTraversal,
) -> HierarchicalPathResult:
    """Compose two local A* paths with one authoritative directed macro route."""
    if source_region == route.start_region and destination_region == route.end_region:
        macro_cells = route.cells
    elif source_region == route.end_region and destination_region == route.start_region:
        macro_cells = tuple(reversed(route.cells))
    else:
        raise ValueError(
            f"WG-LOCAL-HIERARCHY-ROUTE: {route.route_id} does not connect "
            f"{source_region}->{destination_region}"
        )
    if not route.cells or route.cost < 0 or not route.source_ids:
        raise ValueError("WG-LOCAL-HIERARCHY-ROUTE: invalid macro route envelope")
    source_path = _best_anchor_path(
        source_graph,
        start,
        _route_anchors(source_features, route.route_id),
        endpoint_first=True,
    )
    destination_path = _best_anchor_path(
        destination_graph,
        goal,
        _route_anchors(destination_features, route.route_id),
        endpoint_first=False,
    )
    return HierarchicalPathResult(
        route.route_id,
        source_path,
        macro_cells,
        route.cost,
        destination_path,
        source_path.cost + route.cost + destination_path.cost,
    )


def verified_macro_route(
    world: WorldView,
    route_id: str,
) -> MacroRouteTraversal:
    """Resolve one route only through the verified typed macro reader."""
    matches = tuple(route for route in world.routes() if route.fact_id == route_id)
    if len(matches) != 1:
        raise ValueError(f"WG-LOCAL-HIERARCHY-ROUTE: unknown route {route_id}")
    route = matches[0]
    return MacroRouteTraversal(
        route.fact_id,
        str(route.value["start_region"]),
        str(route.value["end_region"]),
        tuple(int(cell) for cell in route.value["cells"]),
        int(route.value["terrain_cost"]),
        route.source_ids,
    )


def find_world_hierarchical_path(
    world: WorldView,
    source_local: LocalSiteMap,
    start: tuple[int, int, int],
    destination_local: LocalSiteMap,
    goal: tuple[int, int, int],
    route_id: str,
) -> HierarchicalPathResult:
    """Route between two reconciled local maps through verified macro authority."""
    if (
        source_local.boundary is None
        or destination_local.boundary is None
        or source_local.movement_graph is None
        or destination_local.movement_graph is None
    ):
        raise ValueError("WG-LOCAL-HIERARCHY-LOCAL: incomplete local navigation envelope")
    return find_hierarchical_path(
        source_local.movement_graph,
        source_local.features,
        source_local.boundary.region_id,
        start,
        destination_local.movement_graph,
        destination_local.features,
        destination_local.boundary.region_id,
        goal,
        verified_macro_route(world, route_id),
    )


def movement_graph_from_mapping(value: Mapping[str, object]) -> LocalMovementGraph:
    """Strictly decode a persisted local movement graph."""
    if set(value) != {"algorithm_version", "nodes", "edges"}:
        raise ValueError("WG-LOCAL-NAV-READ: graph field set mismatch")

    def coordinate(raw: object) -> tuple[int, int, int]:
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, (str, bytes))
            or len(raw) != 3
            or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)
        ):
            raise ValueError("WG-LOCAL-NAV-READ: invalid coordinate")
        return int(raw[0]), int(raw[1]), int(raw[2])

    version, raw_nodes, raw_edges = (value["algorithm_version"], value["nodes"], value["edges"])
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or not isinstance(raw_nodes, Sequence)
        or isinstance(raw_nodes, (str, bytes))
        or not isinstance(raw_edges, Sequence)
        or isinstance(raw_edges, (str, bytes))
    ):
        raise ValueError("WG-LOCAL-NAV-READ: invalid graph values")
    edges: list[LocalMovementEdge] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping) or set(raw) != {
            "source",
            "target",
            "kind",
            "cost",
            "source_ids",
        }:
            raise ValueError("WG-LOCAL-NAV-READ: invalid edge shape")
        kind, cost, sources = raw["kind"], raw["cost"], raw["source_ids"]
        if (
            not isinstance(kind, str)
            or isinstance(cost, bool)
            or not isinstance(cost, int)
            or not isinstance(sources, Sequence)
            or isinstance(sources, (str, bytes))
            or any(not isinstance(item, str) for item in sources)
        ):
            raise ValueError("WG-LOCAL-NAV-READ: invalid edge values")
        edges.append(
            LocalMovementEdge(
                coordinate(raw["source"]),
                coordinate(raw["target"]),
                kind,
                cost,
                tuple(str(item) for item in sources),
            )
        )
    return LocalMovementGraph(
        version,
        tuple(coordinate(item) for item in raw_nodes),
        tuple(edges),
    )
