"""World-referenced story and graph generation plus deterministic validation."""

from __future__ import annotations

from ..domain.run_spec import derive_seed
from ..world.models import BibleV2
from ..world.views import WorldView
from ..worldgen.numeric import identity, stable_id
from .models import (
    ChoiceV2,
    GraphNodeV2,
    GraphV2,
    MediaIntent,
    StoryOpportunity,
    StoryScene,
    StoryV2,
)


def validate_route_transition(
    route: dict[str, object],
    source: str,
    target: str,
    region_cells: dict[str, set[int]],
) -> None:
    if {route.get("start_region"), route.get("end_region")} != {source, target}:
        raise ValueError("GRAPH-TRAVEL: route endpoints do not connect source and target")
    cells = route.get("cells")
    traversable = route.get("traversable_seasons")
    if (
        not isinstance(cells, tuple)
        or not cells
        or cells[0] not in region_cells[str(route["start_region"])]
        or cells[-1] not in region_cells[str(route["end_region"])]
    ):
        raise ValueError("GRAPH-TRAVEL: route geometry is outside declared endpoints")
    if (
        not isinstance(traversable, tuple)
        or len(traversable) != 4
        or not any(value is True for value in traversable)
    ):
        raise ValueError("GRAPH-TRAVEL: route has no traversable season")


def generate_story(
    world: WorldView,
    bible: BibleV2,
    opportunities: tuple[StoryOpportunity, ...],
    bible_hash: str,
    reconciliation_hash: str,
) -> StoryV2:
    if not opportunities:
        raise ValueError("STORY-OPPORTUNITY: no factual opportunities")
    scenes = tuple(
        StoryScene(
            stable_id(
                "scene", world.present_year, identity("opportunity_id", opportunity.opportunity_id)
            ),
            f"Pressure {index + 1}",
            f"The consequences of {opportunity.pressure} become unavoidable.",
            opportunity.location_ids[0],
            opportunity.participant_ids,
            opportunity.opportunity_id,
            tuple(
                dict.fromkeys(
                    opportunity.source_ids
                    + opportunity.participant_ids
                    + opportunity.location_ids
                    + opportunity.route_ids
                    + opportunity.person_ids
                    + opportunity.belief_ids
                    + opportunity.site_ids
                    + opportunity.local_containment_ids
                    + opportunity.revealable_fact_ids
                    + opportunity.answer_fact_ids
                    + opportunity.constraint_ids
                )
            ),
            world.present_year,
        )
        for index, opportunity in enumerate(opportunities)
    )
    return StoryV2(
        "2-pre1",
        bible.title,
        tuple(sorted(world.artifact_ids.values())),
        bible_hash,
        reconciliation_hash,
        scenes,
    )


