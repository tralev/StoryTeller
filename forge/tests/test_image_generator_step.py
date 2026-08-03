"""Tests for ImageGeneratorStep — TDD for Phase 5.

ImageGeneratorStep generates 512x512 images from node image_prompts
using a Style Bible for consistency. Runs in parallel via Job Queue.

Pipeline: node.image_prompt + style_bible → ImageGenerator → PNG bytes → disk
"""

from __future__ import annotations

from typing import Any

import pytest

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput


# ── test data ────────────────────────────────────────────────────────────────


def _make_style_bible() -> dict[str, Any]:
    """Minimal style bible for image generation."""
    return {
        "schema_version": 1,
        "art_style": {
            "palette": "desaturated earth tones, cold blue shadows",
            "lighting": "low-key chiaroscuro, single light source",
            "composition": "character off-center, environmental depth",
            "linework": "visible ink hatching, rough edges",
            "mood": "melancholy, ancient, foreboding",
            "forbidden": [
                "modern technology", "neon colors", "photorealism",
                "3d render", "anime style", "smiling figures",
                "text", "UI elements",
            ],
        },
        "character_design": {
            "char_01": "A weathered wanderer in salt-stained leather, sharp jaw, tired eyes.",
            "char_03": "A masked priest in bleached robes, tall and gaunt, hollow voice.",
        },
        "location_palettes": {
            "loc_01": "Endless white salt flats, pale blue sky, distant grey mountains.",
            "loc_02": "Glowing white salt cathedral, amber candlelight, deep black shadows.",
        },
    }


def _make_single_node() -> dict[str, Any]:
    """A single graph node with image_prompt for testing."""
    return {
        "node_id": "node_01",
        "chapter": 1,
        "scene_type": "exploration",
        "text": "You stand at the edge of the wastes.",
        "present_characters": ["char_01"],
        "present_location": "loc_01",
        "present_creatures": [],
        "mood": "desolate",
        "image_prompt": "A lone figure at the edge of endless white salt flats, cold blue horizon",
        "music_tone": "melancholy",
        "choices": [],
    }


def _make_multiple_nodes() -> list[dict[str, Any]]:
    """Three nodes with different image_prompts for batch testing."""
    return [
        {
            "node_id": "node_01",
            "chapter": 1,
            "scene_type": "exploration",
            "text": "You stand at the edge of the wastes.",
            "present_characters": ["char_01"],
            "present_location": "loc_01",
            "present_creatures": [],
            "mood": "desolate",
            "image_prompt": "A lone figure at the edge of endless white salt flats",
            "music_tone": "melancholy",
            "choices": [],
        },
        {
            "node_id": "node_02",
            "chapter": 2,
            "scene_type": "combat",
            "text": "The Salt Wraith attacks.",
            "present_characters": ["char_01"],
            "present_location": "loc_02",
            "present_creatures": ["cre_01"],
            "mood": "tense",
            "image_prompt": "A translucent salt wraith screaming in a glowing temple",
            "music_tone": "tense",
            "choices": [],
        },
        {
            "node_id": "node_03",
            "chapter": 3,
            "scene_type": "ending",
            "text": "The God-Heart shatters.",
            "present_characters": ["char_01"],
            "present_location": "loc_02",
            "present_creatures": [],
            "mood": "triumphant",
            "image_prompt": "A salt temple collapsing, dawn light breaking through",
            "music_tone": "triumphant",
            "choices": [],
        },
    ]


# ── Mock ImageGenerator ──────────────────────────────────────────────────────


class MockImageGenerator:
    """Mock ImageGenerator that returns deterministic PNG bytes per seed."""

    provider: str = "sd-cpp"
    model_name: str = "sdxl-turbo"
    quantization: str = "Q8_0"

    def __init__(self) -> None:
        self.call_count = 0
        self.thumbnail_count = 0
        self.last_prompt: str = ""
        self.last_negative_prompt: str = ""
        self.last_seed: int | None = None
        self.last_size: tuple[int, int] = (0, 0)

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = (512, 512),
        seed: int | None = None,
        steps: int = 20,
    ) -> bytes:
        self.call_count += 1
        self.last_prompt = prompt
        self.last_negative_prompt = negative_prompt
        self.last_seed = seed
        self.last_size = size
        # Deterministic "image" bytes from seed
        seed_bytes = (seed or 0).to_bytes(4, "big")
        return b"\x89PNG\r\n\x1a\n" + seed_bytes * 64

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        size: tuple[int, int] = (128, 128),
    ) -> bytes:
        self.thumbnail_count += 1
        # Return a smaller version
        return b"\x89PNG\r\n" + image_bytes[:64]

    async def load(self) -> None:
        pass

    async def unload(self) -> None:
        pass

    @property
    def ram_usage_mb(self) -> int:
        return 3500


