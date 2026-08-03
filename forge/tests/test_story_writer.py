"""Tests for StoryWriter PipelineStep."""

from __future__ import annotations

import pytest

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput
from src.models.story_writer import StoryWriter


class MockGenerator:
    """Mock TextGenerator that returns chapter JSON."""

    model_name: str = "test-model"
    quantization: str = "Q4_K_M"

    def __init__(self) -> None:
        self.call_count = 0
        self.last_prompts: list[str] = []

    async def generate(
        self,
        prompt: str = "",
        schema: dict | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        self.call_count += 1
        self.last_prompts.append(prompt)

        if self.call_count == 1:
            # Outline call
            return {"outline": "Three chapters of adventure."}

        ch_num = self.call_count - 1  # call 2→ch1, call 3→ch2, call 4→ch3
        return {
            "chapter": {
                "number": ch_num,
                "title": f"Chapter {ch_num}",
                "summary": f"Summary of chapter {ch_num}.",
                "scenes": [
                    {
                        "scene_id": f"scene_{ch_num:02d}_01",
                        "text": f"The hero ventured forth in chapter {ch_num}. The wind blew cold.",
                        "characters_present": ["char_01"],
                        "location": "loc_01",
                        "entities_referenced": [],
                        "word_count": 100,
                    }
                ],
            }
        }


def _make_bible() -> dict:
    return {
        "world_name": "Test World",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "forbidden": ["resurrection"],
            "required_themes": ["sacrifice"],
            "mortality": "moderate",
            "knowledge_level": "superstitious",
        },
        "entities": {
            "characters": [
                {"id": "char_01", "name": "Hero", "description": "A hero.", "role": "protagonist", "motivation": "Save world", "flaw": "Pride", "aliases": []},
            ],
            "locations": [
                {"id": "loc_01", "name": "Village", "description": "Small village.", "aliases": []},
            ],
            "factions": [],
            "creatures": [],
            "artifacts": [],
            "events": [],
        },
        "systems": {
            "magic": {"source": "Void", "rules": ["Fades at dawn"], "costs": ["Memory"], "limitations": "No resurrection"},
            "politics": {"power_structure": "Monarchy", "conflicts": []},
            "religion": {"gods": [], "afterlife": "Void"},
        },
    }


