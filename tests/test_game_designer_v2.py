import json
from dataclasses import replace

import pytest

from src.narrative.pipeline import _graph_from_dict
from src.narrative.models import StoryOpportunity
from src.narrative.story_graph import validate_graph, validate_route_transition
from src.world.views import WorldView


def _opportunities(path):
    return tuple(StoryOpportunity(item["opportunity_id"], item["pressure"], tuple(item["participant_ids"]),
                                  tuple(item["location_ids"]), tuple(item["route_ids"]),
                                  tuple(item["source_ids"]), tuple(item["revealable_fact_ids"]))
                 for item in json.loads(path.read_text()))


def test_graph_topology_flags_endings_and_world_routes(phase5_project):
    world_path, _, phase5 = phase5_project
    graph = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    opportunities = _opportunities(phase5 / "opportunities.json")
    validate_graph(WorldView(world_path), graph, opportunities)
    assert sum(node.ending is not None for node in graph.nodes) == 2
    assert all(choice.target_node for node in graph.nodes for choice in node.choices)
    assert all(node.media_intent.image_seed != node.media_intent.music_seed for node in graph.nodes)


def test_impossible_travel_and_unreachable_nodes_are_rejected(phase5_project):
    world_path, _, phase5 = phase5_project
    graph = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    opportunities = _opportunities(phase5 / "opportunities.json")
    first = graph.nodes[0]
    bad_choice = replace(first.choices[0], route_id="route_unknown")
    bad = replace(graph, nodes=(replace(first, choices=(bad_choice,)) ,) + graph.nodes[1:])
    with pytest.raises(ValueError, match="GRAPH-TRAVEL"):
        validate_graph(WorldView(world_path), bad, opportunities)


def test_cross_location_choice_requires_route(phase5_project):
    world_path, _, phase5 = phase5_project
    graph = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    opportunities = _opportunities(phase5 / "opportunities.json")
    by_id = {node.node_id: node for node in graph.nodes}
    source = next(node for node in graph.nodes if node.choices
                  and by_id[node.choices[0].target_node].location_id != node.location_id)
    choice = replace(source.choices[0], route_id=None)
    bad = replace(graph, nodes=tuple(replace(node, choices=(choice,) + node.choices[1:])
                                     if node.node_id == source.node_id else node
                                     for node in graph.nodes))
    with pytest.raises(ValueError, match="cross-location choice requires"):
        validate_graph(WorldView(world_path), bad, opportunities)


def test_route_must_connect_both_transition_endpoints(phase5_project):
    world_path, _, phase5 = phase5_project
    world = WorldView(world_path)
    graph = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    opportunities = _opportunities(phase5 / "opportunities.json")
    source = next(node for node in graph.nodes if node.choices and node.choices[0].route_id is not None)
    target = next(node for node in graph.nodes if node.node_id == source.choices[0].target_node)
    wrong_route = next(fact.fact_id for fact in world.routes()
                       if {fact.value["start_region"], fact.value["end_region"]}
                       != {source.location_id, target.location_id})
    choice = replace(source.choices[0], route_id=wrong_route)
    bad = replace(graph, nodes=tuple(replace(node, choices=(choice,) + node.choices[1:])
                                     if node.node_id == source.node_id else node
                                     for node in graph.nodes))
    with pytest.raises(ValueError, match="route endpoints do not connect"):
        validate_graph(world, bad, opportunities)


def test_same_location_choice_rejects_unnecessary_route(phase5_project):
    world_path, _, phase5 = phase5_project
    world = WorldView(world_path)
    graph = _graph_from_dict(json.loads((phase5 / "graph.json").read_text()))
    opportunities = _opportunities(phase5 / "opportunities.json")
    by_id = {node.node_id: node for node in graph.nodes}
    source = next(node for node in graph.nodes if node.choices
                  and by_id[node.choices[0].target_node].location_id == node.location_id)
    choice = replace(source.choices[0], route_id=world.routes()[0].fact_id)
    bad = replace(graph, nodes=tuple(replace(node, choices=(choice,) + node.choices[1:])
                                     if node.node_id == source.node_id else node
                                     for node in graph.nodes))
    with pytest.raises(ValueError, match="same-location choice"):
        validate_graph(world, bad, opportunities)


def test_narrative_route_rejects_geometry_outside_regions_and_closed_seasons(phase5_project):
    world_path, _, _ = phase5_project
    world = WorldView(world_path)
    route = dict(world.routes()[0].value)
    regions = {fact.fact_id: set(fact.value["cells"]) for fact in world.regions()}
    source, target = str(route["start_region"]), str(route["end_region"])
    outsider = next(cell for region_id, cells in regions.items() if region_id != source
                    for cell in cells if cell not in regions[source])
    bad_geometry = dict(route); bad_geometry["cells"] = (outsider, *route["cells"][1:])
    with pytest.raises(ValueError, match="geometry is outside"):
        validate_route_transition(bad_geometry, source, target, regions)
    closed = dict(route); closed["traversable_seasons"] = (False, False, False, False)
    with pytest.raises(ValueError, match="no traversable season"):
        validate_route_transition(closed, source, target, regions)