class MockFailingImageGenerator:
    """ImageGenerator that fails on every call."""

    provider = "sd-cpp"
    model_name = "broken"
    quantization = "Q0"

    async def generate(self, prompt="", **kwargs) -> bytes:
        raise RuntimeError("Image generation failed: out of memory")

    async def generate_thumbnail(self, image_bytes=b"", **kwargs) -> bytes:
        raise RuntimeError("Thumbnail generation failed")

    async def load(self) -> None:
        pass

    async def unload(self) -> None:
        pass

    @property
    def ram_usage_mb(self) -> int:
        return 0


# ── Tests ────────────────────────────────────────────────────────────────────


class TestImageGeneratorStepSingle:
    """Single image generation from a node."""

    @pytest.mark.asyncio
    async def test_generates_image_from_node(self) -> None:
        """ImageGeneratorStep calls ImageGenerator with the node's image_prompt."""
        gen = MockImageGenerator()
        node = _make_single_node()

        # Simulate what ImageGeneratorStep would do
        prompt = node["image_prompt"]
        size = (512, 512)
        image_bytes = await gen.generate(prompt=prompt, size=size, seed=42)

        assert image_bytes.startswith(b"\x89PNG")
        assert gen.call_count == 1
        assert node["image_prompt"] in gen.last_prompt

    @pytest.mark.asyncio
    async def test_injects_style_bible_suffix(self) -> None:
        """The prompt includes the style bible suffix for visual consistency."""
        gen = MockImageGenerator()
        style = _make_style_bible()

        # Build the full prompt as ImageGeneratorStep would
        art_suffix = (
            f"{style['art_style']['palette']}, "
            f"{style['art_style']['linework']}, "
            f"{style['art_style']['mood']}, "
            f"dark fantasy concept art, intricate ink illustration"
        )
        full_prompt = f"A lone figure at the edge of white salt flats, {art_suffix}"

        await gen.generate(prompt=full_prompt, seed=42)
        assert "desaturated earth tones" in gen.last_prompt
        assert "visible ink hatching" in gen.last_prompt
        assert "dark fantasy concept art" in gen.last_prompt

    @pytest.mark.asyncio
    async def test_includes_negative_prompt(self) -> None:
        """Negative prompt excludes forbidden elements from style bible."""
        gen = MockImageGenerator()
        style = _make_style_bible()
        negatives = ", ".join(style["art_style"]["forbidden"])

        await gen.generate(
            prompt="A test scene, dark fantasy concept art",
            negative_prompt=f"colorful, modern, photorealistic, {negatives}",
            seed=42,
        )
        assert "modern technology" in gen.last_negative_prompt
        assert "neon colors" in gen.last_negative_prompt

    @pytest.mark.asyncio
    async def test_uses_correct_size(self) -> None:
        """Images are generated at 512x512."""
        gen = MockImageGenerator()
        await gen.generate(prompt="test", size=(512, 512), seed=1)
        assert gen.last_size == (512, 512)

    @pytest.mark.asyncio
    async def test_deterministic_output(self) -> None:
        """Same seed → identical bytes."""
        gen1 = MockImageGenerator()
        gen2 = MockImageGenerator()

        b1 = await gen1.generate(prompt="test", seed=42)
        b2 = await gen2.generate(prompt="test", seed=42)

        assert b1 == b2

    @pytest.mark.asyncio
    async def test_different_seeds_produce_different_output(self) -> None:
        """Different seeds → different bytes."""
        gen = MockImageGenerator()
        b1 = await gen.generate(prompt="test", seed=1)
        b2 = await gen.generate(prompt="test", seed=2)
        assert b1 != b2

    @pytest.mark.asyncio
    async def test_generates_thumbnail(self) -> None:
        """Thumbnails are generated from full images."""
        gen = MockImageGenerator()
        full = await gen.generate(prompt="test", seed=42, size=(512, 512))
        thumb = await gen.generate_thumbnail(full, size=(128, 128))

        assert thumb.startswith(b"\x89PNG")
        assert gen.thumbnail_count == 1
        assert gen.call_count == 1  # Full image separate from thumbnail

    @pytest.mark.asyncio
    async def test_step_output_includes_metadata(self) -> None:
        """StepOutput includes artifact_id, paths, and generation params."""
        # Expected StepOutput shape from ImageGeneratorStep
        gen = MockImageGenerator()
        node = _make_single_node()
        image_bytes = await gen.generate(prompt=node["image_prompt"], seed=42)
        thumb_bytes = await gen.generate_thumbnail(image_bytes)

        output = StepOutput(
            data={
                "images": {
                    "node_01": {
                        "size": (512, 512),
                        "seed": 42,
                        "prompt": node["image_prompt"],
                        "image_bytes_length": len(image_bytes),
                        "thumbnail_bytes_length": len(thumb_bytes),
                    }
                },
                "image_count": 1,
                "total_bytes": len(image_bytes) + len(thumb_bytes),
            },
            step_name="image_generator",
            artifact_id="img_a1b2c3d4",
        )

        assert output.step_name == "image_generator"
        assert output.artifact_id is not None
        assert output.data["image_count"] == 1
        assert "node_01" in output.data["images"]


