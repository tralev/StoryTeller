"""Adapters that make existing v2 services one production pipeline."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..models.base import PipelineStep, StepOutput


class _Stage(PipelineStep[Any]):
    def __init__(self, name: str, output_key: str, output_dir: str,
                 generator: Any = None, **kwargs: Any) -> None:
        super().__init__(name=name, generator=generator, validator=None, **kwargs)
        self.output_key = output_key; self.root = Path(output_dir)


class PhysicalWorldStage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..worldgen.physical_pipeline import generate_physical_world
        path = self.root / "world" / "physical"
        result = generate_physical_world(context.spec.world, context.seed, path)
        return StepOutput({**result, "path": str(path)}, self.name)


class SimulateWorldStage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..worldgen.simulation import simulate_world
        physical = Path(context.outputs["world_physical"]["path"])
        path = self.root / "world" / "authoritative"
        result = simulate_world(physical, context.spec.world.history_years, path)
        return StepOutput({**result, "path": str(path)}, self.name)


class BibleV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..storage.fs import atomic_write_bytes
        from ..validators.world_reconciler import WorldReconciler
        from ..world.builder import WorldBuilderV2
        from ..world.views import WorldView
        from ..worldgen.artifacts import canonical_json
        world = Path(context.outputs["world"]["path"]); path = self.root / "bible"
        bible, _ = WorldBuilderV2().build(world, context.title, path)
        if self.generator is None:
            raise ValueError("BIBLE-ENRICHMENT-MODEL: text generator is required")

        # The model receives an immutable, source-linked projection and may
        # enrich only prose interpretations. Structured world facts are never
        # accepted from inference output.
        prompt = (
            "Enrich this authoritative world Bible with 1 to 8 concise mature "
            "dark-fantasy interpretations. Do not restate or alter facts. Return "
            "JSON only as {\"interpretations\": [\"...\"]}.\n\n"
            + canonical_json(bible).decode("utf-8")
        )
        generated = await self.generator.generate(
            prompt=prompt,
            temperature=context.spec.temperature,
            seed=context.seed,
            max_tokens=1024,
        )
        if isinstance(generated, str):
            try:
                generated = json.loads(generated)
            except json.JSONDecodeError as error:
                raise ValueError("BIBLE-ENRICHMENT-JSON: model returned invalid JSON") from error
        interpretations = generated.get("interpretations") if isinstance(generated, dict) else None
        if not isinstance(interpretations, list) or not 1 <= len(interpretations) <= 8:
            raise ValueError("BIBLE-ENRICHMENT-SHAPE: expected 1 to 8 interpretations")
        cleaned = tuple(item.strip() for item in interpretations
                        if isinstance(item, str) and item.strip())
        if len(cleaned) != len(interpretations):
            raise ValueError("BIBLE-ENRICHMENT-SHAPE: interpretations must be non-empty strings")
        bible = replace(bible, interpretations=cleaned)
        report = WorldReconciler().reconcile(WorldView(world), bible)
        if not report.accepted:
            raise ValueError("BIBLE-ENRICHMENT-RECONCILIATION: enriched Bible was rejected")
        atomic_write_bytes(path / "bible.json", canonical_json(bible))
        atomic_write_bytes(path / "reconciliation.json", canonical_json(report))
        return StepOutput({"path": str(path / "bible.json"), "root": str(path),
                           "accepted": report.accepted}, self.name)


class ReconcileWorldStage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        path = Path(context.outputs["bible"]["root"]) / "reconciliation.json"
        value = json.loads(path.read_text())
        if not value.get("accepted"):
            raise ValueError("WORLD-RECONCILIATION: Bible was not accepted")
        return StepOutput({"path": str(path), "accepted": True}, self.name)


class ArtDirectionV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..storage.fs import atomic_write_bytes
        from ..world.art_direction import ArtDirectionV2, derive_art_direction
        from ..world.models import BibleV2
        from ..world.views import WorldView
        from ..worldgen.artifacts import canonical_json
        if self.generator is None:
            raise ValueError("ART-DIRECTION-MODEL: text generator is required")
        bible_root = Path(context.outputs["bible"]["root"])
        bible = BibleV2.from_dict(json.loads(Path(context.outputs["bible"]["path"]).read_text()))
        deterministic = derive_art_direction(WorldView(context.outputs["world"]["path"]), bible)
        prompt = (
            "Refine the visual wording for this authoritative art direction. Return JSON only as "
            "{\"climate_palettes\": {\"<existing key>\": \"description\"}, "
            "\"culture_motifs\": {\"<existing key>\": \"description\"}}. Preserve exactly "
            "the supplied keys; do not add facts, cultures, climates, maps, or references.\n"
            + canonical_json({"climate_palettes": deterministic.climate_palettes,
                              "culture_motifs": deterministic.culture_motifs}).decode("utf-8")
        )
        generated = await self.generator.generate(
            prompt=prompt, temperature=context.spec.temperature, seed=context.seed, max_tokens=2048,
        )
        if isinstance(generated, str):
            try:
                generated = json.loads(generated)
            except json.JSONDecodeError as error:
                raise ValueError("ART-DIRECTION-JSON: model returned invalid JSON") from error
        if not isinstance(generated, dict) or set(generated) != {"climate_palettes", "culture_motifs"}:
            raise ValueError("ART-DIRECTION-SHAPE: expected only palette and motif maps")
        palettes = generated["climate_palettes"]
        motifs = generated["culture_motifs"]
        if (not isinstance(palettes, dict) or set(palettes) != set(deterministic.climate_palettes)
                or not isinstance(motifs, dict) or set(motifs) != set(deterministic.culture_motifs)):
            raise ValueError("ART-DIRECTION-SHAPE: model must preserve every key exactly")
        for values in (palettes, motifs):
            if any(not isinstance(value, str) or not value.strip()
                   or len(value.encode("utf-8")) > 2048 for value in values.values()):
                raise ValueError("ART-DIRECTION-SHAPE: descriptions must be bounded non-empty strings")
        enriched = ArtDirectionV2(
            deterministic.map_artifact_id, deterministic.climate_artifact_id,
            deterministic.accepted_bible_refs,
            {key: palettes[key].strip() for key in sorted(palettes)},
            {key: motifs[key].strip() for key in sorted(motifs)}, deterministic.world_map,
        )
        path = bible_root / "style_bible.json"
        atomic_write_bytes(path, canonical_json(enriched))
        return StepOutput({"path": str(path), "root": str(bible_root)}, self.name)


class StoryV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import _story_from_dict, generate_story_foundation
        from ..storage.fs import atomic_write_bytes
        from ..world.views import WorldView
        from ..worldgen.artifacts import canonical_json
        path = self.root / "narrative"
        coverage = generate_story_foundation(context.outputs["world"]["path"],
                                               context.outputs["bible"]["path"], path,
                                               local_root=context.outputs["local_maps"]["root"])
        if self.generator is None:
            raise ValueError("STORY-PROSE-MODEL: text generator is required")
        story_data = json.loads((path / "story.json").read_text())
        prompt_scenes = [{"scene_id": item["scene_id"], "factual_summary": item["summary"]}
                         for item in story_data["scenes"]]
        prompt = (
            "Write a concise title and mature dark-fantasy summary for every supplied scene. "
            "Do not add facts, people, places, events, or outcomes. Return JSON only as "
            "{\"scenes\": {\"<scene_id>\": {\"title\": \"...\", \"summary\": \"...\"}}} "
            "with exactly these scene IDs:\n" + canonical_json(prompt_scenes).decode("utf-8")
        )
        generated = await self.generator.generate(
            prompt=prompt, temperature=context.spec.temperature,
            seed=context.seed, max_tokens=max(2048, len(prompt_scenes) * 256),
        )
        if isinstance(generated, str):
            try:
                generated = json.loads(generated)
            except json.JSONDecodeError as error:
                raise ValueError("STORY-PROSE-JSON: model returned invalid JSON") from error
        prose = generated.get("scenes") if isinstance(generated, dict) else None
        expected = {item["scene_id"] for item in story_data["scenes"]}
        if not isinstance(prose, dict) or set(prose) != expected:
            raise ValueError("STORY-PROSE-SHAPE: model must return every scene exactly once")
        for item in story_data["scenes"]:
            replacement = prose[item["scene_id"]]
            if not isinstance(replacement, dict) or set(replacement) != {"title", "summary"}:
                raise ValueError("STORY-PROSE-SHAPE: each scene requires only title and summary")
            for field in ("title", "summary"):
                value = replacement[field]
                if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 8192:
                    raise ValueError(f"STORY-PROSE-SHAPE: {field} must be a bounded non-empty string")
                item[field] = value.strip()
        story = _story_from_dict(story_data)
        atomic_write_bytes(path / "story.json", canonical_json(story))
        dependency_ids = tuple(sorted(WorldView(context.outputs["world"]["path"]).artifact_ids.values()))
        for scene in story.scenes:
            atomic_write_bytes(path / "checkpoints" / "story" / f"{scene.scene_id}.json",
                               canonical_json({"scene": scene, "dependency_ids": dependency_ids}))
        return StepOutput({"path": str(path / "story.json"), "root": str(path),
                           "coverage": coverage}, self.name)


class GraphV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import (_graph_from_dict, _opportunities_from_dict,
                                          generate_graph_foundation)
        from ..narrative.story_graph import validate_graph
        from ..storage.fs import atomic_write_bytes
        from ..world.views import WorldView
        from ..worldgen.artifacts import canonical_json
        path = Path(context.outputs["story"]["root"])
        coverage = generate_graph_foundation(context.outputs["world"]["path"], path)
        if self.generator is None:
            raise ValueError("GRAPH-PROSE-MODEL: text generator is required")
        graph_data = json.loads((path / "graph.json").read_text())
        prompt_nodes = [{"node_id": item["node_id"], "factual_summary": item["text"]}
                        for item in graph_data["nodes"]]
        prompt = (
            "Write concise mature dark-fantasy prose for every supplied graph node. "
            "Do not add facts, names, places, routes, choices, or outcomes. Return JSON "
            "only as {\"nodes\": {\"<node_id>\": \"prose\"}} with exactly these IDs:\n"
            + canonical_json(prompt_nodes).decode("utf-8")
        )
        generated = await self.generator.generate(
            prompt=prompt, temperature=context.spec.temperature,
            seed=context.seed, max_tokens=max(2048, len(prompt_nodes) * 256),
        )
        if isinstance(generated, str):
            try:
                generated = json.loads(generated)
            except json.JSONDecodeError as error:
                raise ValueError("GRAPH-PROSE-JSON: model returned invalid JSON") from error
        prose = generated.get("nodes") if isinstance(generated, dict) else None
        expected = {item["node_id"] for item in graph_data["nodes"]}
        if not isinstance(prose, dict) or set(prose) != expected:
            raise ValueError("GRAPH-PROSE-SHAPE: model must return every node exactly once")
        for item in graph_data["nodes"]:
            text = prose[item["node_id"]]
            if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 8192:
                raise ValueError("GRAPH-PROSE-SHAPE: node prose must be a bounded non-empty string")
            item["text"] = text.strip()
        graph = _graph_from_dict(graph_data)
        opportunities = _opportunities_from_dict(json.loads((path / "opportunities.json").read_text()))
        world = WorldView(context.outputs["world"]["path"])
        validate_graph(world, graph, opportunities)
        atomic_write_bytes(path / "graph.json", canonical_json(graph))
        for node in graph.nodes:
            atomic_write_bytes(path / "checkpoints" / "graph" / f"{node.node_id}.json",
                               canonical_json({"node": node,
                                               "dependency_ids": tuple(sorted(
                                                   world.artifact_ids.values()
                                               ))}))
        return StepOutput({"path": str(path), "coverage": coverage}, self.name)


class LocalMapsV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import generate_narrative_local_maps
        project = self.root / "local_worlds"
        coverage = generate_narrative_local_maps(context.outputs["world"]["path"], project)
        return StepOutput({"path": str(project / "local_maps"), "root": str(project),
                           "coverage": coverage}, self.name)


class MediaIntentsV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import _graph_from_dict, write_media_intents
        project = Path(context.outputs["narrative_project"]["path"])
        graph = _graph_from_dict(json.loads((project / "graph.json").read_text()))
        if self.generator is None:
            raise ValueError("MEDIA-INTENT-MODEL: text generator is required")
        source = {node.node_id: {"image_prompt": node.media_intent.image_prompt,
                                "music_mood": node.media_intent.music_mood}
                  for node in graph.nodes}
        prompt = (
            "Refine the image prompt and music mood for every graph node without adding facts. "
            "Return JSON only as {\"nodes\": {\"<node_id>\": {\"image_prompt\": \"...\", "
            "\"music_mood\": \"...\"}}}; preserve exactly these node IDs and fields.\n"
            + json.dumps(source, sort_keys=True, separators=(",", ":"))
        )
        generated = await self.generator.generate(
            prompt=prompt, temperature=context.spec.temperature, seed=context.seed,
            max_tokens=max(2048, len(graph.nodes) * 384),
        )
        if isinstance(generated, str):
            try:
                generated = json.loads(generated)
            except json.JSONDecodeError as error:
                raise ValueError("MEDIA-INTENT-JSON: model returned invalid JSON") from error
        if not isinstance(generated, dict) or set(generated) != {"nodes"} or not isinstance(generated["nodes"], dict):
            raise ValueError("MEDIA-INTENT-SHAPE: expected only a nodes mapping")
        coverage = write_media_intents(project, generated["nodes"])
        return StepOutput(coverage, self.name)


class ImageMediaV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import generate_narrative_images
        if self.generator is None:
            raise ValueError("MEDIA-IMAGE-MODEL: image generator is required")
        project = Path(context.outputs["narrative_project"]["path"])
        return StepOutput(await generate_narrative_images(project, self.generator), self.name)


class MusicMediaV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import generate_narrative_music
        project = Path(context.outputs["narrative_project"]["path"])
        return StepOutput(generate_narrative_music(project), self.name)


class AcceptMediaV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import accept_narrative_media
        project = Path(context.outputs["narrative_project"]["path"])
        return StepOutput(accept_narrative_media(project), self.name)


class GmIndexV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..narrative.pipeline import generate_narrative_index
        project = Path(context.outputs["narrative_project"]["path"])
        coverage = generate_narrative_index(
            context.outputs["world"]["path"], context.outputs["bible"]["path"], project,
            local_root=context.outputs["local_maps"]["root"],
        )
        return StepOutput({"path": str(project / "gm_index.json"), "root": str(project),
                           "coverage": coverage}, self.name)


class PackageV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..storage.package_v2 import inspect_v2_package
        from ..storage.project_v2 import package_project_v2
        destination = self.root / ".output.story.staged"
        path = package_project_v2(context.outputs["world"]["path"], context.outputs["bible"]["root"],
                                  context.outputs["narrative_project"]["path"], destination,
                                  title=context.title, seed=context.seed, staged=True,
                                  local_root=context.outputs["local_maps"]["root"])
        info = inspect_v2_package(path)
        return StepOutput({"package_path": str(path), "package_size": path.stat().st_size,
                           "content_hash": info["content_hash"], "media_complete": True,
                           "coverage": {"images": 1.0, "midi": 1.0}}, self.name)


class AcceptPackageV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..storage.package_v2 import validate_v2_package
        candidate = Path(context.outputs["package_candidate"]["package_path"])
        result = validate_v2_package(candidate)
        if not result.accepted or result.manifest is None:
            issue = result.issues[0]
            raise ValueError(f"{issue.code}: {issue.message}")
        return StepOutput({"accepted": True, "package_path": str(candidate),
                           "story_id": result.manifest["story_id"],
                           "content_hash": result.manifest["content_hash"]}, self.name)


class PublishPackageV2Stage(_Stage):
    async def generate(self, context: Any) -> StepOutput[dict[str, Any]]:
        from ..storage.package_v2 import publish_staged_package, validate_v2_package
        acceptance = context.outputs["package_acceptance"]
        if acceptance.get("accepted") is not True:
            raise ValueError("PACKAGE_NOT_ACCEPTED: publication requires accepted candidate")
        staged = Path(acceptance["package_path"])
        current = validate_v2_package(staged)
        if (not current.accepted or current.manifest is None or
                current.manifest.get("content_hash") != acceptance.get("content_hash") or
                current.manifest.get("story_id") != acceptance.get("story_id")):
            raise ValueError("PACKAGE_CHANGED_AFTER_ACCEPTANCE: staged candidate is no longer accepted")
        path = publish_staged_package(staged, self.root / "output.story")
        return StepOutput({"package_path": str(path), "package_size": path.stat().st_size,
                           "content_hash": acceptance["content_hash"],
                           "story_id": acceptance["story_id"], "media_complete": True,
                           "coverage": {"images": 1.0, "midi": 1.0}}, self.name)
