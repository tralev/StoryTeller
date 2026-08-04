"""ImageGeneratorStep — PipelineStep for parallel image generation.

Reads graph nodes + style bible, renders art_director_v1.j2 for each node,
calls ImageGenerator to produce 512x512 PNG images and thumbnails.

Writes image files to output_dir/images/ and output_dir/thumbnails/.
Stores file paths (not raw bytes) in context.outputs for the Packager.

Supports node-level checkpointing for resume after interruption.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from ..config import AppConfig
from ..interfaces import ImageGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from ..storage.fs import atomic_write_bytes
from .base import PipelineStep, StepOutput


class ImageGeneratorStep(PipelineStep[ImageGenerator]):
    """Generate images from graph node image_prompts using a Style Bible.

    output_key = "images"

    Writes PNG files to output_dir/images/ and output_dir/thumbnails/.

    Usage:
        step = ImageGeneratorStep(image_generator, output_dir="output")
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["graph"] = {...}
        context.outputs["style_bible"] = {...}
        output = await step.run(context)
        # output.data maps node_id → {image_path, thumb_path, ...}
    """

    def __init__(
        self,
        generator: ImageGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.QUARANTINE,
        output_dir: str = "tmp/output",
        policy: Any = None,  # Phase 5.6G: ExecutionPolicy
    ) -> None:
        from ..pipeline.policy import ExecutionPolicy
        self.image_gen = generator
        self.output_dir = Path(output_dir)
        super().__init__(
            name="image_generator",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
            policy=policy or ExecutionPolicy.default(),
        )

    async def generate(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        """Generate images for all graph nodes, writing to disk."""
        graph = context.outputs.get_graph()  # Phase 5.6N N5
        style_bible = context.outputs.get_style_bible()
        if graph is None:
            raise ValueError(
                "ImageGeneratorStep requires context.outputs['graph']. "
                "Run GameDesigner first."
            )
        if style_bible is None:
            raise ValueError(
                "ImageGeneratorStep requires context.outputs['style_bible']. "
                "Run ArtDirector first."
            )

        nodes = graph.get("nodes", [])
        art = style_bible.get("art_style", {})
        char_designs = style_bible.get("character_design", {})
        loc_palettes = style_bible.get("location_palettes", {})

        # Ensure output directories exist
        img_dir = self.output_dir / "images"
        thumb_dir = self.output_dir / "thumbnails"
        img_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        style_suffix = self._build_style_suffix(art)
        base_negatives = self._build_base_negatives(art)

        images: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        nodes_with_prompts = 0
        completed_nodes: set[str] = set()

        # Check for previously completed nodes (resume support)
        prev_output = context.outputs.get_images()
        if isinstance(prev_output, dict):
            prev_images = prev_output.get("images", {})
            for nid, meta in prev_images.items():
                img_path = Path(meta.get("image_path", ""))
                if img_path.exists():
                    images[nid] = cast(dict[str, Any], meta)
                    completed_nodes.add(nid)
                    total_bytes += meta.get("image_bytes", 0)

        for i, node in enumerate(nodes):
            node_id = node.get("node_id", f"node_{i:02d}")
            if node_id in completed_nodes:
                continue  # Already done (resume)

            image_prompt = node.get("image_prompt", "").strip()
            if not image_prompt:
                continue
            nodes_with_prompts += 1

            node_d: dict[str, Any] = cast(dict[str, Any], node)
            char_text = self._build_character_context(node_d, char_designs)
            loc_text = self._build_location_context(node_d, loc_palettes)
            full_prompt = f"{image_prompt}, {char_text}{loc_text}, {style_suffix}"
            negative = (
                "colorful, modern, photorealistic, 3d render, anime, "
                f"cartoon, text, signature, watermark, {base_negatives}"
            )
            seed = context.seed + i

            try:
                img_bytes = await self.image_gen.generate(
                    prompt=full_prompt,
                    negative_prompt=negative,
                    size=(512, 512),
                    seed=seed,
                )
                thumb_bytes = await self.image_gen.generate_thumbnail(
                    img_bytes, size=(128, 128),
                )
            except Exception as e:
                from ..pipeline.errors import is_retryable
                if is_retryable(e):
                    continue  # QUARANTINE — retryable generation error
                raise  # Terminal error — abort entire batch

            # Write to disk (Phase 5.6 O2: atomic — tmp file + rename)
            img_path = img_dir / f"{node_id}.png"
            thumb_path = thumb_dir / f"{node_id}.png"
            atomic_write_bytes(img_path, img_bytes)
            atomic_write_bytes(thumb_path, thumb_bytes)

            images[node_id] = {
                "size": (512, 512),
                "seed": seed,
                "prompt": image_prompt,
                "image_path": str(img_path),
                "thumb_path": str(thumb_path),
                "image_bytes": len(img_bytes),
            }
            total_bytes += len(img_bytes) + len(thumb_bytes)

        if nodes_with_prompts > 0 and len(images) == len(completed_nodes):
            raise RuntimeError(
                f"Image generation failed for all {nodes_with_prompts} new nodes. "
                "Check that the image model is loaded and accessible."
            )

        result = {
            "images": images,
            "image_count": len(images),
            "total_bytes": total_bytes,
        }

        artifact_id = self._make_artifact_id(result)
        return StepOutput(data=result, step_name=self.name, artifact_id=artifact_id)

    async def generate_node(
        self,
        node_id: str,
        node: dict[str, Any],
        index: int,
        style_bible: dict[str, Any],
        seed: int,
        img_dir: Path,
        thumb_dir: Path,
    ) -> dict[str, Any]:
        """Generate a single image for one node (Phase 5.5H).

        Called by BatchScheduler — one job per node.
        """
        image_prompt = node.get("image_prompt", "").strip()
        if not image_prompt:
            raise ValueError(f"Node {node_id} has no image_prompt")

        art = style_bible.get("art_style", {})
        char_designs = style_bible.get("character_design", {})
        loc_palettes = style_bible.get("location_palettes", {})

        style_suffix = self._build_style_suffix(art)
        base_negatives = self._build_base_negatives(art)

        char_text = self._build_character_context(node, char_designs)
        loc_text = self._build_location_context(node, loc_palettes)
        full_prompt = f"{image_prompt}, {char_text}{loc_text}, {style_suffix}"
        negative = (
            "colorful, modern, photorealistic, 3d render, anime, "
            f"cartoon, text, signature, watermark, {base_negatives}"
        )

        img_bytes = await self.image_gen.generate(
            prompt=full_prompt,
            negative_prompt=negative,
            size=(512, 512),
            seed=seed,
        )
        thumb_bytes = await self.image_gen.generate_thumbnail(
            img_bytes, size=(128, 128),
        )

        # Write to disk (Phase 5.6 O2: atomic — tmp file + rename)
        img_path = img_dir / f"{node_id}.png"
        thumb_path = thumb_dir / f"{node_id}.png"
        atomic_write_bytes(img_path, img_bytes)
        atomic_write_bytes(thumb_path, thumb_bytes)

        return {
            "size": (512, 512),
            "seed": seed,
            "prompt": image_prompt,
            "image_path": str(img_path),
            "thumb_path": str(thumb_path),
            "image_bytes": len(img_bytes),
        }

    # ── prompt building ─────────────────────────────────────────────────

    @staticmethod
    def _build_style_suffix(art: dict[str, Any]) -> str:
        parts = [
            art.get("palette", ""),
            art.get("lighting", ""),
            art.get("linework", ""),
            art.get("mood", ""),
            "dark fantasy concept art",
            "intricate ink illustration",
            "parchment background",
            "masterpiece",
            "trending on artstation",
        ]
        return ", ".join(p for p in parts if p)

    @staticmethod
    def _build_base_negatives(art: dict[str, Any]) -> str:
        return ", ".join(art.get("forbidden", []))

    @staticmethod
    def _build_character_context(
        node: dict[str, Any], char_designs: dict[str, str]
    ) -> str:
        parts = [
            char_designs[cid]
            for cid in node.get("present_characters", [])
            if cid in char_designs
        ]
        return ", ".join(parts) + ", " if parts else ""

    @staticmethod
    def _build_location_context(
        node: dict[str, Any], loc_palettes: dict[str, str]
    ) -> str:
        loc_id = node.get("present_location", "")
        if loc_id and loc_id in loc_palettes:
            return f"{loc_palettes[loc_id]}, "
        return ""

    # ── metadata ────────────────────────────────────────────────────────

    @staticmethod
    def _make_artifact_id(data: dict[str, Any]) -> str:
        content = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"img_{digest}"