def generate_graph(
    world: WorldView, story: StoryV2, opportunities: tuple[StoryOpportunity, ...]
) -> GraphV2:
    if any(scene.world_year != world.present_year for scene in story.scenes):
        raise ValueError("GRAPH-TEMPORAL: story scene year contradicts authoritative present")
    routes = {fact.fact_id: fact.value for fact in world.routes()}
    nodes: list[GraphNodeV2] = []
    seed = int(world.payload("world_index")["seed"])
    opportunity_by_id = {item.opportunity_id: item for item in opportunities}

    adjacency: dict[str, list[tuple[str, str]]] = {}
    for route_key, route in sorted(routes.items()):
        left, right = route["start_region"], route["end_region"]
        adjacency.setdefault(left, []).append((right, route_key))
        adjacency.setdefault(right, []).append((left, route_key))

    def shortest_path(source: str, target: str) -> list[str]:
        if source == target:
            return [source]
        frontier = [source]
        previous: dict[str, str | None] = {source: None}
        while frontier:
            current = frontier.pop(0)
            for neighbor, _ in sorted(adjacency.get(current, [])):
                if neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == target:
                    path = [target]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])  # type: ignore[arg-type]
                    return list(reversed(path))
                frontier.append(neighbor)
        raise ValueError(f"GRAPH-TRAVEL: no authoritative route path connects {source} to {target}")

    sequence: list[tuple[StoryScene, StoryOpportunity, str]] = []
    for scene in story.scenes:
        opportunity = opportunity_by_id[scene.opportunity_id]
        if not sequence:
            sequence.append((scene, opportunity, scene.location_id))
            continue
        for location in shortest_path(sequence[-1][2], scene.location_id)[1:]:
            sequence.append((scene, opportunity, location))
    while len(sequence) < 10:
        sequence.append(sequence[-1])
    # The penultimate decision branches to two terminal nodes. Keep the
    # alternate ending at that decision's authoritative location so the branch
    # never invents a direct route across multiple route-network hops.
    alternate_scene, alternate_opportunity, _ = sequence[-1]
    sequence[-1] = (alternate_scene, alternate_opportunity, sequence[-3][2])
    node_count = len(sequence)
    node_ids = tuple(
        stable_id(
            "node",
            seed,
            identity("sequence_position", index),
            identity("scene_id", item[0].scene_id),
            identity("location_id", item[2]),
        )
        for index, item in enumerate(sequence)
    )
    node_locations = tuple(item[2] for item in sequence)

    def route_between(source: str, target: str) -> str | None:
        if source == target:
            return None
        matches = sorted(
            route_id
            for route_id, route in routes.items()
            if {route["start_region"], route["end_region"]} == {source, target}
        )
        if not matches:
            raise ValueError(f"GRAPH-TRAVEL: no authoritative route connects {source} to {target}")
        return matches[0]

    def season_for(route_id: str | None, ordinal: int) -> int:
        if route_id is None:
            return ordinal % 4
        traversable = tuple(routes[route_id]["traversable_seasons"])
        for offset in range(4):
            season = (ordinal + offset) % 4
            if traversable[season] is True:
                return season
        raise ValueError("GRAPH-TRAVEL: route has no traversable season")

    flags: list[str] = []
    for index in range(node_count):
        scene, opportunity, node_location = sequence[index]
        node_id = node_ids[index]
        ending = (
            "bittersweet"
            if index == node_count - 2
            else "good"
            if index == node_count - 1
            else None
        )
        choices: list[ChoiceV2] = []
        if ending is None:
            target = node_ids[index + 1]
            flag = f"visited_{index + 1:03d}"
            flags.append(flag)
            route_id = route_between(node_location, node_locations[index + 1])
            target_location = node_locations[index + 1]
            choice_refs = tuple(
                dict.fromkeys(
                    scene.authoritative_refs
                    + (node_location, target_location)
                    + ((route_id,) if route_id else ())
                )
            )
            choices.append(
                ChoiceV2(
                    stable_id(
                        "choice",
                        seed,
                        identity("node_id", node_id),
                        identity("branch", "follow"),
                    ),
                    "Follow the documented pressure.",
                    target,
                    route_id,
                    (flag,),
                    (),
                    choice_refs,
                    world.present_year,
                    season_for(route_id, index),
                )
            )
            if index == node_count - 3:
                settlement_route = route_between(node_location, node_locations[-1])
                settlement_refs = tuple(
                    dict.fromkeys(
                        scene.authoritative_refs
                        + (node_location, node_locations[-1])
                        + ((settlement_route,) if settlement_route else ())
                    )
                )
                choices.append(
                    ChoiceV2(
                        stable_id(
                            "choice",
                            seed,
                            identity("node_id", node_id),
                            identity("branch", "settlement"),
                        ),
                        "Accept the costly settlement.",
                        node_ids[-1],
                        settlement_route,
                        ("accepted_settlement",),
                        (flag,),
                        settlement_refs,
                        world.present_year,
                        season_for(settlement_route, index),
                    )
                )
                flags.append("accepted_settlement")
        image_seed = derive_seed(seed, "media", node_id, "image")
        music_seed = derive_seed(seed, "media", node_id, "music")
        node_refs = tuple(
            dict.fromkeys(
                scene.authoritative_refs
                + (node_location,)
                + tuple(ref for choice in choices for ref in choice.authoritative_refs)
            )
        )
        intent = MediaIntent(
            f"Mature dark fantasy at {node_location}; {scene.summary}",
            "tense_resolve" if ending is None else ending,
            72 + index % 24,
            image_seed,
            music_seed,
            node_refs,
        )
        nodes.append(
            GraphNodeV2(
                node_id,
                scene.scene_id,
                node_location,
                scene.participant_ids,
                scene.opportunity_id,
                node_refs,
                scene.summary,
                tuple(choices),
                intent,
                ending,
                world.present_year,
            )
        )
    graph = GraphV2("2-pre1", node_ids[0], tuple(sorted(set(flags))), tuple(nodes))
    validate_graph(world, graph, opportunities)
    return graph