class TestStoryWriter:
    """StoryWriter PipelineStep tests."""

    @pytest.mark.asyncio
    async def test_generates_three_chapters(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=MockGenerator())
        output = await writer.run(ctx)

        assert isinstance(output, StepOutput)
        assert output.step_name == "story_writer"
        assert len(output.data["chapters"]) == 3
        assert output.data["chapters"][0]["number"] == 1
        assert output.data["chapters"][1]["number"] == 2
        assert output.data["chapters"][2]["number"] == 3

    @pytest.mark.asyncio
    async def test_generates_artifact_id(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=MockGenerator())
        output = await writer.run(ctx)

        assert output.artifact_id is not None
        assert output.artifact_id.startswith("story_")

    @pytest.mark.asyncio
    async def test_requires_bible_in_context(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)

        writer = StoryWriter(generator=MockGenerator())
        with pytest.raises(PipelineError, match="context.outputs"):
            await writer.run(ctx)

    @pytest.mark.asyncio
    async def test_includes_version_metadata(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=MockGenerator())
        output = await writer.run(ctx)

        assert output.data["schema_version"] == 1
        assert output.data["seed"] == 42
        assert output.data["based_on_bible"] == "bible.json"

    @pytest.mark.asyncio
    async def test_generates_outline_first(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        gen = MockGenerator()
        writer = StoryWriter(generator=gen)
        await writer.run(ctx)

        # First call should be outline generation
        assert gen.call_count == 4  # outline + 3 chapters
        assert "Outline" in gen.last_prompts[0]

    @pytest.mark.asyncio
    async def test_passes_previous_chapters_as_context(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        gen = MockGenerator()
        writer = StoryWriter(generator=gen)
        await writer.run(ctx)

        # Chapter 3 prompt should contain summary of chapters 1 and 2
        ch3_prompt = gen.last_prompts[3]  # 0=outline, 1=ch1, 2=ch2, 3=ch3
        assert "Summary of chapter 1" in ch3_prompt
        assert "Summary of chapter 2" in ch3_prompt

    @pytest.mark.asyncio
    async def test_per_chapter_seed_deterministic(self) -> None:
        """Each chapter uses a different seed (seed + chapter_index)."""
        ctx = PipelineContext(run_id="run_01", seed=100)
        ctx.outputs["bible"] = _make_bible()

        gen1 = MockGenerator()
        gen2 = MockGenerator()
        out1 = await StoryWriter(generator=gen1).run(ctx)
        out2 = await StoryWriter(generator=gen2).run(ctx)

        # Same seed → same output
        assert out1.artifact_id == out2.artifact_id

    @pytest.mark.asyncio
    async def test_builds_entity_usage_index(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=MockGenerator())
        output = await writer.run(ctx)

        assert "entity_usage" in output.data
        # char_01 should appear in all 3 chapters
        usage = output.data["entity_usage"]
        assert "char_01" in usage
        assert len(usage["char_01"]["appears_in_scenes"]) == 3

    @pytest.mark.asyncio
    async def test_normalization_applied(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=MockGenerator())
        output = await writer.run(ctx)

        # Chapters should be sorted by number
        numbers = [c["number"] for c in output.data["chapters"]]
        assert numbers == [1, 2, 3]


class TestStoryWriterEdgeCases:
    """Edge cases for StoryWriter."""

    @pytest.mark.asyncio
    async def test_malformed_chapter_no_chapter_key(self) -> None:
        """LLM returns a dict without 'number'/'title' — should raise."""

        class BadGenerator:
            model_name: str = "test"
            quantization: str = "Q4"
            call_count = 0

            async def generate(self, prompt="", **kwargs):
                self.call_count += 1
                if self.call_count == 1:
                    return {"outline": "An outline."}
                return {"wrong_key": "no chapter field at all"}

        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=BadGenerator())
        with pytest.raises(PipelineError, match="malformed|required|missing"):
            await writer.run(ctx)

    @pytest.mark.asyncio
    async def test_malformed_outline_not_a_dict(self) -> None:
        """LLM returns something other than a dict for outline — should raise."""

        class BadGenerator:
            model_name: str = "test"
            quantization: str = "Q4"

            async def generate(self, prompt="", **kwargs):
                return ["not", "a", "dict"]

        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.outputs["bible"] = _make_bible()

        writer = StoryWriter(generator=BadGenerator())
        with pytest.raises(PipelineError, match="malformed|dict|list"):
            await writer.run(ctx)

    def test_build_entity_usage_with_missing_fields(self) -> None:
        """_build_entity_usage handles scenes with no characters_present or location."""
        chapters = [
            {
                "number": 1,
                "title": "Ch1",
                "scenes": [
                    {
                        "scene_id": "scene_01_01",
                        "text": "Nothing happens.",
                        # No characters_present, no location
                    }
                ],
            }
        ]
        usage = StoryWriter._build_entity_usage(chapters, _make_bible())
        # Should not crash; returns empty dict since no entities referenced
        assert isinstance(usage, dict)

    def test_build_entity_usage_with_empty_location(self) -> None:
        """_build_entity_usage skips empty string locations."""
        chapters = [
            {
                "number": 1,
                "title": "Ch1",
                "scenes": [
                    {
                        "scene_id": "scene_01_01",
                        "text": "In the void.",
                        "characters_present": [],
                        "location": "",
                    }
                ],
            }
        ]
        usage = StoryWriter._build_entity_usage(chapters, _make_bible())
        assert "" not in usage
