"""Real-model smoke test — controlled 1-node generation with actual GGUF models.

Phase 5.5I: Verifies the pipeline works with real models (not mocks).
Requires models in ../ai_models/ or ~/.storyteller/models/.

This is a GATED test — skipped if models aren't found. Run manually:
    STORYTELLER_MODELS_DIR=../ai_models PYTHONPATH=. .venv/bin/pytest \\
        tests/test_real_model_smoke.py -v -s --timeout 600
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


def _find_models_dir() -> str | None:
    """Find the models directory."""
    candidates = [
        os.environ.get("STORYTELLER_MODELS_DIR", ""),
        str(Path(__file__).resolve().parent.parent.parent / "ai_models"),
        os.path.expanduser("~/.storyteller/models"),
    ]
    for d in candidates:
        if d and Path(d).exists() and any(Path(d).glob("*.gguf")):
            return d
    return None


def _has_text_model(models_dir: str) -> bool:
    return (Path(models_dir) / "Qwen2.5-7B-Instruct-Q4_K_M.gguf").exists()


def _has_image_model(models_dir: str) -> bool:
    return (Path(models_dir) / "sd_xl_turbo_1.0.q8_0.gguf").exists()


def _model_count(models_dir: str) -> int:
    return len(list(Path(models_dir).glob("*.gguf")))


class TestRealModelSmoke:
    """Real-model pipeline smoke tests. Gated — skipped without models."""

    @pytest.fixture(autouse=True)
    def _check_models(self, request: Any) -> None:
        models_dir = _find_models_dir()
        if not models_dir:
            pytest.skip("No models directory found")
        if not _has_text_model(models_dir):
            pytest.skip(f"Qwen2.5-7B GGUF not found in {models_dir}")
        self._models_dir = models_dir

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_text_model_loads_and_unloads(self) -> None:
        """The Qwen 7B text model loads and unloads correctly."""
        from src.backends.llm_backend import LlamaCppTextGenerator
        from src.config import ModelConfig

        cfg = ModelConfig(
            provider="llama_cpp",
            model="qwen2.5-7b-instruct",
            quantization="Q4_K_M",
            file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        )

        gen = LlamaCppTextGenerator(cfg)

        # Load
        await gen.load()
        assert gen._model is not None, "Model should be loaded"

        # Generate a simple completion
        result = await gen.generate(
            prompt='Output ONLY valid JSON: {"test": true}',
            temperature=0.0,
            seed=42,
            max_tokens=64,
        )
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

        # Unload
        await gen.unload()

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_world_builder_with_real_model(self) -> None:
        """WorldBuilder generates a valid Bible with the real Qwen 7B model."""
        from src.backends.llm_backend import LlamaCppTextGenerator
        from src.config import ModelConfig
        from src.models.world_builder import WorldBuilder
        from src.job_queue import PipelineContext

        cfg = ModelConfig(
            provider="llama_cpp",
            model="qwen2.5-7b-instruct",
            quantization="Q4_K_M",
            file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            temperature=0.7,
            max_tokens=2048,
        )

        gen = LlamaCppTextGenerator(cfg)
        await gen.load()

        try:
            wb = WorldBuilder(gen, validator=None, config=None)
            ctx = PipelineContext(run_id="smoke_test", seed=42)
            ctx.state["tone"] = "dark_fantasy"
            ctx.state["title"] = "Smoke Test World"
            ctx.state["temperature"] = 0.3
            ctx.state["start_time"] = __import__("time").time()

            output = await wb.run(ctx)

            # Verify basic structure
            assert output.data is not None
            assert "world_name" in output.data, f"Missing world_name: {list(output.data.keys())[:5]}"
            assert "entities" in output.data
            assert "systems" in output.data

            # At least some characters
            chars = output.data["entities"].get("characters", [])
            assert len(chars) >= 1, f"Expected at least 1 character, got {len(chars)}"

            print(f"\n✓ World: {output.data['world_name']}")
            print(f"  Characters: {len(chars)}")
            print(f"  Locations: {len(output.data['entities'].get('locations', []))}")
            print(f"  Artifact ID: {output.artifact_id}")
        finally:
            await gen.unload()

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_minimal_pipeline_text_only(self) -> None:
        """Real-model Bible + Story generation (text only, no images)."""
        from src.backends.llm_backend import LlamaCppTextGenerator
        from src.config import ModelConfig
        from src.models.world_builder import WorldBuilder
        from src.models.story_writer import StoryWriter
        from src.job_queue import PipelineContext

        cfg = ModelConfig(
            provider="llama_cpp",
            model="qwen2.5-7b-instruct",
            quantization="Q4_K_M",
            file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            temperature=0.7,
            max_tokens=2048,
        )

        gen = LlamaCppTextGenerator(cfg)
        await gen.load()

        try:
            ctx = PipelineContext(run_id="smoke_text", seed=42)
            ctx.state["tone"] = "dark_fantasy"
            ctx.state["title"] = "The Short Tale"
            ctx.state["temperature"] = 0.3
            ctx.state["start_time"] = __import__("time").time()

            # Phase 1: World Bible
            wb = WorldBuilder(gen, validator=None, config=None)
            bible_out = await wb.run(ctx)
            ctx.outputs["bible"] = bible_out.data
            print(f"\n✓ Bible: {bible_out.data.get('world_name', '?')} ({bible_out.artifact_id})")

            # Phase 2: Story (single chapter)
            sw = StoryWriter(gen, validator=None, config=None)
            story_out = await sw.run(ctx)
            ctx.outputs["story"] = story_out.data

            chapters = story_out.data.get("chapters", [])
            assert len(chapters) >= 1, f"Expected at least 1 chapter, got {len(chapters)}"
            print(f"✓ Story: {len(chapters)} chapters ({story_out.artifact_id})")
            for ch in chapters:
                scenes = ch.get("scenes", [])
                print(f"  Ch{ch.get('number','?')}: {len(scenes)} scenes, "
                      f"{ch.get('summary', '')[:60]}...")
        finally:
            await gen.unload()

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_models_available_summary(self) -> None:
        """Report which models are available for testing."""
        models_dir = self._models_dir
        count = _model_count(models_dir)
        print(f"\n✓ Models directory: {models_dir}")
        print(f"  {count} GGUF files found")
        print(f"  Text model (Qwen 7B): {'✓' if _has_text_model(models_dir) else '✗'}")
        print(f"  Image model (SDXL): {'✓' if _has_image_model(models_dir) else '✗'}")
        assert count >= 1, "No GGUF models found"
