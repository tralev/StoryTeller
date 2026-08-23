"""Offline deterministic Phase 5 narrative/media/index production pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..storage.fs import atomic_write_bytes
from ..validators.world_reconciler import WorldReconciler
from ..world.models import BibleV2
from ..world.views import WorldView
from ..worldgen.artifacts import canonical_json
from ..worldgen.local_index import (
    build_local_world_index,
    local_world_index_from_mapping,
    validate_local_world_index,
)
from ..worldgen.local_maps import generate_local_maps
from ..worldgen.local_reader import audit_local_storage
from ..worldgen.local_reconciliation import validate_local_reconciliation
from .batch import BatchCompletion, BatchJob, StrictBatchScheduler
from .knowledge import build_knowledge_index
from .media import (
    FULL_SIZE,
    THUMB_SIZE,
    derive_thumbnail,
    deterministic_image,
    generate_score,
    publish_verified,
    score_to_midi,
    validate_midi,
    validate_png,
    validate_score,
)
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
        return MediaRef(
            item["path"],
            item["sha256"],
            item["seed"],
            item["producer_fingerprint"],
            tuple(item["dependency_ids"]),
        )

    return NodeMedia(value["node_id"], ref("image"), ref("thumbnail"), ref("score"), ref("midi"))


class MediaProducer:
    """Produces one all-or-nothing node media record with verified publications."""

    FINGERPRINT = "storyteller.media.reference.v1"

    def __init__(
        self, root: Path, *, after_publish: Callable[[str, str], None] | None = None
    ) -> None:
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
        expected_dependencies = (
            tuple(sorted(dependencies)),
            tuple(sorted(dependencies + (media.image.sha256,))),
            tuple(sorted(dependencies)),
            tuple(sorted(dependencies + (media.score.sha256,))),
        )
        if any(
            ref.producer_fingerprint != self.FINGERPRINT or ref.dependency_ids != expected
            for ref, expected in zip(refs, expected_dependencies)
        ):
            return None
        expected_seeds = (
            node.media_intent.image_seed,
            node.media_intent.image_seed,
            node.media_intent.music_seed,
            node.media_intent.music_seed,
        )
        for ref, seed in zip(refs, expected_seeds):
            path = self.root / ref.path
            if ref.seed != seed or not path.is_file() or _hash(path) != ref.sha256:
                return None
        validate_png((self.root / media.image.path).read_bytes(), FULL_SIZE)
        validate_png((self.root / media.thumbnail.path).read_bytes(), THUMB_SIZE)
        score = _score_from_dict(json.loads((self.root / media.score.path).read_text()))
        validate_score(score)
        validate_midi((self.root / media.midi.path).read_bytes(), score)
        return media

    async def produce(self, node: GraphNodeV2) -> NodeMedia:
        dependencies = tuple(
            sorted(set(node.authoritative_refs + (node.opportunity_id, node.scene_id)))
        )
        resumed = self._resume(node, dependencies)
        if resumed is not None:
            return resumed
        image_path = self.root / "media" / "images" / f"{node.node_id}.png"
        thumb_path = self.root / "media" / "thumbnails" / f"{node.node_id}.png"
        score_path = self.root / "media" / "scores" / f"{node.node_id}.json"
        midi_path = self.root / "media" / "midi" / f"{node.node_id}.mid"
        image_data = deterministic_image(node.media_intent.image_seed)
        image = publish_verified(
            image_path,
            image_data,
            lambda data: validate_png(data, FULL_SIZE),
            seed=node.media_intent.image_seed,
            fingerprint=self.FINGERPRINT,
            dependencies=dependencies,
        )
        if self.after_publish:
            self.after_publish(node.node_id, "image")
        thumbnail_data = derive_thumbnail(image_path.read_bytes())
        thumbnail = publish_verified(
            thumb_path,
            thumbnail_data,
            lambda data: validate_png(data, THUMB_SIZE),
            seed=node.media_intent.image_seed,
            fingerprint=self.FINGERPRINT,
            dependencies=dependencies + (image.sha256,),
        )
        if self.after_publish:
            self.after_publish(node.node_id, "thumbnail")
        score_value = generate_score(node.media_intent.music_seed, node.media_intent.tempo_bpm)
        validate_score(score_value)
        score_bytes = canonical_json(score_value)
        score = publish_verified(
            score_path,
            score_bytes,
            lambda data: validate_score(_score_from_dict(json.loads(data))),
            seed=node.media_intent.music_seed,
            fingerprint=self.FINGERPRINT,
            dependencies=dependencies,
        )
        midi_bytes = score_to_midi(score_value)
        midi = publish_verified(
            midi_path,
            midi_bytes,
            lambda data: validate_midi(data, score_value),
            seed=node.media_intent.music_seed,
            fingerprint=self.FINGERPRINT,
            dependencies=dependencies + (score.sha256,),
        )
        if self.after_publish:
            self.after_publish(node.node_id, "midi")
        return NodeMedia(
            node.node_id,
            _relative(image, self.root),
            _relative(thumbnail, self.root),
            _relative(score, self.root),
            _relative(midi, self.root),
        )


def _score_from_dict(value: dict[str, Any]) -> StructuredScore:
    from .models import ScoreNote

    return StructuredScore(
        value["format_version"],
        value["ppq"],
        value["tempo_bpm"],
        value["loop_start_tick"],
        value["loop_end_tick"],
        value["program"],
        tuple(ScoreNote(**note) for note in value["notes"]),
    )


def require_complete_media(graph: GraphV2, media: dict[str, NodeMedia]) -> None:
    missing = sorted(node.node_id for node in graph.nodes if node.node_id not in media)
    if missing or len(media) != len(graph.nodes):
        raise ValueError(f"MEDIA-COVERAGE-INCOMPLETE: {missing}")


async def _generate_media(
    root: Path, graph: GraphV2, *, workers: int = 4, producer: MediaProducer | None = None
) -> dict[str, NodeMedia]:
    producer = producer or MediaProducer(root)
    scheduler: StrictBatchScheduler[GraphNodeV2] = StrictBatchScheduler(
        max_workers=workers, max_retries=2
    )
    jobs = tuple(BatchJob(node.node_id, node) for node in graph.nodes)

    async def worker(job: BatchJob[GraphNodeV2]) -> GraphNodeV2:
        # Scheduler is generic over one payload/result type. Completion values
        # are attached separately so worker ordering cannot affect aggregation.
        produced[job.job_id] = await producer.produce(job.payload)
        return job.payload

    def complete(completion: BatchCompletion[GraphNodeV2]) -> None:
        media = produced[completion.job_id]
        atomic_write_bytes(
            root / "checkpoints" / "media" / f"{completion.job_id}.json", canonical_json(media)
        )

    produced: dict[str, NodeMedia] = {}
    await scheduler.run(
        jobs,
        worker,
        retryable=lambda error: isinstance(error, (OSError, RuntimeError)),
        code=lambda error: (
            "MEDIA-RETRYABLE" if isinstance(error, (OSError, RuntimeError)) else "MEDIA-TERMINAL"
        ),
        on_complete=complete,
    )
    require_complete_media(graph, produced)
    return {key: produced[key] for key in sorted(produced)}


def generate_story_foundation(
    world_path: str | Path, bible_path: str | Path, output: str | Path, *, local_root: str | Path
) -> dict[str, Any]:
    """Generate factual opportunities and the source-linked story backbone."""
    root = Path(output).resolve()
    world = WorldView(world_path)
    bible_file = Path(bible_path)
    bible = BibleV2.from_dict(json.loads(bible_file.read_text()))
    reconciliation_file = bible_file.parent / "reconciliation.json"
    reconciliation = json.loads(reconciliation_file.read_text())
    if not reconciliation.get("accepted"):
        raise ValueError("NARRATIVE-BIBLE: reconciliation must be accepted")
    report = WorldReconciler().reconcile(world, bible)
    if not report.accepted:
        raise ValueError("NARRATIVE-BIBLE: Bible no longer reconciles with world")
    world_before = world.file_hashes
    local_index = local_world_index_from_mapping(
        json.loads((Path(local_root) / "local_index.json").read_text())
    )
    opportunities = generate_opportunities(world, local_index)
    story = generate_story(
        world, bible, opportunities, _hash(bible_file), _hash(reconciliation_file)
    )
    dependency_ids = tuple(sorted(world.artifact_ids.values()))
    atomic_write_bytes(
        root / "checkpoints" / "story" / "outline.json",
        canonical_json(
            {
                "scene_ids": [scene.scene_id for scene in story.scenes],
                "dependency_ids": dependency_ids,
                "bible_hash": story.bible_hash,
                "reconciliation_hash": story.reconciliation_hash,
            }
        ),
    )
    for scene in story.scenes:
        atomic_write_bytes(
            root / "checkpoints" / "story" / f"{scene.scene_id}.json",
            canonical_json({"scene": scene, "dependency_ids": dependency_ids}),
        )
    atomic_write_bytes(root / "opportunities.json", canonical_json(opportunities))
    atomic_write_bytes(root / "story.json", canonical_json(story))
    world.assert_unchanged(world_before)
    return {"path": str(root), "scenes": len(story.scenes), "opportunities": len(opportunities)}


def generate_graph_foundation(world_path: str | Path, output: str | Path) -> dict[str, Any]:
    """Generate and validate graph topology from a committed story backbone."""
    root = Path(output).resolve()
    world = WorldView(world_path)
    story = _story_from_dict(json.loads((root / "story.json").read_text()))
    opportunities = _opportunities_from_dict(json.loads((root / "opportunities.json").read_text()))
    graph = generate_graph(world, story, opportunities)
    validate_graph(world, graph, opportunities)
    dependency_ids = tuple(sorted(world.artifact_ids.values()))
    atomic_write_bytes(
        root / "checkpoints" / "graph" / "skeleton.json",
        canonical_json(
            {
                "starting_node": graph.starting_node,
                "node_ids": [node.node_id for node in graph.nodes],
                "dependency_ids": dependency_ids,
            }
        ),
    )
    for node in graph.nodes:
        atomic_write_bytes(
            root / "checkpoints" / "graph" / f"{node.node_id}.json",
            canonical_json({"node": node, "dependency_ids": dependency_ids}),
        )
    atomic_write_bytes(root / "graph.json", canonical_json(graph))
    return {"path": str(root), "nodes": len(graph.nodes)}


def generate_narrative_foundation(
    world_path: str | Path, bible_path: str | Path, output: str | Path
) -> dict[str, Any]:
    """Compatibility wrapper for the explicit story and graph stages."""
    generate_story_foundation(world_path, bible_path, output, local_root=output)
    return generate_graph_foundation(world_path, output)


def generate_narrative_local_maps(world_path: str | Path, output: str | Path) -> dict[str, Any]:
    """Generate, validate, and persist a local 3D map for every world site."""
    root = Path(output).resolve()
    world = WorldView(world_path)
    local_maps = generate_local_maps(world)
    reused = 0
    published = 0

    def publish(path: Path, data: bytes) -> None:
        nonlocal reused, published
        if path.is_file() and path.read_bytes() == data:
            reused += 1
            return
        atomic_write_bytes(path, data)
        published += 1

    for local in local_maps:
        validate_local_reconciliation(world, local)
        publish(root / "local_maps" / f"{local.site_id}.json", canonical_json(local))
        for family, chunks in (
            ("material", local.chunks),
            ("occupancy", local.occupancy_chunks),
            ("construction", local.construction_chunks),
        ):
            for chunk in chunks:
                publish(
                    root / "local_chunks" / local.site_id / family / f"{chunk.sha256}.json",
                    canonical_json(chunk),
                )
    if len(local_maps) != len(world.sites()):
        raise ValueError("LOCAL-COVERAGE: every site must have exactly one local map")
    local_index = build_local_world_index(local_maps)
    validate_local_world_index(
        local_index,
        local_maps,
        expected_site_ids=tuple(site.fact_id for site in world.sites()),
        local_root=root / "local_maps",
    )
    publish(root / "local_index.json", canonical_json(local_index))
    storage = audit_local_storage(root, local_index)
    return {
        "path": str(root / "local_maps"),
        "local_maps": len(local_maps),
        "sites": len(world.sites()),
        "published": published,
        "reused": reused,
        "storage": storage,
    }


async def generate_narrative_media(output: str | Path, *, workers: int = 4) -> dict[str, Any]:
    """Generate and verify mandatory per-node media for an existing graph."""
    root = Path(output).resolve()
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    media = await _generate_media(root, graph, workers=workers)
    atomic_write_bytes(root / "media.json", canonical_json(media))
    return {
        "path": str(root),
        "nodes": len(graph.nodes),
        "images": len(media),
        "thumbnails": len(media),
        "scores": len(media),
        "midi": len(media),
    }


def write_media_intents(output: str | Path, intents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Validate and commit model-refined descriptions keyed by graph node."""
    root = Path(output).resolve()
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    expected = {node.node_id for node in graph.nodes}
    if set(intents) != expected:
        raise ValueError("MEDIA-INTENT-COVERAGE: every graph node is required exactly once")
    normalized: dict[str, dict[str, Any]] = {}
    by_id = {node.node_id: node for node in graph.nodes}
    for node_id in sorted(intents):
        value = intents[node_id]
        if not isinstance(value, dict) or set(value) != {"image_prompt", "music_mood"}:
            raise ValueError("MEDIA-INTENT-SHAPE: only image_prompt and music_mood are accepted")
        if any(
            not isinstance(value[key], str)
            or not value[key].strip()
            or len(value[key].encode("utf-8")) > 4096
            for key in ("image_prompt", "music_mood")
        ):
            raise ValueError("MEDIA-INTENT-SHAPE: descriptions must be bounded non-empty strings")
        source = by_id[node_id].media_intent
        normalized[node_id] = {
            "image_prompt": value["image_prompt"].strip(),
            "music_mood": value["music_mood"].strip(),
            "tempo_bpm": source.tempo_bpm,
            "image_seed": source.image_seed,
            "music_seed": source.music_seed,
            "authoritative_refs": source.authoritative_refs,
        }
    validate_media_intent_authority(graph, normalized)
    atomic_write_bytes(root / "media_intents.json", canonical_json(normalized))
    return {"path": str(root / "media_intents.json"), "node_count": len(normalized)}