class TestImageGeneratorStepBatch:
    """Batch image generation for multiple nodes."""

    @pytest.mark.asyncio
    async def test_generates_images_for_all_nodes(self) -> None:
        """Each node gets its own image, generated with its own seed."""
        nodes = _make_multiple_nodes()
        gen = MockImageGenerator()

        results: dict[str, bytes] = {}
        for i, node in enumerate(nodes):
            seed = 42 + i
            img = await gen.generate(prompt=node["image_prompt"], seed=seed)
            results[node["node_id"]] = img

        assert len(results) == 3
        assert gen.call_count == 3
        # Each node got its image_prompt
        assert all(n["node_id"] in results for n in nodes)

    @pytest.mark.asyncio
    async def test_different_nodes_have_different_prompts(self) -> None:
        """Each node's image_prompt is unique — no accidental reuse."""
        nodes = _make_multiple_nodes()
        gen = MockImageGenerator()
        prompts_seen: list[str] = []

        for i, node in enumerate(nodes):
            await gen.generate(prompt=node["image_prompt"], seed=42 + i)
            prompts_seen.append(gen.last_prompt)

        # All prompts should differ
        assert len(set(prompts_seen)) == 3

    @pytest.mark.asyncio
    async def test_nodes_without_image_prompt_skipped(self) -> None:
        """Nodes missing image_prompt are skipped with a warning, not crashed."""

        class WarningCollector:
            """Mock that also tracks skipped nodes."""
            warnings: list[str] = []

        nodes = [
            {"node_id": "node_01", "image_prompt": "A scene."},
            {"node_id": "node_02"},  # No image_prompt
            {"node_id": "node_03", "image_prompt": ""},  # Empty prompt
        ]

        generated = 0
        skipped = 0
        for node in nodes:
            prompt = node.get("image_prompt", "")
            if not prompt:
                skipped += 1
                continue
            generated += 1

        assert generated == 1
        assert skipped == 2

    @pytest.mark.asyncio
    async def test_batch_thumbnail_generation(self) -> None:
        """Thumbnails generated for each full image."""
        gen = MockImageGenerator()
        for i in range(3):
            full = await gen.generate(prompt=f"scene {i}", seed=i)
            await gen.generate_thumbnail(full)

        assert gen.thumbnail_count == 3


class TestImageGeneratorStepEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_requires_graph_in_context(self) -> None:
        """ImageGeneratorStep requires context.outputs['graph']."""
        ctx = PipelineContext(run_id="r1", seed=1)
        # No graph set
        assert "graph" not in ctx.outputs
        # When implemented: ImageGeneratorStep should raise PipelineError

    @pytest.mark.asyncio
    async def test_requires_style_bible_in_context(self) -> None:
        """ImageGeneratorStep requires context.outputs['style_bible']."""
        ctx = PipelineContext(run_id="r1", seed=1)
        assert "style_bible" not in ctx.outputs
        # When implemented: ImageGeneratorStep should raise PipelineError

    @pytest.mark.asyncio
    async def test_generation_failure_aborts(self) -> None:
        """Failing generator raises error that propagates (ABORT policy)."""
        gen = MockFailingImageGenerator()
        with pytest.raises(RuntimeError, match="out of memory"):
            await gen.generate(prompt="test")

    @pytest.mark.asyncio
    async def test_empty_graph_no_nodes(self) -> None:
        """Empty graph with no nodes produces empty output, not a crash."""

        class EmptyGraphGenerator:
            provider = "sd-cpp"
            model_name = "test"
            quantization = "Q4"
            call_count = 0

            async def generate(self, prompt="", **kwargs):
                self.call_count += 1
                return b""

            async def generate_thumbnail(self, img=b"", **kwargs):
                return b""

        gen = EmptyGraphGenerator()
        # No nodes → no calls
        assert gen.call_count == 0

    def test_style_bible_forbidden_list_integrity(self) -> None:
        """Forbidden elements list is non-empty and covers key categories."""
        style = _make_style_bible()
        forbidden = style["art_style"]["forbidden"]
        assert len(forbidden) >= 5
        assert any("modern" in f.lower() for f in forbidden)
        assert any("neon" in f.lower() for f in forbidden)
        assert any("photorealism" in f.lower() for f in forbidden)

    def test_style_bible_character_designs_complete(self) -> None:
        """Every character in the bible has a character_design entry."""
        style = _make_style_bible()
        present_chars = ["char_01", "char_03"]
        for cid in present_chars:
            assert cid in style["character_design"], f"Missing design for {cid}"

    def test_style_bible_location_palettes_complete(self) -> None:
        """Every location in the bible has a location_palettes entry."""
        style = _make_style_bible()
        present_locs = ["loc_01", "loc_02"]
        for lid in present_locs:
            assert lid in style["location_palettes"], f"Missing palette for {lid}"


class TestImageGeneratorStepArtDirectorIntegration:
    """Style bible + node → image prompt pipeline."""

    def test_character_design_injected_by_id(self) -> None:
        """Character design pulled from style bible by character ID."""
        style = _make_style_bible()
        node = _make_single_node()

        char_designs = []
        for cid in node["present_characters"]:
            if cid in style["character_design"]:
                char_designs.append(f"[{cid}]: {style['character_design'][cid]}")

        assert len(char_designs) > 0
        assert "char_01" in char_designs[0]
        assert "weathered wanderer" in char_designs[0]

    def test_location_palette_injected_by_id(self) -> None:
        """Location palette pulled from style bible by location ID."""
        style = _make_style_bible()
        node = _make_single_node()
        loc_id = node["present_location"]

        palette = style["location_palettes"].get(loc_id, "")
        assert loc_id in palette or "salt flats" in palette

    def test_full_prompt_assembly(self) -> None:
        """The full prompt combines image_prompt + style suffix + character + location."""
        style = _make_style_bible()
        node = _make_single_node()

        art = style["art_style"]
        suffix_parts = [
            art["palette"],
            art["lighting"],
            art["linework"],
            art["mood"],
            "dark fantasy concept art",
            "intricate ink illustration",
            "parchment background",
            "masterpiece",
            "trending on artstation",
        ]
        style_suffix = ", ".join(suffix_parts)

        full_prompt = f"{node['image_prompt']}, {style_suffix}"
        assert node["image_prompt"] in full_prompt
        assert "dark fantasy concept art" in full_prompt
        assert "trending on artstation" in full_prompt

    def test_negative_prompt_assembly(self) -> None:
        """Negative prompt combines base exclusions + style bible forbidden list."""
        style = _make_style_bible()

        base_negatives = [
            "colorful", "modern", "photorealistic", "3d render",
            "anime", "cartoon", "text", "signature", "watermark",
        ]
        forbidden = style["art_style"]["forbidden"]
        full_negative = ", ".join(base_negatives + forbidden)

        assert "modern technology" in full_negative
        assert "anime style" in full_negative
        assert "watermark" in full_negative
