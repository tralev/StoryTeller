"""ManifestBuilder — produces a complete, schema-compliant manifest.json.

Phase 5.5D: Runs AFTER all generation steps and BEFORE packaging.
Reads all context.outputs, builds a manifest that satisfies
manifest.schema.json with all required fields: artifact_id, story_id,
title, generated_at, generator_version, models_used, prompt_versions,
entry_point, files, content_hash, stats.

Replaces the old pattern where Packager patched an empty dict.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, cast

from ..job_queue import PipelineContext
from ..models.base import StepOutput
from ..pipeline.artifacts import ManifestDict


class ManifestBuilder:
    """Build a complete, validated manifest from pipeline context.

    Usage:
        builder = ManifestBuilder()
        context.outputs["bible"] = {...}
        context.outputs["graph"] = {...}
        ...
        output = await builder.run(context)
        # output.data is a manifest dict matching manifest.schema.json
    """

    GENERATOR_VERSION = "0.1.0"

    def __init__(self, schemas_dir: str | None = None) -> None:
        self._schemas_dir = schemas_dir

    async def run(self, context: PipelineContext) -> StepOutput[ManifestDict]:
        """Build the manifest from all available context artifacts."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Generate a stable story_id from seed + world_name
        bible = context.outputs.get_bible() or {}  # Phase 5.6N N5
        world_name = bible.get("world_name", "unknown") if isinstance(bible, dict) else "unknown"
        story_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"storyteller:{context.seed}:{world_name}"))

        # Count assets
        graph = context.outputs.get_graph() or {}
        nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
        total_nodes = len(nodes)
        entry_point = graph.get("starting_node", "node_01") if isinstance(graph, dict) else "node_01"
        endings = graph.get("endings_summary", []) if isinstance(graph, dict) else []
        total_endings = len(endings)

        # Count images from the images output dict.
        # Phase 5.6 Q3: total_images counts COMPLETED (non-quarantined)
        # images only (image_count) — the aggregated dict also holds
        # structured quarantine records, which are NOT media files. Using
        # the completed count keeps stats consistent with missing_images.
        images_data = context.outputs.get_images() or {}
        total_images = (
            images_data.get("image_count", 0) if isinstance(images_data, dict) else 0
        )

        # Count MIDI from the midi output dict (same completed-only rule).
        midi_data = context.outputs.get_midi() or {}
        total_midi = (
            midi_data.get("midi_count", 0) if isinstance(midi_data, dict) else 0
        )

        # Phase 5.6 Q3: expected vs completed vs quarantined media counts
        # (nodes with a trigger vs completed items vs explicitly quarantined)
        nodes_with_image_prompt = sum(
            1 for n in nodes if str(n.get("image_prompt", "")).strip()
        )
        nodes_with_music_tone = sum(
            1 for n in nodes if str(n.get("music_tone", "")).strip()
        )
        images_completed = (
            images_data.get("image_count", 0) if isinstance(images_data, dict) else 0
        )
        midi_completed = (
            midi_data.get("midi_count", 0) if isinstance(midi_data, dict) else 0
        )
        quarantined_images = (
            images_data.get("quarantined", 0) if isinstance(images_data, dict) else 0
        )
        quarantined_midi = (
            midi_data.get("quarantined", 0) if isinstance(midi_data, dict) else 0
        )
        missing_images = max(0, nodes_with_image_prompt - images_completed)
        missing_midi = max(0, nodes_with_music_tone - midi_completed)

        # Compute content hash (from all immutable artifacts)
        content_hash = self._compute_content_hash(context)

        # Model identities
        models_used = self._collect_model_info(context)

        # Prompt versions (all v1 currently)
        prompt_versions = {
            "world_builder": "v1",
            "story_writer": "v1",
            "game_designer": "v1",
            "art_director": "v1",
            "composer": "v1",
            "style_bible": "v1",
        }

        gen_time = round(
            time.time() - context.state.get("start_time", time.time()), 1,
        )

        # ── Canonical fields (artifact identity — same for identical seeds) ──
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "story_id": story_id,
            "title": context.title,  # Phase 5.6N N4: typed run spec
            "tone": context.tone,
            "seed": context.seed,
            "generator_version": self.GENERATOR_VERSION,
            "models_used": models_used,
            "prompt_versions": prompt_versions,
            "entry_point": entry_point,
            "files": {
                "bible": "content/bible.json",
                "style_bible": "content/style_bible.json",
                "story": "content/story.json",
                "graph": "content/graph.json",
                "gm_index": "content/gm_index.json",
                "images": "content/images/",
                "midi": "content/midi/",
                "thumbnails": "content/thumbnails/",
            },
            "stats": {
                "total_nodes": total_nodes,
                "total_images": total_images,
                "total_midi": total_midi,
                "total_endings": total_endings,
                # Phase 5.6 Q3: media coverage inventory
                "nodes_with_image_prompt": nodes_with_image_prompt,
                "nodes_with_music_tone": nodes_with_music_tone,
                "quarantined_images": quarantined_images,
                "quarantined_midi": quarantined_midi,
                "missing_images": missing_images,
                "missing_midi": missing_midi,
            },
            "content_hash": content_hash,

            # ── Operational metadata (varies per run, NOT part of artifact identity) ──
            "meta": {
                "artifact_id": "",  # Set by packager after ZIP is built
                "generated_at": now,
                "run_id": context.run_id,
                "generation_time_seconds": gen_time,
                "peak_ram_mb": 0,  # Updated by generate_story after packaging
            },
        }

        # Validate against schema if available
        if self._schemas_dir:
            self._validate(manifest)

        return StepOutput(
            data=cast(ManifestDict, manifest),
            step_name="manifest_builder",
            artifact_id=f"manifest_{content_hash[:8]}",  # Content-derived, not temporal
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _collect_model_info(context: PipelineContext) -> dict[str, str]:
        """Collect model identity strings from context or config."""
        config = context.config
        if config is None:
            return {
                "text_generator": "unknown",
                "validator": "unknown",
                "image_generator": "unknown",
                "music_generator": "unknown",
            }
        return {
            "text_generator": f"{config.text_generator.model}-{config.text_generator.quantization}",
            "validator": f"{config.validator.model}-{config.validator.quantization}",
            "image_generator": f"{config.image_generator.model}-{config.image_generator.quantization}",
            "music_generator": config.music_generator.model,
        }

    @staticmethod
    def _compute_content_hash(context: PipelineContext) -> str:
        """SHA256 of all immutable content artifacts using canonical algorithm.

        Phase 5.6 A5: Uses shared content_hash.compute_json_content_hash
        for consistent hashing across ManifestBuilder and Packager.
        """
        from .content_hash import compute_json_content_hash

        json_artifacts: dict[str, dict[str, Any]] = {}
        for key in ["bible", "style_bible", "story", "graph", "gm_index"]:
            data = context.outputs.get(key)
            if isinstance(data, dict):
                json_artifacts[key] = data
        return compute_json_content_hash(json_artifacts)

    def _validate(self, manifest: dict[str, Any]) -> None:
        """Validate manifest against manifest.schema.json — terminal on failure.

        Phase 5.6 A4: Schema failure raises PackageValidationError.
        Previously printed a warning and continued.
        """
        try:
            from ..validators.schema_validator import SchemaValidator
            from ..pipeline.errors import PackageValidationError

            sv = SchemaValidator(self._schemas_dir or "schemas")
            result = sv.validate_manifest(manifest)
            if not result.is_valid:
                raise PackageValidationError(
                    "manifest.json",
                    [result.format_for_retry()],
                )
        except PackageValidationError:
            raise
        except Exception as e:
            # Schema validator itself failed — also terminal
            from ..pipeline.errors import PackageValidationError
            raise PackageValidationError(
                "manifest.json",
                [f"Manifest validation infrastructure error: {e}"],
            ) from e