def _require_intent_authority(node: GraphNodeV2, intent: dict[str, Any]) -> None:
    refs = intent.get("authoritative_refs")
    if (
        not isinstance(refs, (list, tuple))
        or tuple(refs) != node.authoritative_refs
        or tuple(refs) != node.media_intent.authoritative_refs
    ):
        raise ValueError("MEDIA-INTENT-AUTHORITY: intent lost or changed node authority")


def validate_media_intent_authority(
    graph: GraphV2,
    intents: dict[str, dict[str, Any]],
) -> None:
    """Require exact node authority on every separately persisted media intent."""
    if set(intents) != {node.node_id for node in graph.nodes}:
        raise ValueError("MEDIA-INTENT-AUTHORITY: intent inventory does not match graph")
    for node in graph.nodes:
        _require_intent_authority(node, intents[node.node_id])


async def generate_narrative_images(output: str | Path, generator: Any) -> dict[str, Any]:
    """Generate and verify full images and deterministic thumbnails."""
    root = Path(output).resolve()
    intents = json.loads((root / "media_intents.json").read_text())
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    validate_media_intent_authority(graph, intents)
    refs: dict[str, dict[str, Any]] = {}
    for node in graph.nodes:
        intent = intents[node.node_id]
        _require_intent_authority(node, intent)
        dependencies = tuple(
            sorted(set(node.authoritative_refs + (node.opportunity_id, node.scene_id)))
        )
        image_data = await generator.generate(
            prompt=intent["image_prompt"],
            negative_prompt="text, watermark",
            size=FULL_SIZE,
            seed=intent["image_seed"],
            steps=20,
        )
        image = publish_verified(
            root / "media" / "images" / f"{node.node_id}.png",
            image_data,
            lambda data: validate_png(data, FULL_SIZE),
            seed=intent["image_seed"],
            fingerprint="storyteller.media.image.v2",
            dependencies=dependencies,
        )
        thumbnail = publish_verified(
            root / "media" / "thumbnails" / f"{node.node_id}.png",
            derive_thumbnail(image_data),
            lambda data: validate_png(data, THUMB_SIZE),
            seed=intent["image_seed"],
            fingerprint="storyteller.media.image.v2",
            dependencies=dependencies + (image.sha256,),
        )
        refs[node.node_id] = {
            "image": _relative(image, root),
            "thumbnail": _relative(thumbnail, root),
        }
        atomic_write_bytes(
            root / "checkpoints" / "images" / f"{node.node_id}.json",
            canonical_json(refs[node.node_id]),
        )
    atomic_write_bytes(root / "image_refs.json", canonical_json(refs))
    return {"path": str(root / "image_refs.json"), "node_count": len(refs)}


