"""WG-LOCAL-005 legal movement graph foundation evidence."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_conditionals import ConditionalFeatureSpec
from src.worldgen.local_maps import generate_local_maps
from src.worldgen.local_navigation import (
    MOVEMENT_COSTS,
    LocalPathNotFound,
    MacroRouteTraversal,
    build_movement_graph,
    find_hierarchical_path,
    find_local_path,
    movement_graph_from_mapping,
    validate_movement_graph,
    verified_macro_route,
)


@pytest.fixture(scope="module")
def generated_local_maps(phase4_world):
    return generate_local_maps(WorldView(phase4_world))


def test_generated_graph_has_canonical_bidirectional_legal_edges(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        assert local.movement_graph is not None
        graph = local.movement_graph
        assert graph.nodes == tuple(sorted(set(graph.nodes)))
        assert graph.edges == tuple(sorted(set(graph.edges)))
        assert {"walk", "door", "ramp", "stairs", "climb"} <= {edge.kind for edge in graph.edges}
        edges = {(edge.source, edge.target, edge.kind) for edge in graph.edges}
        assert all(
            (edge.target, edge.source, edge.kind) in edges
            and edge.cost == MOVEMENT_COSTS[edge.kind]
            for edge in graph.edges
        )
        validate_movement_graph(local.features, graph)


def test_bridge_edges_use_the_frozen_bridge_cost() -> None:
    feature = ConditionalFeatureSpec(
        "bridge", "bridge", ((4, 5, 2), (5, 5, 2)), ("src-route", "src-river")
    )
    graph = build_movement_graph((feature,))
    assert len(graph.edges) == 2
    assert all(
        edge.kind == "bridge" and edge.cost == MOVEMENT_COSTS["bridge"] for edge in graph.edges
    )


@pytest.mark.parametrize("mutation", ["cost", "geometry", "missing", "order"])
def test_movement_validator_rejects_forged_graph(generated_local_maps, mutation: str) -> None:
    local = generated_local_maps[0]
    assert local.movement_graph is not None
    graph = local.movement_graph
    edges = list(graph.edges)
    if mutation == "cost":
        edges[0] = replace(edges[0], cost=999)
    elif mutation == "geometry":
        edges[0] = replace(edges[0], target=(999, 999, 999))
    elif mutation == "missing":
        edges.pop()
    else:
        edges[0], edges[-1] = edges[-1], edges[0]
    with pytest.raises(ValueError, match="WG-LOCAL-NAV"):
        validate_movement_graph(local.features, replace(graph, edges=tuple(edges)))


def test_movement_reader_is_strict(generated_local_maps) -> None:
    graph = generated_local_maps[0].movement_graph
    assert graph is not None
    payload = asdict(graph)
    assert movement_graph_from_mapping(payload) == graph
    with pytest.raises(ValueError, match="NAV-READ"):
        movement_graph_from_mapping({**payload, "invented": True})
    bad_edge = {**payload["edges"][0], "cost": False}
    with pytest.raises(ValueError, match="NAV-READ"):
        movement_graph_from_mapping({**payload, "edges": (bad_edge, *payload["edges"][1:])})


def test_astar_finds_canonical_generated_street_path(generated_local_maps) -> None:
    local = generated_local_maps[0]
    assert local.movement_graph is not None
    road = next(feature for feature in local.features if feature.kind == "road")
    result = find_local_path(local.movement_graph, road.cells[0], road.cells[-1])
    assert result.path == road.cells
    assert result.cost == (len(road.cells) - 1) * MOVEMENT_COSTS["walk"]
    assert result.visited_nodes <= len(local.movement_graph.nodes)


def test_astar_uses_lexicographic_equal_cost_tie_and_is_order_independent() -> None:
    start, goal = (0, 0, 0), (1, 1, 0)
    upper = ConditionalFeatureSpec("upper", "road", (start, (1, 0, 0), goal), ("src",))
    lower = ConditionalFeatureSpec("lower", "road", (start, (0, 1, 0), goal), ("src",))
    forward = build_movement_graph((upper, lower))
    reverse = build_movement_graph((lower, upper))
    expected = (start, (0, 1, 0), goal)
    assert find_local_path(forward, start, goal).path == expected
    assert find_local_path(reverse, start, goal) == find_local_path(forward, start, goal)


def test_astar_ramp_heuristic_remains_admissible() -> None:
    start, goal = (2, 2, 2), (3, 2, 3)
    graph = build_movement_graph((ConditionalFeatureSpec("ramp", "ramp", (start, goal), ("src",)),))
    result = find_local_path(graph, start, goal)
    assert result.path == (start, goal)
    assert result.cost == MOVEMENT_COSTS["ramp"]


def test_astar_has_stable_endpoint_and_unreachable_diagnostics() -> None:
    first = ConditionalFeatureSpec("first", "road", ((0, 0, 0), (1, 0, 0)), ("src",))
    second = ConditionalFeatureSpec("second", "road", ((5, 5, 0), (6, 5, 0)), ("src",))
    graph = build_movement_graph((first, second))
    with pytest.raises(LocalPathNotFound) as captured:
        find_local_path(graph, (0, 0, 0), (6, 5, 0))
    assert captured.value.reachable_nodes == 2
    assert str(captured.value) == ("WG-LOCAL-PATH-NOT-FOUND: (0, 0, 0)->(6, 5, 0); reachable=2")
    with pytest.raises(ValueError, match="PATH-ENDPOINT"):
        find_local_path(graph, (99, 99, 99), (6, 5, 0))


def _hierarchy_fixture():
    route_id = "route-1"
    source_features = (
        ConditionalFeatureSpec("source-road", "road", ((1, 1, 0), (2, 1, 0), (3, 1, 0)), ("src",)),
        ConditionalFeatureSpec(
            "source-anchor",
            "route_connection",
            ((2, 1, 0), (3, 1, 0)),
            ("routes-artifact", route_id),
        ),
    )
    destination_features = (
        ConditionalFeatureSpec(
            "destination-anchor",
            "route_connection",
            ((1, 1, 0), (0, 1, 0)),
            ("routes-artifact", route_id),
        ),
        ConditionalFeatureSpec(
            "destination-road",
            "road",
            ((0, 1, 0), (1, 1, 0), (2, 1, 0)),
            ("src",),
        ),
    )
    route = MacroRouteTraversal(
        route_id,
        "region-a",
        "region-b",
        (10, 11, 12),
        700,
        ("routes-artifact",),
    )
    return source_features, destination_features, route


def test_hierarchical_path_composes_local_macro_local_segments() -> None:
    source_features, destination_features, route = _hierarchy_fixture()
    result = find_hierarchical_path(
        build_movement_graph(source_features),
        source_features,
        "region-a",
        (1, 1, 0),
        build_movement_graph(destination_features),
        destination_features,
        "region-b",
        (2, 1, 0),
        route,
    )
    assert result.route_id == route.route_id
    assert result.source_local.path == ((1, 1, 0), (2, 1, 0), (3, 1, 0))
    assert result.macro_cells == route.cells
    assert result.destination_local.path == ((0, 1, 0), (1, 1, 0), (2, 1, 0))
    assert result.total_cost == (
        result.source_local.cost + route.cost + result.destination_local.cost
    )


def test_hierarchical_path_reverses_authoritative_macro_geometry() -> None:
    source_features, destination_features, route = _hierarchy_fixture()
    result = find_hierarchical_path(
        build_movement_graph(destination_features),
        destination_features,
        "region-b",
        (2, 1, 0),
        build_movement_graph(source_features),
        source_features,
        "region-a",
        (1, 1, 0),
        route,
    )
    assert result.macro_cells == tuple(reversed(route.cells))


def test_hierarchical_path_rejects_wrong_route_and_missing_anchor() -> None:
    source_features, destination_features, route = _hierarchy_fixture()
    source_graph = build_movement_graph(source_features)
    destination_graph = build_movement_graph(destination_features)
    with pytest.raises(ValueError, match="HIERARCHY-ROUTE"):
        find_hierarchical_path(
            source_graph,
            source_features,
            "unrelated",
            (1, 1, 0),
            destination_graph,
            destination_features,
            "region-b",
            (2, 1, 0),
            route,
        )
    missing = tuple(
        feature for feature in destination_features if feature.kind != "route_connection"
    )
    with pytest.raises(ValueError, match="HIERARCHY-ANCHOR"):
        find_hierarchical_path(
            source_graph,
            source_features,
            "region-a",
            (1, 1, 0),
            build_movement_graph(missing),
            missing,
            "region-b",
            (2, 1, 0),
            route,
        )


def test_macro_segment_is_loaded_through_verified_world_reader(phase4_world) -> None:
    world = WorldView(phase4_world)
    fact = world.routes()[0]
    route = verified_macro_route(world, fact.fact_id)
    assert route.route_id == fact.fact_id
    assert route.cells == tuple(fact.value["cells"])
    assert route.cost == fact.value["terrain_cost"]
    assert route.source_ids == fact.source_ids
    with pytest.raises(ValueError, match="unknown route"):
        verified_macro_route(world, "forged-route")
