"""Offline deterministic Phase 5 narrative/media/index production pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

from ..storage.fs import atomic_write_bytes
from ..validators.world_reconciler import WorldReconciler
from ..world.models import BibleV2
from ..world.views import WorldView
from ..worldgen.artifacts import canonical_json
from ..worldgen.local_maps import generate_local_maps, validate_local_map
from .batch import BatchCompletion, BatchJob, StrictBatchScheduler
from .knowledge import build_knowledge_index
from .media import (FULL_SIZE, THUMB_SIZE, derive_thumbnail, deterministic_image, generate_score,
                    publish_verified, score_to_midi, validate_midi, validate_png, validate_score)
from .models import GraphNodeV2, GraphV2, MediaRef, NodeMedia, StructuredScore
from .opportunities import generate_opportunities
from .story_graph import generate_graph, generate_story, validate_graph


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(ref: MediaRef, root: Path) -> MediaRef:
    return replace(ref, path=str(Path(ref.path).relative_to(root)))


def _media_from_dict(value: dict[str, Any]) -> NodeMedia:
    def ref(name: str) -> MediaRef:
        item = value[name]
        return MediaRef(item["path"], item["sha256"], item["seed"], item["producer_fingerprint"],
                        tuple(item["dependency_ids"]))
    return NodeMedia(value["node_id"], ref("image"), ref("thumbnail"), ref("score"), ref("midi"))


class MediaProducer:
    """Produces one all-or-nothing node media record with verified publications."""
    FINGERPRINT = "storyteller.media.reference.v1"

    def __init__(self, root: Path, *, after_publish: Callable[[str, str], None] | None = None) -> None:
        self.root = root.resolve()
        self.after_publish = after_publish

    def _resume(self, node: GraphNodeV2, dependencies: tuple[str, ...]) -> NodeMedia | None:
        checkpoint = self.root / "checkpoints" / "media" / f"{node.node_id}.json"
        if not checkpoint.is_file():
            return None
        try:
            media = _media_from_dict(json.loads(checkpoint.read_text()))
        except Exception:
            return None
        refs = (media.image, media.thumbnail, media.score, media.midi)
        expected_dependencies = (tuple(sorted(dependencies)),
                                 tuple(sorted(dependencies + (media.image.sha256,))),
                                 tuple(sorted(dependencies)),
                                 tuple(sorted(dependencies + (media.score.sha256,))))
        if any(ref.producer_fingerprint != self.FINGERPRINT
               or ref.dependency_ids != expected for ref, expected in zip(refs, expected_dependencies)):
            return None
        expected_seeds = (node.media_intent.image_seed, node.media_intent.image_seed,
                          node.media_intent.music_seed, node.media_intent.music_seed)
        for ref, seed in zip(refs, expected_seeds):
            path = self.root / ref.path
            if ref.seed != seed or not path.is_file() or _hash(path) != ref.sha256:
                return None
        validate_png((self.root / media.image.path).read_bytes(), FULL_SIZE)
        validate_png((self.root / media.thumbnail.path).read_bytes(), THUMB_SIZE)
        score = _score_from_dict(json.loads((self.root / media.score.path).read_text()))
        validate_score(score); validate_midi((self.root / media.midi.path).read_bytes(), score)
        return media

    async def produce(self, node: GraphNodeV2) -> NodeMedia:
        dependencies = tuple(sorted(set(node.authoritative_refs + (node.opportunity_id, node.scene_id))))
        resumed = self._resume(node, dependencies)
        if resumed is not None:
            return resumed
        image_path = self.root / "media" / "images" / f"{node.node_id}.png"
        thumb_path = self.root / "media" / "thumbnails" / f"{node.node_id}.png"
        score_path = self.root / "media" / "scores" / f"{node.node_id}.json"
        midi_path = self.root / "media" / "midi" / f"{node.node_id}.mid"
        image_data = deterministic_image(node.media_intent.image_seed)
        image = publish_verified(image_path, image_data, lambda data: validate_png(data, FULL_SIZE),
                                 seed=node.media_intent.image_seed, fingerprint=self.FINGERPRINT,
                                 dependencies=dependencies)
        if self.after_publish: self.after_publish(node.node_id, "image")
        thumbnail_data = derive_thumbnail(image_path.read_bytes())
        thumbnail = publish_verified(thumb_path, thumbnail_data, lambda data: validate_png(data, THUMB_SIZE),
                                     seed=node.media_intent.image_seed, fingerprint=self.FINGERPRINT,
                                     dependencies=dependencies + (image.sha256,))
        if self.after_publish: self.after_publish(node.node_id, "thumbnail")
        score_value = generate_score(node.media_intent.music_seed, node.media_intent.tempo_bpm)
        validate_score(score_value)
        score_bytes = canonical_json(score_value)
        score = publish_verified(score_path, score_bytes,
                                 lambda data: validate_score(_score_from_dict(json.loads(data))),
                                 seed=node.media_intent.music_seed, fingerprint=self.FINGERPRINT,
                                 dependencies=dependencies)
        midi_bytes = score_to_midi(score_value)
        midi = publish_verified(midi_path, midi_bytes, lambda data: validate_midi(data, score_value),
                                seed=node.media_intent.music_seed, fingerprint=self.FINGERPRINT,
                                dependencies=dependencies + (score.sha256,))
        if self.after_publish: self.after_publish(node.node_id, "midi")
        return NodeMedia(node.node_id, _relative(image, self.root), _relative(thumbnail, self.root),
                         _relative(score, self.root), _relative(midi, self.root))


def _score_from_dict(value: dict[str, Any]) -> StructuredScore:
    from .models import ScoreNote
    return StructuredScore(value["format_version"], value["ppq"], value["tempo_bpm"],
                           value["loop_start_tick"], value["loop_end_tick"], value["program"],
                           tuple(ScoreNote(**note) for note in value["notes"]))


def require_complete_media(graph: GraphV2, media: dict[str, NodeMedia]) -> None:
    missing = sorted(node.node_id for node in graph.nodes if node.node_id not in media)
    if missing or len(media) != len(graph.nodes):
        raise ValueError(f"MEDIA-COVERAGE-INCOMPLETE: {missing}")


async def _generate_media(root: Path, graph: GraphV2, *, workers: int = 4,
                          producer: MediaProducer | None = None) -> dict[str, NodeMedia]:
    producer = producer or MediaProducer(root)
    scheduler: StrictBatchScheduler[GraphNodeV2] = StrictBatchScheduler(max_workers=workers, max_retries=2)
    jobs = tuple(BatchJob(node.node_id, node) for node in graph.nodes)

    async def worker(job: BatchJob[GraphNodeV2]) -> GraphNodeV2:
        # Scheduler is generic over one payload/result type. Completion values
        # are attached separately so worker ordering cannot affect aggregation.
        produced[job.job_id] = await producer.produce(job.payload)
        return job.payload

    def complete(completion: BatchCompletion[GraphNodeV2]) -> None:
        media = produced[completion.job_id]
        atomic_write_bytes(root / "checkpoints" / "media" / f"{completion.job_id}.json",
                           canonical_json(media))

    produced: dict[str, NodeMedia] = {}
    await scheduler.run(jobs, worker, retryable=lambda error: isinstance(error, (OSError, RuntimeError)),
                        code=lambda error: "MEDIA-RETRYABLE" if isinstance(error, (OSError, RuntimeError))
                        else "MEDIA-TERMINAL", on_complete=complete)
    require_complete_media(graph, produced)
    return {key: produced[key] for key in sorted(produced)}


def generate_narrative(world_path: str | Path, bible_path: str | Path,
                       output: str | Path, *, workers: int = 4) -> dict[str, Any]:
    root = Path(output).resolve(); world = WorldView(world_path)
    bible_file = Path(bible_path); bible = BibleV2.from_dict(json.loads(bible_file.read_text()))
    reconciliation_file = bible_file.parent / "reconciliation.json"
    reconciliation = json.loads(reconciliation_file.read_text())
    if not reconciliation.get("accepted"):
        raise ValueError("NARRATIVE-BIBLE: reconciliation must be accepted")
    report = WorldReconciler().reconcile(world, bible)
    if not report.accepted:
        raise ValueError("NARRATIVE-BIBLE: Bible no longer reconciles with world")
    world_before = world.file_hashes
    opportunities = generate_opportunities(world)
    local_maps = generate_local_maps(world)
    for local in local_maps:
        validate_local_map(local)
        atomic_write_bytes(root / "local_maps" / f"{local.site_id}.json", canonical_json(local))
    story = generate_story(world, bible, opportunities, _hash(bible_file), _hash(reconciliation_file))
    graph = generate_graph(world, story, opportunities)
    validate_graph(world, graph, opportunities)
    dependency_ids = tuple(sorted(world.artifact_ids.values()))
    atomic_write_bytes(root / "checkpoints" / "story" / "outline.json", canonical_json({
        "scene_ids": [scene.scene_id for scene in story.scenes], "dependency_ids": dependency_ids,
        "bible_hash": story.bible_hash, "reconciliation_hash": story.reconciliation_hash,
    }))
    for scene in story.scenes:
        atomic_write_bytes(root / "checkpoints" / "story" / f"{scene.scene_id}.json",
                           canonical_json({"scene": scene, "dependency_ids": dependency_ids}))
    atomic_write_bytes(root / "checkpoints" / "graph" / "skeleton.json", canonical_json({
        "starting_node": graph.starting_node, "node_ids": [node.node_id for node in graph.nodes],
        "dependency_ids": dependency_ids,
    }))
    for node in graph.nodes:
        atomic_write_bytes(root / "checkpoints" / "graph" / f"{node.node_id}.json",
                           canonical_json({"node": node, "dependency_ids": dependency_ids}))
    atomic_write_bytes(root / "opportunities.json", canonical_json(opportunities))
    atomic_write_bytes(root / "story.json", canonical_json(story))
    atomic_write_bytes(root / "graph.json", canonical_json(graph))
    media = asyncio.run(_generate_media(root, graph, workers=workers))
    atomic_write_bytes(root / "media.json", canonical_json(media))
    knowledge = build_knowledge_index(world, bible, story, graph, opportunities, local_maps)
    atomic_write_bytes(root / "gm_index.json", canonical_json(knowledge))
    source_coverage = sorted({source for entry in knowledge for source in entry.source_ids})
    expected_sources = sorted(world.artifact_ids.values())
    if not set(expected_sources) <= set(source_coverage):
        raise ValueError("GM-COVERAGE: authoritative artifacts omitted")
    world.assert_unchanged(world_before)
    project_manifest = {
        "format": "storyteller.phase5.project.v1", "world_artifact_ids": world.artifact_ids,
        "world_file_hashes": world_before, "bible_sha256": _hash(bible_file),
        "reconciliation_sha256": _hash(reconciliation_file),
        "story_sha256": _hash(root / "story.json"), "graph_sha256": _hash(root / "graph.json"),
        "producer_fingerprint": MediaProducer.FINGERPRINT,
    }
    atomic_write_bytes(root / "project_manifest.json", canonical_json(project_manifest))
    inventory: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in ("inventory.json", "coverage.json"):
            relative = str(path.relative_to(root))
            inventory[relative] = {"sha256": _hash(path), "size": path.stat().st_size}
    coverage = {"nodes": len(graph.nodes), "images": len(media), "thumbnails": len(media),
                "scores": len(media), "midi": len(media), "local_maps": len(local_maps),
                "sites": len(world.sites()), "gm_entries": len(knowledge),
                "world_sources": len(source_coverage), "expected_world_sources": len(expected_sources),
                "complete": True}
    atomic_write_bytes(root / "inventory.json", canonical_json(inventory))
    atomic_write_bytes(root / "coverage.json", canonical_json(coverage))
    return coverage


def _graph_from_dict(value: dict[str, Any]) -> GraphV2:
    from .models import ChoiceV2, MediaIntent
    nodes = tuple(GraphNodeV2(item["node_id"], item["scene_id"], item["location_id"],
                              tuple(item["participant_ids"]), item["opportunity_id"],
                              tuple(item["authoritative_refs"]), item["text"],
                              tuple(ChoiceV2(choice["choice_id"], choice["text"], choice["target_node"],
                                             choice["route_id"], tuple(choice["sets_flags"]),
                                             tuple(choice["requires_flags"])) for choice in item["choices"]),
                              MediaIntent(**item["media_intent"]), item["ending"])
                  for item in value["nodes"])
    return GraphV2(value["schema_version"], value["starting_node"], tuple(value["flags"]), nodes)


def validate_project(root_path: str | Path) -> dict[str, int]:
    root = Path(root_path).resolve()
    required = ("story.json", "graph.json", "opportunities.json", "media.json", "gm_index.json",
                "project_manifest.json", "inventory.json", "coverage.json")
    if any(not (root / name).is_file() for name in required):
        raise ValueError("PROJECT-INCOMPLETE: required artifact missing")
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    nodes = {node.node_id: node for node in graph.nodes}
    if graph.starting_node not in nodes:
        raise ValueError("PROJECT-GRAPH: invalid start")
    reachable, frontier = {graph.starting_node}, [graph.starting_node]
    endings = 0
    while frontier:
        node = nodes[frontier.pop(0)]
        if node.media_intent.image_seed == node.media_intent.music_seed:
            raise ValueError("PROJECT-SEEDS: media domains are not separated")
        if node.ending is not None:
            endings += 1
            if node.choices:
                raise ValueError("PROJECT-GRAPH: ending has choices")
        for choice in node.choices:
            if choice.target_node not in nodes or any(flag not in graph.flags for flag in choice.requires_flags):
                raise ValueError("PROJECT-GRAPH: invalid target or flag")
            if choice.target_node not in reachable:
                reachable.add(choice.target_node); frontier.append(choice.target_node)
    if reachable != set(nodes) or endings < 2:
        raise ValueError("PROJECT-GRAPH: reachability or endings invalid")
    media_raw = json.loads((root / "media.json").read_text())
    media = {key: _media_from_dict(value) for key, value in media_raw.items()}
    require_complete_media(graph, media)
    for node_id, item in media.items():
        missing_paths = [ref.path for ref in (item.image, item.thumbnail, item.score, item.midi)
                         if not (root / ref.path).is_file()]
        if missing_paths:
            raise ValueError(f"PROJECT-MEDIA-MISSING: {node_id}: {missing_paths}")
        validate_png((root / item.image.path).read_bytes(), FULL_SIZE)
        validate_png((root / item.thumbnail.path).read_bytes(), THUMB_SIZE)
        score = _score_from_dict(json.loads((root / item.score.path).read_text()))
        validate_score(score); validate_midi((root / item.midi.path).read_bytes(), score)
        for ref in (item.image, item.thumbnail, item.score, item.midi):
            if _hash(root / ref.path) != ref.sha256:
                raise ValueError(f"PROJECT-HASH: corrupt media for {node_id}")
    inventory = json.loads((root / "inventory.json").read_text())
    for relative, metadata in inventory.items():
        path = root / relative
        if not path.is_file() or _hash(path) != metadata["sha256"]:
            raise ValueError(f"PROJECT-INVENTORY: mismatch {relative}")
    coverage = json.loads((root / "coverage.json").read_text())
    if not coverage.get("complete") or coverage["nodes"] != len(graph.nodes):
        raise ValueError("PROJECT-COVERAGE: incomplete")
    manifest = json.loads((root / "project_manifest.json").read_text())
    entries = json.loads((root / "gm_index.json").read_text())
    indexed_sources = {source for entry in entries for source in entry["source_ids"]}
    if not set(manifest["world_artifact_ids"].values()) <= indexed_sources:
        raise ValueError("PROJECT-GM-COVERAGE: world source omitted")
    valid_nodes = set(nodes)
    if any(any(node not in valid_nodes for node in entry["reveal_after_nodes"]) for entry in entries):
        raise ValueError("PROJECT-GM-REVEAL: unknown reveal node")
    if (coverage["local_maps"] != coverage["sites"]
            or len(list((root / "local_maps").glob("*.json"))) != coverage["sites"]):
        raise ValueError("PROJECT-LOCAL-MAPS: incomplete site coverage")
    return {"nodes": len(graph.nodes), "media": len(media), "gm_entries": int(coverage["gm_entries"])}