def generate_narrative_music(output: str | Path) -> dict[str, Any]:
    """Generate deterministic structured scores and verified MIDI publications."""
    root = Path(output).resolve()
    intents = json.loads((root / "media_intents.json").read_text())
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    validate_media_intent_authority(graph, intents)
    refs: dict[str, dict[str, Any]] = {}
    for node in graph.nodes:
        intent = intents[node.node_id]
        _require_intent_authority(node, intent)
        dependencies = tuple(
            sorted(set(node.authoritative_refs + (node.opportunity_id, node.scene_id)))
        )
        score_value = generate_score(intent["music_seed"], intent["tempo_bpm"])
        validate_score(score_value)
        score = publish_verified(
            root / "media" / "scores" / f"{node.node_id}.json",
            canonical_json(score_value),
            lambda data: validate_score(_score_from_dict(json.loads(data))),
            seed=intent["music_seed"],
            fingerprint="storyteller.media.music.v2",
            dependencies=dependencies,
        )
        midi = publish_verified(
            root / "media" / "midi" / f"{node.node_id}.mid",
            score_to_midi(score_value),
            lambda data: validate_midi(data, score_value),
            seed=intent["music_seed"],
            fingerprint="storyteller.media.music.v2",
            dependencies=dependencies + (score.sha256,),
        )
        refs[node.node_id] = {"score": _relative(score, root), "midi": _relative(midi, root)}
        atomic_write_bytes(
            root / "checkpoints" / "music" / f"{node.node_id}.json",
            canonical_json(refs[node.node_id]),
        )
    atomic_write_bytes(root / "music_refs.json", canonical_json(refs))
    return {"path": str(root / "music_refs.json"), "node_count": len(refs)}


