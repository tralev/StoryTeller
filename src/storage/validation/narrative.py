"""Cross-file narrative, score, and Game Master package validation."""

import hashlib
import zipfile
from collections.abc import Mapping
from typing import Any

from ...narrative.knowledge_source import MAX_NORMALIZED_TEXT_BYTES
from ...narrative.media import validate_midi, validate_score
from ...narrative.pipeline import _score_from_dict
from .common import JsonLoader, PackageV2Error
from .identity import PackageIdentityIndex


def validate_structured_scores(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    identities: PackageIdentityIndex,
    load_json: JsonLoader,
) -> None:
    mappings = (
        ("SCORE-SOURCES", "PACKAGE_SCORE_REFERENCES"),
        ("BEAT-", "PACKAGE_SCORE_BEAT_ARITHMETIC"),
        ("SCORE-EVENTS", "PACKAGE_SCORE_EVENT_ORDER"),
        ("SCORE-MARKERS", "PACKAGE_SCORE_MARKER_ORDER"),
        ("SCORE-PROGRAM", "PACKAGE_SCORE_TRACK_PROGRAM"),
        ("SCORE-EVENT", "PACKAGE_SCORE_EVENT_SHAPE"),
    )
    for node, assets in manifest["node_assets"].items():
        path = assets["score"]
        raw = load_json(archive.read(path), path)
        try:
            score = _score_from_dict(raw)
            validate_score(score)
        except (KeyError, TypeError, ValueError) as error:
            message = str(error)
            code = next(
                (code for prefix, code in mappings if prefix in message),
                "PACKAGE_SCORE_EVENT_SHAPE",
            )
            raise PackageV2Error(code, message, path) from error
        if (
            score.node_id != node
            or not score.source_ids
            or any(source not in identities.ids for source in score.source_ids)
        ):
            raise PackageV2Error("PACKAGE_SCORE_REFERENCES", "score references differ", path)
        if score.expected_midi_sha256 != hashlib.sha256(archive.read(assets["midi"])).hexdigest():
            raise PackageV2Error("PACKAGE_SCORE_MIDI_HASH", "score MIDI hash differs", path)
        try:
            validate_midi(archive.read(assets["midi"]), score)
        except ValueError as error:
            raise PackageV2Error("PACKAGE_MIDI_PROFILE", str(error), assets["midi"]) from error


def validate_gm_coverage(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    graph: Mapping[str, Any],
    identities: PackageIdentityIndex,
    load_json: JsonLoader,
) -> None:
    gm = load_json(archive.read("narrative/gm_index.json"), "narrative/gm_index.json")
    reconciliation = load_json(
        archive.read("narrative/reconciliation.json"), "narrative/reconciliation.json"
    )
    entries = gm.get("entries") if isinstance(gm, dict) else None
    if not isinstance(entries, list) or not entries:
        raise PackageV2Error("PACKAGE_GM_COVERAGE", "GM index is empty")
    graph_nodes = {node.get("node_id") for node in graph.get("nodes", [])}
    sources: set[str] = set()
    for entry in entries:
        entry_sources = entry.get("source_ids") if isinstance(entry, dict) else None
        reveal = entry.get("reveal_after_nodes") if isinstance(entry, dict) else None
        if (
            not isinstance(entry_sources, list)
            or not entry_sources
            or any(source not in identities.ids for source in entry_sources)
            or not isinstance(reveal, list)
            or any(node not in graph_nodes for node in reveal)
        ):
            raise PackageV2Error("PACKAGE_GM_COVERAGE", "GM references do not resolve")
        sources.update(entry_sources)
    expected_raw = reconciliation.get("world_artifact_ids", {})
    expected = set(expected_raw.values()) if isinstance(expected_raw, dict) else set(expected_raw)
    if not expected or not expected <= sources:
        raise PackageV2Error("PACKAGE_GM_COVERAGE", "authoritative world coverage is incomplete")
    index_path = "narrative/knowledge/index.json"
    if index_path not in archive.namelist():
        # Migration window: packages produced before the bounded-reader slice
        # remain valid until all three native readers enforce the new members.
        return
    index = load_json(archive.read(index_path), index_path)
    locators = index.get("entries") if isinstance(index, dict) else None
    if not isinstance(locators, list):
        raise PackageV2Error("PACKAGE_KNOWLEDGE_INDEX", "knowledge locators must be an array")
    entry_by_id = {entry["entry_id"]: entry for entry in entries if isinstance(entry, dict)}
    locator_ids: list[str] = []
    for locator in locators:
        if not isinstance(locator, dict):
            raise PackageV2Error("PACKAGE_KNOWLEDGE_INDEX", "invalid knowledge locator")
        entry_id = locator.get("entry_id")
        path = locator.get("path")
        tokens = locator.get("tokens")
        reveal = locator.get("reveal_after_nodes")
        expected_path = f"chunks/{entry_id}.json"
        if (
            not isinstance(entry_id, str)
            or entry_id not in entry_by_id
            or path != expected_path
            or not isinstance(tokens, list)
            or any(not isinstance(token, str) or not token for token in tokens)
            or tokens != sorted(set(tokens))
            or reveal != entry_by_id[entry_id].get("reveal_after_nodes")
        ):
            raise PackageV2Error("PACKAGE_KNOWLEDGE_INDEX", "invalid knowledge locator")
        archive_path = f"narrative/knowledge/{path}"
        if archive_path not in archive.namelist():
            raise PackageV2Error(
                "PACKAGE_KNOWLEDGE_CHUNK", "knowledge chunk is missing", archive_path
            )
        payload = archive.read(archive_path)
        chunk = load_json(payload, archive_path)
        legacy = entry_by_id[entry_id]
        comparable_chunk = dict(chunk) if isinstance(chunk, dict) else {}
        comparable_legacy = dict(legacy)
        chunk_text = comparable_chunk.pop("normalized_text", None)
        legacy_text = comparable_legacy.pop("normalized_text", None)
        if (
            locator.get("size_bytes") != len(payload)
            or locator.get("sha256") != hashlib.sha256(payload).hexdigest()
            or comparable_chunk != comparable_legacy
            or not isinstance(chunk_text, str)
            or not isinstance(legacy_text, str)
            or len(chunk_text.encode("utf-8")) > MAX_NORMALIZED_TEXT_BYTES
            or not legacy_text.startswith(chunk_text)
        ):
            raise PackageV2Error(
                "PACKAGE_KNOWLEDGE_CHUNK", "knowledge chunk identity differs", archive_path
            )
        locator_ids.append(entry_id)
    if locator_ids != sorted(entry_by_id) or len(locator_ids) != len(set(locator_ids)):
        raise PackageV2Error(
            "PACKAGE_KNOWLEDGE_COVERAGE", "knowledge locator coverage must be exact"
        )


