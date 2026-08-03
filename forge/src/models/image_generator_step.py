"""ImageGeneratorStep — PipelineStep for parallel image generation.

Reads graph nodes + style bible, renders art_director_v1.j2 for each node,
calls ImageGenerator to produce 512x512 PNG images and thumbnails.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..config import AppConfig
from ..interfaces import ImageGenerator, Validator
from ..job_queue import FailurePolicy, PipelineContext
from .base import PipelineStep, StepOutput


class ImageGeneratorStep(PipelineStep[ImageGenerator]):
    """Generate images from graph node image_prompts using a Style Bible.

    Usage:
        step = ImageGeneratorStep(image_generator, validator, config)
        context = PipelineContext(run_id="run_01", seed=42)
        context.outputs["graph"] = {...}
        context.outputs["style_bible"] = {...}
        output = await step.run(context)
        # output.data maps node_id → image metadata
    """

    def __init__(
        self,
        generator: ImageGenerator,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.QUARANTINE,
    ) -> None:
        self.image_gen = generator
        super().__init__(
            name="image_generator",
            generator=generator,
            validator=validator,
            config=config,
            failure_policy=failure_policy,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate images for all graph nodes in parallel-ready batches.

        Requires context.outputs["graph"] and context.outputs["style_bible"].
        """
        graph = context.outputs.get("graph")
        style_bible = context.outputs.get("style_bible")
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

        # Build style suffix once
        style_suffix = self._build_style_suffix(art)
        base_negatives = self._build_base_negatives(art)

        images: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        nodes_with_prompts = 0

        for i, node in enumerate(nodes):
            node_id = node.get("node_id", f"node_{i:02d}")
            image_prompt = node.get("image_prompt", "").strip()
            if not image_prompt:
                continue  # Skip nodes without prompts
            nodes_with_prompts += 1

            # Build the full prompt
            char_text = self._build_character_context(node, char_designs)
            loc_text = self._build_location_context(node, loc_palettes)
            full_prompt = f"{image_prompt}, {char_text}{loc_text}, {style_suffix}"
            negative = f"colorful, modern, photorealistic, 3d render, anime, cartoon, text, signature, watermark, {base_negatives}"
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
            except Exception:
                continue  # QUARANTINE: skip failed nodes

            images[node_id] = {
                "size": (512, 512),
                "seed": seed,
                "prompt": image_prompt,
                "image_bytes_length": len(img_bytes),
                "thumbnail_bytes_length": len(thumb_bytes),
            }
            total_bytes += len(img_bytes) + len(thumb_bytes)

        if nodes_with_prompts > 0 and len(images) == 0:
            raise RuntimeError(
                f"Image generation failed for all {nodes_with_prompts} nodes. "
                "Check that the image model is loaded and accessible."
            )

        result = {
            "images": images,
            "image_count": len(images),
            "total_bytes": total_bytes,
        }

        artifact_id = self._make_artifact_id(result)
        return StepOutput(data=result, step_name=self.name, artifact_id=artifact_id)

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
        forbidden = art.get("forbidden", [])
        return ", ".join(forbidden)

    @staticmethod
    def _build_character_context(
        node: dict[str, Any], char_designs: dict[str, str]
    ) -> str:
        parts = []
        for cid in node.get("present_characters", []):
            if cid in char_designs:
                parts.append(char_designs[cid])
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