def accept_narrative_media(output: str | Path) -> dict[str, Any]:
    """Join independently produced media only after complete consumer validation."""
    root = Path(output).resolve()
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    images = json.loads((root / "image_refs.json").read_text())
    music = json.loads((root / "music_refs.json").read_text())
    expected = {node.node_id for node in graph.nodes}
    if set(images) != expected or set(music) != expected:
        raise ValueError("MEDIA-COVERAGE-INCOMPLETE: image and music sets must match the graph")
    media = {
        node_id: NodeMedia(
            node_id,
            _media_ref_from_dict(images[node_id]["image"]),
            _media_ref_from_dict(images[node_id]["thumbnail"]),
            _media_ref_from_dict(music[node_id]["score"]),
            _media_ref_from_dict(music[node_id]["midi"]),
        )
        for node_id in sorted(expected)
    }
    require_complete_media(graph, media)
    for record in media.values():
        validate_png((root / record.image.path).read_bytes(), FULL_SIZE)
        validate_png((root / record.thumbnail.path).read_bytes(), THUMB_SIZE)
        score = _score_from_dict(json.loads((root / record.score.path).read_text()))
        validate_score(score)
        validate_midi((root / record.midi.path).read_bytes(), score)
    atomic_write_bytes(root / "media.json", canonical_json(media))
    return {"path": str(root / "media.json"), "node_count": len(media)}