def validate_story_graph_references(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    graph: Mapping[str, Any],
    identities: PackageIdentityIndex,
    load_json: JsonLoader,
) -> None:
    story = load_json(archive.read("narrative/story.json"), "narrative/story.json")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "graph nodes are missing")
    node_by_id = {node.get("node_id"): node for node in nodes if isinstance(node, dict)}
    if (
        len(node_by_id) != len(nodes)
        or graph.get("starting_node") not in node_by_id
        or graph.get("starting_node") != manifest.get("entry_node")
        or set(node_by_id) != set(manifest["node_assets"])
    ):
        raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "graph node inventory differs")
    flags = graph.get("flags")
    if not isinstance(flags, list) or len(flags) != len(set(flags)):
        raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "graph flags are invalid")
    reachable = {graph["starting_node"]}
    choice_ids: set[str] = set()
    frontier = [graph["starting_node"]]
    while frontier:
        node = node_by_id[frontier.pop()]
        choices = node.get("choices")
        if (
            not isinstance(choices, list)
            or (choices and node.get("ending") is not None)
            or (not choices and node.get("ending") is None)
        ):
            raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "node termination is invalid")
        for choice in choices:
            choice_id = choice.get("choice_id") if isinstance(choice, dict) else None
            target = choice.get("target_node") if isinstance(choice, dict) else None
            if (
                not isinstance(choice_id, str)
                or choice_id in choice_ids
                or target not in node_by_id
                or any(flag not in flags for flag in choice.get("requires_flags", []))
                or choice.get("transition_year", -1) < node.get("world_year", 0)
            ):
                raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "choice semantics are invalid")
            choice_ids.add(choice_id)
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    if reachable != set(node_by_id):
        raise PackageV2Error("PACKAGE_GRAPH_SEMANTICS", "graph contains unreachable nodes")
    scenes = story.get("scenes") if isinstance(story, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise PackageV2Error("PACKAGE_STORY_GRAPH_REFERENCES", "story scenes are missing")
    scene_by_id = {scene.get("scene_id"): scene for scene in scenes if isinstance(scene, dict)}
    if len(scene_by_id) != len(scenes):
        raise PackageV2Error("PACKAGE_STORY_GRAPH_REFERENCES", "duplicate story scene")
    for node in nodes:
        scene = scene_by_id.get(node.get("scene_id"))
        if (
            scene is None
            or any(
                node.get(key) != scene.get(key)
                for key in ("participant_ids", "opportunity_id", "world_year")
            )
            or not set(scene.get("authoritative_refs", []))
            <= set(node.get("authoritative_refs", []))
            or scene.get("location_id") not in node.get("authoritative_refs", [])
            or node.get("location_id") not in identities.ids
            or any(item not in identities.ids for item in node.get("participant_ids", []))
            or any(item not in identities.ids for item in node.get("authoritative_refs", []))
        ):
            raise PackageV2Error(
                "PACKAGE_STORY_GRAPH_REFERENCES", "story and graph references differ"
            )
