import json
from dataclasses import replace

import pytest

from src.narrative.pipeline import _graph_from_dict
from src.narrative.models import StoryOpportunity
from src.narrative.story_graph import validate_graph
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