def _media_ref_from_dict(value: dict[str, Any]) -> MediaRef:
    return MediaRef(
        value["path"],
        value["sha256"],
        value["seed"],
        value["producer_fingerprint"],
        tuple(value["dependency_ids"]),
    )


def generate_narrative_index(
    world_path: str | Path,
    bible_path: str | Path,
    output: str | Path,
    *,
    local_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build the complete GM index and seal the narrative project inventory."""
    root = Path(output).resolve()
    world = WorldView(world_path)
    local_project = root if local_root is None else Path(local_root).resolve()
    world_before = world.file_hashes
    bible_file = Path(bible_path)
    bible = BibleV2.from_dict(json.loads(bible_file.read_text()))
    reconciliation_file = bible_file.parent / "reconciliation.json"
    story = _story_from_dict(json.loads((root / "story.json").read_text()))
    graph = _graph_from_dict(json.loads((root / "graph.json").read_text()))
    opportunities = _opportunities_from_dict(json.loads((root / "opportunities.json").read_text()))
    validate_graph(world, graph, opportunities)
    local_maps = tuple(
        _local_map_from_dict(json.loads(path.read_text()))
        for path in sorted((local_project / "local_maps").glob("*.json"))
    )
    for local in local_maps:
        validate_local_reconciliation(world, local)
    local_index = local_world_index_from_mapping(
        json.loads((local_project / "local_index.json").read_text())
    )
    validate_local_world_index(
        local_index,
        local_maps,
        expected_site_ids=tuple(site.fact_id for site in world.sites()),
        local_root=local_project / "local_maps",
    )
    media_raw = json.loads((root / "media.json").read_text())
    media = {key: _media_from_dict(value) for key, value in media_raw.items()}
    require_complete_media(graph, media)
    knowledge = build_knowledge_index(world, bible, story, graph, opportunities, local_maps)
    atomic_write_bytes(root / "gm_index.json", canonical_json(knowledge))
    source_coverage = sorted({source for entry in knowledge for source in entry.source_ids})
    expected_sources = sorted(world.artifact_ids.values())
    if not set(expected_sources) <= set(source_coverage):
        raise ValueError("GM-COVERAGE: authoritative artifacts omitted")
    world.assert_unchanged(world_before)
    project_manifest = {
        "format": "storyteller.phase5.project.v1",
        "world_artifact_ids": world.artifact_ids,
        "world_file_hashes": world_before,
        "bible_sha256": _hash(bible_file),
        "reconciliation_sha256": _hash(reconciliation_file),
        "story_sha256": _hash(root / "story.json"),
        "graph_sha256": _hash(root / "graph.json"),
        "producer_fingerprint": MediaProducer.FINGERPRINT,
    }
    atomic_write_bytes(root / "project_manifest.json", canonical_json(project_manifest))
    inventory: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in ("inventory.json", "coverage.json"):
            relative = str(path.relative_to(root))
            inventory[relative] = {"sha256": _hash(path), "size": path.stat().st_size}
    coverage = {
        "nodes": len(graph.nodes),
        "images": len(media),
        "thumbnails": len(media),
        "scores": len(media),
        "midi": len(media),
        "local_maps": len(local_maps),
        "sites": len(world.sites()),
        "gm_entries": len(knowledge),
        "world_sources": len(source_coverage),
        "expected_world_sources": len(expected_sources),
        "complete": True,
    }
    atomic_write_bytes(root / "inventory.json", canonical_json(inventory))
    atomic_write_bytes(root / "coverage.json", canonical_json(coverage))
    return coverage


async def generate_narrative_async(
    world_path: str | Path, bible_path: str | Path, output: str | Path, *, workers: int = 4
) -> dict[str, Any]:
    """Compatibility wrapper executing the three explicit production stages."""
    generate_narrative_local_maps(world_path, output)
    generate_narrative_foundation(world_path, bible_path, output)
    await generate_narrative_media(output, workers=workers)
    return generate_narrative_index(world_path, bible_path, output)


def generate_narrative(
    world_path: str | Path, bible_path: str | Path, output: str | Path, *, workers: int = 4
) -> dict[str, Any]:
    """Synchronous diagnostic-command wrapper around the production coroutine."""
    return asyncio.run(
        generate_narrative_async(
            world_path,
            bible_path,
            output,
            workers=workers,
        )
    )


def _graph_from_dict(value: dict[str, Any]) -> GraphV2:
    from .models import ChoiceV2, MediaIntent

    nodes = tuple(
        GraphNodeV2(
            item["node_id"],
            item["scene_id"],
            item["location_id"],
            tuple(item["participant_ids"]),
            item["opportunity_id"],
            tuple(item["authoritative_refs"]),
            item["text"],
            tuple(
                ChoiceV2(
                    choice["choice_id"],
                    choice["text"],
                    choice["target_node"],
                    choice["route_id"],
                    tuple(choice["sets_flags"]),
                    tuple(choice["requires_flags"]),
                    tuple(choice["authoritative_refs"]),
                    int(choice["transition_year"]),
                    int(choice["season"]),
                )
                for choice in item["choices"]
            ),
            MediaIntent(
                item["media_intent"]["image_prompt"],
                item["media_intent"]["music_mood"],
                item["media_intent"]["tempo_bpm"],
                item["media_intent"]["image_seed"],
                item["media_intent"]["music_seed"],
                tuple(item["media_intent"]["authoritative_refs"]),
            ),
            item["ending"],
            int(item["world_year"]),
        )
        for item in value["nodes"]
    )
    return GraphV2(value["schema_version"], value["starting_node"], tuple(value["flags"]), nodes)


def _story_from_dict(value: dict[str, Any]) -> Any:
    from .models import StoryScene, StoryV2

    return StoryV2(
        value["schema_version"],
        value["title"],
        tuple(value["world_artifact_ids"]),
        value["bible_hash"],
        value["reconciliation_hash"],
        tuple(
            StoryScene(
                item["scene_id"],
                item["title"],
                item["summary"],
                item["location_id"],
                tuple(item["participant_ids"]),
                item["opportunity_id"],
                tuple(item["authoritative_refs"]),
                int(item["world_year"]),
            )
            for item in value["scenes"]
        ),
    )


def _opportunities_from_dict(value: list[dict[str, Any]]) -> Any:
    from .models import StoryOpportunity

    return tuple(
        StoryOpportunity(
            item["opportunity_id"],
            item["pressure"],
            tuple(item["participant_ids"]),
            tuple(item["location_ids"]),
            tuple(item["route_ids"]),
            tuple(item["source_ids"]),
            tuple(item["revealable_fact_ids"]),
            tuple(item.get("person_ids", ())),
            tuple(item.get("belief_ids", ())),
            tuple(item.get("site_ids", ())),
            tuple(item.get("local_containment_ids", ())),
            item.get("opportunity_kind", "faction_goal"),
            tuple(item.get("answer_fact_ids", ())),
            tuple(item.get("constraint_ids", ())),
            tuple((str(role), str(person)) for role, person in item.get("role_assignments", ())),
        )
        for item in value
    )


def _local_map_from_dict(value: dict[str, Any]) -> Any:
    from ..worldgen.local_boundaries import local_boundary_from_mapping
    from ..worldgen.local_chunks import local_voxel_chunk_from_mapping
    from ..worldgen.local_construction import construction_chunk_from_mapping
    from ..worldgen.local_maps import LocalFeature, LocalSiteMap
    from ..worldgen.local_navigation import movement_graph_from_mapping
    from ..worldgen.local_occupancy import local_occupancy_chunk_from_mapping
    from ..worldgen.local_physics import (
        heat_simulation_from_mapping,
        magma_simulation_from_mapping,
        structural_simulation_from_mapping,
        water_simulation_from_mapping,
    )
    from ..worldgen.local_society import (
        cultural_layout_from_mapping,
        persistent_entity_from_mapping,
    )
    from ..worldgen.local_summary import local_macro_summary_from_mapping

    boundary_raw = value.get("boundary")
    boundary = local_boundary_from_mapping(boundary_raw) if isinstance(boundary_raw, dict) else None
    return LocalSiteMap(
        value["algorithm_version"],
        value["site_id"],
        value["width"],
        value["height"],
        value["z_levels"],
        value["macro_cell"],
        tuple(value["strata"]),
        tuple(value["surface_height"]),
        tuple(
            LocalFeature(
                item["feature_id"],
                item["kind"],
                tuple(tuple(cell) for cell in item["cells"]),
                tuple(item["source_ids"]),
            )
            for item in value["features"]
        ),
        boundary,
        tuple(local_voxel_chunk_from_mapping(item) for item in value.get("chunks", ())),
        tuple(
            local_occupancy_chunk_from_mapping(item) for item in value.get("occupancy_chunks", ())
        ),
        tuple(
            construction_chunk_from_mapping(item) for item in value.get("construction_chunks", ())
        ),
        cultural_layout_from_mapping(value["layout"])
        if isinstance(value.get("layout"), dict)
        else None,
        tuple(persistent_entity_from_mapping(item) for item in value.get("entities", ())),
        movement_graph_from_mapping(value["movement_graph"])
        if isinstance(value.get("movement_graph"), dict)
        else None,
        water_simulation_from_mapping(value["water_simulation"])
        if isinstance(value.get("water_simulation"), dict)
        else None,
        magma_simulation_from_mapping(value["magma_simulation"])
        if isinstance(value.get("magma_simulation"), dict)
        else None,
        heat_simulation_from_mapping(value["heat_simulation"])
        if isinstance(value.get("heat_simulation"), dict)
        else None,
        structural_simulation_from_mapping(
            value["structural_simulation"],
            heat_simulation_from_mapping(value["heat_simulation"]).final,
        )
        if (
            isinstance(value.get("structural_simulation"), dict)
            and isinstance(value.get("heat_simulation"), dict)
        )
        else None,
        local_macro_summary_from_mapping(value["macro_summary"])
        if isinstance(value.get("macro_summary"), dict)
        else None,
    )


def validate_project(root_path: str | Path) -> dict[str, int]:
    root = Path(root_path).resolve()
    required = (
        "story.json",
        "graph.json",
        "opportunities.json",
        "media.json",
        "gm_index.json",
        "project_manifest.json",
        "inventory.json",
        "coverage.json",
    )
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
            if choice.target_node not in nodes or any(
                flag not in graph.flags for flag in choice.requires_flags
            ):
                raise ValueError("PROJECT-GRAPH: invalid target or flag")
            if choice.target_node not in reachable:
                reachable.add(choice.target_node)
                frontier.append(choice.target_node)
    if reachable != set(nodes) or endings < 2:
        raise ValueError("PROJECT-GRAPH: reachability or endings invalid")
    media_raw = json.loads((root / "media.json").read_text())
    media = {key: _media_from_dict(value) for key, value in media_raw.items()}
    require_complete_media(graph, media)
    for node_id, item in media.items():
        missing_paths = [
            ref.path
            for ref in (item.image, item.thumbnail, item.score, item.midi)
            if not (root / ref.path).is_file()
        ]
        if missing_paths:
            raise ValueError(f"PROJECT-MEDIA-MISSING: {node_id}: {missing_paths}")
        validate_png((root / item.image.path).read_bytes(), FULL_SIZE)
        validate_png((root / item.thumbnail.path).read_bytes(), THUMB_SIZE)
        score = _score_from_dict(json.loads((root / item.score.path).read_text()))
        validate_score(score)
        validate_midi((root / item.midi.path).read_bytes(), score)
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
    if any(
        any(node not in valid_nodes for node in entry["reveal_after_nodes"]) for entry in entries
    ):
        raise ValueError("PROJECT-GM-REVEAL: unknown reveal node")
    if (
        coverage["local_maps"] != coverage["sites"]
        or len(list((root / "local_maps").glob("*.json"))) != coverage["sites"]
    ):
        raise ValueError("PROJECT-LOCAL-MAPS: incomplete site coverage")
    return {
        "nodes": len(graph.nodes),
        "media": len(media),
        "gm_entries": int(coverage["gm_entries"]),
    }
