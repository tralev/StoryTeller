"""Complete source-covered GM knowledge index and spoiler eligibility."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict

from ..world.models import BibleV2
from ..world.views import WorldFact, WorldView
from ..worldgen.artifacts import canonical_json
from ..worldgen.local_maps import LocalSiteMap
from ..worldgen.numeric import identity as id_component, stable_id
from .models import GraphV2, KnowledgeEntry, StoryOpportunity, StoryV2


def normalize_knowledge(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def revealed(entry: KnowledgeEntry, visited: frozenset[str]) -> bool:
    return not entry.reveal_after_nodes or frozenset(entry.reveal_after_nodes).issubset(visited)


def build_knowledge_index(world: WorldView, bible: BibleV2, story: StoryV2, graph: GraphV2,
                          opportunities: tuple[StoryOpportunity, ...],
                          local_maps: tuple[LocalSiteMap, ...]) -> tuple[KnowledgeEntry, ...]:
    entries: list[KnowledgeEntry] = []
    external_to_entry: dict[str, str] = {}
    node_ids = tuple(node.node_id for node in graph.nodes)
    reveal_by_ref: dict[str, str] = {}
    for node in graph.nodes:
        for ref in node.authoritative_refs:
            reveal_by_ref.setdefault(ref, node.node_id)

    def add(kind: str, identity: str, value: object, sources: tuple[str, ...],
            outgoing: tuple[str, ...] = (), reveal: tuple[str, ...] = ()) -> None:
        text = canonical_json(value).decode("utf-8")
        entry_id = stable_id(
            "knowledge", world.present_year, id_component("kind", kind),
            id_component("source_identity", identity),
        )
        external_to_entry[identity] = entry_id
        entries.append(KnowledgeEntry(entry_id, kind,
                                      normalize_knowledge(text), tuple(sorted(set(sources))), (),
                                      tuple(sorted(set(outgoing))), reveal))

    # Artifact sentinels prove that even dense/unused grids remain represented.
    for kind, artifact_id in sorted(world.artifact_ids.items()):
        add("artifact", kind, {"kind": kind, "artifact_id": artifact_id}, (artifact_id,))
    fact_groups = (world.regions(), world.routes(), world.sites(), world.settlements(),
                   world.civilizations(), world.cohorts(), world.events())
    for group in fact_groups:
        for fact in group:
            reveal_node = reveal_by_ref.get(fact.fact_id)
            # Historical facts not selected by the narrative stay hidden until
            # the graph has been fully traversed; they are never omitted.
            if fact.kind == "event" and reveal_node is None:
                reveal_node = node_ids[-1]
            add(fact.kind, fact.fact_id, fact.value, fact.source_ids,
                tuple(str(value) for value in fact.value.values() if isinstance(value, str)),
                (reveal_node,) if reveal_node else ())
    add("ecology", "world", world.ecology().value, world.ecology().source_ids)
    add("registries", "world", world.registries().value, world.registries().source_ids)
    add("identities", "world", world.identities().value, world.identities().source_ids)
    for claim in bible.local_entities:
        add("bible_local", claim.entity_id, asdict(claim), claim.authoritative_refs,
            (claim.contained_by,), (reveal_by_ref.get(claim.contained_by, node_ids[0]),))
    for scene in story.scenes:
        add("story_scene", scene.scene_id, asdict(scene), scene.authoritative_refs,
            (scene.location_id,) + scene.participant_ids,
            (reveal_by_ref.get(scene.scene_id, node_ids[0]),))
    for node in graph.nodes:
        add("graph_node", node.node_id, asdict(node), node.authoritative_refs,
            tuple(choice.target_node for choice in node.choices), (node.node_id,))
    for opportunity in opportunities:
        add("opportunity", opportunity.opportunity_id, asdict(opportunity), opportunity.source_ids,
            opportunity.participant_ids + opportunity.location_ids + opportunity.route_ids,
            (reveal_by_ref.get(opportunity.opportunity_id, node_ids[0]),))
    for local in local_maps:
        sources = tuple(sorted({source for feature in local.features for source in feature.source_ids}))
        add("local_map", local.site_id, asdict(local), sources, (local.site_id,),
            (reveal_by_ref.get(local.site_id, node_ids[0]),))

    # Build incoming references without changing entry identities.
    ids = {entry.entry_id for entry in entries}
    incoming: dict[str, set[str]] = {entry.entry_id: set() for entry in entries}
    for entry in entries:
        for target in entry.outgoing_refs:
            target_entry = external_to_entry.get(target)
            if target_entry in ids:
                incoming[target_entry].add(entry.entry_id)
    return tuple(KnowledgeEntry(entry.entry_id, entry.kind, entry.normalized_text, entry.source_ids,
                                tuple(sorted(incoming[entry.entry_id])),
                                tuple(sorted(external_to_entry[target] for target in entry.outgoing_refs
                                             if target in external_to_entry)),
                                entry.reveal_after_nodes)
                 for entry in sorted(entries, key=lambda item: item.entry_id))
