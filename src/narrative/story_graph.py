"""World-referenced story and graph generation plus deterministic validation."""
from __future__ import annotations

import hashlib

from ..domain.run_spec import derive_seed
from ..world.models import BibleV2
from ..world.views import WorldView
from ..worldgen.artifacts import canonical_json
from .models import (ChoiceV2, GraphNodeV2, GraphV2, MediaIntent, StoryOpportunity,
                     StoryScene, StoryV2)


def generate_story(world: WorldView, bible: BibleV2, opportunities: tuple[StoryOpportunity, ...],
                   bible_hash: str, reconciliation_hash: str) -> StoryV2:
    if not opportunities:
        raise ValueError("STORY-OPPORTUNITY: no factual opportunities")
    scenes = tuple(StoryScene(
        f"scene_{index + 1:03d}", f"Pressure {index + 1}",
        f"The consequences of {opportunity.pressure} become unavoidable.",
        opportunity.location_ids[0], opportunity.participant_ids,
        opportunity.opportunity_id,
        tuple(dict.fromkeys(opportunity.source_ids + opportunity.participant_ids
                            + opportunity.location_ids + opportunity.route_ids)),
    ) for index, opportunity in enumerate(opportunities))
    return StoryV2("2-pre1", bible.title, tuple(sorted(world.artifact_ids.values())),
                   bible_hash, reconciliation_hash, scenes)


def generate_graph(world: WorldView, story: StoryV2,
                   opportunities: tuple[StoryOpportunity, ...]) -> GraphV2:
    routes = {fact.fact_id: fact.value for fact in world.routes()}
    node_count = max(10, len(story.scenes) + 2)
    nodes: list[GraphNodeV2] = []
    flags: list[str] = []
    for index in range(node_count):
        scene = story.scenes[min(index, len(story.scenes) - 1)]
        opportunity = opportunities[min(index, len(opportunities) - 1)]
        node_id = f"node_{index + 1:03d}"
        ending = "bittersweet" if index == node_count - 2 else "good" if index == node_count - 1 else None
        choices: list[ChoiceV2] = []
        if ending is None:
            target = f"node_{index + 2:03d}"
            flag = f"visited_{index + 1:03d}"
            flags.append(flag)
            route_id = opportunity.route_ids[0] if opportunity.route_ids else None
            if route_id is not None and route_id not in routes:
                raise ValueError("GRAPH-ROUTE: opportunity references unknown route")
            choices.append(ChoiceV2(f"choice_{index + 1:03d}_a", "Follow the documented pressure.",
                                    target, route_id, (flag,), ()))
            if index == node_count - 3:
                choices.append(ChoiceV2(f"choice_{index + 1:03d}_b", "Accept the costly settlement.",
                                        f"node_{node_count:03d}", route_id,
                                        ("accepted_settlement",), (flag,)))
                flags.append("accepted_settlement")
        image_seed = derive_seed(int(world.payload("world_index")["seed"]), "media.image", node_id)
        music_seed = derive_seed(int(world.payload("world_index")["seed"]), "media.music", node_id)
        intent = MediaIntent(f"Mature dark fantasy at {scene.location_id}; {scene.summary}",
                             "tense_resolve" if ending is None else ending, 72 + index % 24,
                             image_seed, music_seed)
        nodes.append(GraphNodeV2(node_id, scene.scene_id, scene.location_id, scene.participant_ids,
                                 scene.opportunity_id, scene.authoritative_refs,
                                 scene.summary, tuple(choices), intent, ending))
    graph = GraphV2("2-pre1", "node_001", tuple(sorted(set(flags))), tuple(nodes))
    validate_graph(world, graph, opportunities)
    return graph


def validate_graph(world: WorldView, graph: GraphV2,
                   opportunities: tuple[StoryOpportunity, ...]) -> None:
    nodes = {node.node_id: node for node in graph.nodes}
    if graph.starting_node not in nodes:
        raise ValueError("GRAPH-START: unknown starting node")
    region_ids = {fact.fact_id for fact in world.regions()}
    civ_ids = {fact.fact_id for fact in world.civilizations()}
    opportunity_ids = {item.opportunity_id for item in opportunities}
    route_facts = {fact.fact_id: fact.value for fact in world.routes()}
    reachable = {graph.starting_node}
    frontier = [graph.starting_node]
    ending_count = 0
    while frontier:
        current = nodes[frontier.pop(0)]
        if current.location_id not in region_ids or current.opportunity_id not in opportunity_ids:
            raise ValueError("GRAPH-WORLD-REF: invalid node world reference")
        if any(participant not in civ_ids for participant in current.participant_ids):
            raise ValueError("GRAPH-ENTITY-STATE: participant is not present")
        if current.ending is not None:
            ending_count += 1
            if current.choices:
                raise ValueError("GRAPH-ENDING: ending cannot have choices")
        for choice in current.choices:
            if choice.target_node not in nodes:
                raise ValueError("GRAPH-TARGET: unknown target")
            if choice.route_id is not None:
                route = route_facts.get(choice.route_id)
                if route is None or current.location_id not in (route["start_region"], route["end_region"]):
                    raise ValueError("GRAPH-TRAVEL: route does not contain source location")
            for required in choice.requires_flags:
                if required not in graph.flags:
                    raise ValueError("GRAPH-FLAG: unknown required flag")
            if choice.target_node not in reachable:
                reachable.add(choice.target_node); frontier.append(choice.target_node)
    if set(nodes) != reachable:
        raise ValueError("GRAPH-REACHABILITY: unreachable nodes")
    if ending_count < 2:
        raise ValueError("GRAPH-ENDINGS: at least two endings required")