def validate_graph(
    world: WorldView, graph: GraphV2, opportunities: tuple[StoryOpportunity, ...]
) -> None:
    nodes = {node.node_id: node for node in graph.nodes}
    if graph.starting_node not in nodes:
        raise ValueError("GRAPH-START: unknown starting node")
    region_facts = {fact.fact_id: fact.value for fact in world.regions()}
    region_ids = set(region_facts)
    region_cells = {region_id: set(value["cells"]) for region_id, value in region_facts.items()}
    civilizations = {fact.fact_id: fact.value for fact in world.civilizations()}
    civ_ids = set(civilizations)
    people = {fact.fact_id: fact.value for fact in world.people()}
    opportunity_ids = {item.opportunity_id for item in opportunities}
    opportunity_by_id = {item.opportunity_id: item for item in opportunities}
    route_facts = {fact.fact_id: fact.value for fact in world.routes()}
    reachable = {graph.starting_node}
    frontier = [graph.starting_node]
    ending_count = 0
    while frontier:
        current = nodes[frontier.pop(0)]
        if current.location_id not in region_ids or current.opportunity_id not in opportunity_ids:
            raise ValueError("GRAPH-WORLD-REF: invalid node world reference")
        if current.world_year != world.present_year:
            raise ValueError("GRAPH-TEMPORAL: node year must equal authoritative present year")
        opportunity = opportunity_by_id[current.opportunity_id]
        required_evidence = set(
            opportunity.revealable_fact_ids
            + opportunity.answer_fact_ids
            + opportunity.local_containment_ids
            + opportunity.constraint_ids
            + opportunity.person_ids
            + opportunity.belief_ids
            + opportunity.site_ids
        )
        if not required_evidence <= set(current.authoritative_refs):
            raise ValueError("GRAPH-OPPORTUNITY-EVIDENCE: projected evidence is missing")
        if current.media_intent.authoritative_refs != current.authoritative_refs:
            raise ValueError("GRAPH-MEDIA-AUTHORITY: media intent lost node authority")
        if any(
            participant not in civ_ids or not civilizations[participant].get("active", False)
            for participant in current.participant_ids
        ):
            raise ValueError("GRAPH-ENTITY-STATE: participant is not present")
        for _, person_id in opportunity.role_assignments:
            person = people.get(person_id)
            if (
                person is None
                or int(person["created_year"]) > current.world_year
                or (
                    person["status"] == "dead"
                    and person["status_year"] is not None
                    and int(person["status_year"]) <= current.world_year
                )
            ):
                raise ValueError("GRAPH-ENTITY-STATE: assigned person is unavailable")
        if current.ending is not None:
            ending_count += 1
            if current.choices:
                raise ValueError("GRAPH-ENDING: ending cannot have choices")
        for choice in current.choices:
            if choice.target_node not in nodes:
                raise ValueError("GRAPH-TARGET: unknown target")
            target_node = nodes[choice.target_node]
            target_location = target_node.location_id
            if (
                choice.transition_year != current.world_year
                or target_node.world_year != choice.transition_year
                or not 0 <= choice.season < 4
            ):
                raise ValueError("GRAPH-TEMPORAL: choice time does not match both endpoints")
            required_choice_refs = {current.location_id, target_location}
            if choice.route_id is not None:
                required_choice_refs.add(choice.route_id)
            if current.location_id == target_location:
                if choice.route_id is not None:
                    raise ValueError("GRAPH-TRAVEL: same-location choice must not cite a route")
            else:
                if choice.route_id is None:
                    raise ValueError(
                        "GRAPH-TRAVEL: cross-location choice requires an authoritative route"
                    )
                route = route_facts.get(choice.route_id)
                if route is None:
                    raise ValueError("GRAPH-TRAVEL: route ID is stale or unknown")
                validate_route_transition(route, current.location_id, target_location, region_cells)
                traversable = route["traversable_seasons"]
                seasonal_cells = route["seasonal_cells"]
                if (
                    traversable[choice.season] is not True
                    or not seasonal_cells[choice.season]
                    or seasonal_cells[choice.season][0]
                    not in region_cells[str(route["start_region"])]
                    or seasonal_cells[choice.season][-1]
                    not in region_cells[str(route["end_region"])]
                ):
                    raise ValueError("GRAPH-TRAVEL: selected season is closed or loses an endpoint")
            if not required_choice_refs <= set(choice.authoritative_refs) or not set(
                choice.authoritative_refs
            ) <= set(current.authoritative_refs):
                raise ValueError(
                    "GRAPH-CHOICE-AUTHORITY: choice authority is incomplete or invented"
                )
            for required in choice.requires_flags:
                if required not in graph.flags:
                    raise ValueError("GRAPH-FLAG: unknown required flag")
            if choice.target_node not in reachable:
                reachable.add(choice.target_node)
                frontier.append(choice.target_node)
    if set(nodes) != reachable:
        raise ValueError("GRAPH-REACHABILITY: unreachable nodes")
    if ending_count < 2:
        raise ValueError("GRAPH-ENDINGS: at least two endings required")
