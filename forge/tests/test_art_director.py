"""Tests for ArtDirector PipelineStep."""

from __future__ import annotations

import pytest

from src.job_queue import PipelineContext
from src.models.art_director import ArtDirector
from src.models.base import PipelineError, StepOutput


class MockGenerator:
    """Mock TextGenerator for ArtDirector tests."""

    model_name: str = "test-model"
    quantization: str = "Q4_K_M"

    def __init__(self, output: dict | None = None) -> None:
        self.output = output or _make_minimal_style_bible()
        self.call_count = 0
        self.last_prompt: str = ""

    async def generate(
        self,
        prompt: str = "",
        schema: dict | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        self.call_count += 1
        self.last_prompt = prompt
        return dict(self.output)


def _make_minimal_bible() -> dict:
    return {
        "world_name": "Test World",
        "narrative_rules": {"tone": "dark_fantasy"},
        "entities": {
            "characters": [
                {"id": "char_01", "name": "Hero", "description": "A brave hero."},
                {"id": "char_02", "name": "Mentor", "description": "A wise mentor."},
            ],
            "locations": [
                {"id": "loc_01", "name": "Village", "description": "Small village."},
                {"id": "loc_02", "name": "Dungeon", "description": "Dark dungeon."},
            ],
        },
        "systems": {
            "magic": {"source": "Mana", "rules": ["Rule 1"], "limitations": "Limited"},
        },
    }


def _make_minimal_style_bible() -> dict:
    return {
        "art_style": {
            "palette": "dark tones",
            "lighting": "low-key",
            "composition": "off-center",
            "linework": "ink",
            "mood": "melancholy",
            "forbidden": ["modern", "neon"],
        },
        "character_design": {
            "char_01": "A warrior.",
            "char_02": "An elder.",
        },
        "location_palettes": {
            "loc_01": "Warm village.",
            "loc_02": "Dark dungeon.",
        },
    }


class TestArtDirector:
    """ArtDirector PipelineStep tests."""

    @pytest.mark.asyncio
    async def test_generates_style_bible(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        director = ArtDirector(generator=MockGenerator())
        output = await director.run(ctx)

        assert isinstance(output, StepOutput)
        assert output.step_name == "art_director"
        assert "art_style" in output.data
        assert output.data["art_style"]["palette"] == "dark tones"

    @pytest.mark.asyncio
    async def test_generates_artifact_id(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        director = ArtDirector(generator=MockGenerator())
        output = await director.run(ctx)

        assert output.artifact_id is not None
        assert output.artifact_id.startswith("style_")

    @pytest.mark.asyncio
    async def test_requires_bible_in_context(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        # No bible in context.outputs

        director = ArtDirector(generator=MockGenerator())
        with pytest.raises(PipelineError, match="context.outputs"):
            await director.run(ctx)

    @pytest.mark.asyncio
    async def test_passes_bible_summary_to_prompt(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        gen = MockGenerator()
        director = ArtDirector(generator=gen)
        await director.run(ctx)

        # Prompt should contain entity names
        assert "Hero" in gen.last_prompt
        assert "Village" in gen.last_prompt

    @pytest.mark.asyncio
    async def test_includes_version_metadata(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        director = ArtDirector(generator=MockGenerator())
        output = await director.run(ctx)

        assert output.data["schema_version"] == 1
        assert output.data["seed"] == 42
        assert "created_at" in output.data

    @pytest.mark.asyncio
    async def test_deterministic_artifact_id(self) -> None:
        ctx = PipelineContext(run_id="r1", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        gen = MockGenerator()
        out1 = await ArtDirector(generator=gen).run(ctx)
        out2 = await ArtDirector(generator=gen).run(ctx)

        assert out1.artifact_id == out2.artifact_id

    @pytest.mark.asyncio
    async def test_bible_summary_includes_magic(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_minimal_bible()

        gen = MockGenerator()
        director = ArtDirector(generator=gen)
        await director.run(ctx)

        assert "Mana" in gen.last_prompt
        assert "Rule 1" in gen.last_prompt


class TestArtDirectorEdgeCases:
    """Edge cases for ArtDirector."""

    @pytest.mark.asyncio
    async def test_empty_entities_does_not_crash(self) -> None:
        """Bible with no entities at all should not crash."""
        bible = {
            "world_name": "Empty World",
            "narrative_rules": {"tone": "dark_fantasy"},
            "entities": {},
            "systems": {},
        }
        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.outputs["bible"] = bible

        gen = MockGenerator()
        director = ArtDirector(generator=gen)
        output = await director.run(ctx)
        assert output.artifact_id is not None

    @pytest.mark.asyncio
    async def test_no_magic_system_section(self) -> None:
        """Bible without systems.magic should not crash."""
        bible = _make_minimal_bible()
        del bible["systems"]["magic"]
        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.outputs["bible"] = bible

        gen = MockGenerator()
        director = ArtDirector(generator=gen)
        output = await director.run(ctx)
        assert output.artifact_id is not None
        assert "Mana" not in gen.last_prompt
